"""Owned CPU logits network and parameter shape plan; framework passed only after worker admission."""
from __future__ import annotations

from collections import OrderedDict

from .training_io import require
from .training_record import TrainingJob


def parameter_shapes(job):
    require(type(job) is TrainingJob, "admitted training job required")
    record = job.record()["architecture"]
    channels, shapes = 3, {}
    for index, block in enumerate(record["convBlocks"]):
        base = f"features.conv_{index}"
        out = block["outChannels"]
        shapes[base + ".weight"] = (out, channels, *block["kernel"])
        if block["bias"]:
            shapes[base + ".bias"] = (out,)
        channels = out
    for name, size, bias in (("occupancy_head", 1, record["occupancyBias"]),
                              ("bin_head", len(job.class_order), record["binBias"])):
        shapes[name + ".weight"] = (size, channels)
        if bias:
            shapes[name + ".bias"] = (size,)
    return dict(sorted(shapes.items()))


def build_model(job, torch):
    """Construct exact record architecture and overwrite every constructor-initialized parameter."""
    arch = job.record()["architecture"]

    class TwoHead(torch.nn.Module):
        def __init__(self):
            super().__init__()
            layers, channels = OrderedDict(), 3
            for index, block in enumerate(arch["convBlocks"]):
                layers[f"conv_{index}"] = torch.nn.Conv2d(
                    channels, block["outChannels"], tuple(block["kernel"]), stride=tuple(block["stride"]),
                    padding=tuple(block["padding"]), dilation=tuple(block["dilation"]), groups=1,
                    bias=block["bias"], padding_mode="zeros", device="cpu", dtype=torch.float32)
                layers[f"relu_{index}"] = torch.nn.ReLU(inplace=False)
                channels = block["outChannels"]
            self.features = torch.nn.Sequential(layers)
            self.pool = torch.nn.AdaptiveAvgPool2d((1, 1))
            self.flatten = torch.nn.Flatten(start_dim=1, end_dim=-1)
            self.occupancy_head = torch.nn.Linear(channels, 1, bias=arch["occupancyBias"], device="cpu", dtype=torch.float32)
            self.bin_head = torch.nn.Linear(channels, len(job.class_order), bias=arch["binBias"], device="cpu", dtype=torch.float32)

        def forward(self, image):
            features = self.flatten(self.pool(self.features(image)))
            return self.occupancy_head(features), self.bin_head(features)

    model = TwoHead()
    actual = {name: tuple(value.shape) for name, value in sorted(model.named_parameters())}
    require(actual == parameter_shapes(job), "actual named network parameters differ from admitted plan")
    require(sum(value.numel() for value in model.parameters()) == job.parameter_count, "parameter count mismatch")
    generator = torch.Generator(device="cpu").manual_seed(job.record()["optimisation"]["seeds"]["initialization"])
    init = arch["initialization"]
    with torch.no_grad():
        for _, parameter in sorted(model.named_parameters()):
            torch.nn.init.uniform_(parameter, a=init["low"], b=init["high"], generator=generator)
    return model
