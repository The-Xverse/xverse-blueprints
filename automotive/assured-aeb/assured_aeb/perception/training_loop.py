"""Record-driven fit and training-selection checkpoint loop; imports no framework at module load."""
from __future__ import annotations

import hashlib
import math

from .training_io import canonical, require
from .training_network import build_model
from .training_weights import encode_weights


def sample_identity(sample):
    return {"runId": sample["runId"], "frame": sample["frame"], "rawSha256": sample["label"]["rawSha256"]}


def epoch_order(identities, *, seed, epoch):
    """Owned deterministic seeded permutation; digest collisions resolve by canonical identity bytes."""
    def key(identity):
        encoded = canonical(identity)
        return hashlib.sha256(canonical({"seed": seed, "epoch": epoch, "sample": identity})).digest(), encoded
    return sorted(identities, key=key)


def equal_example_mean(values):
    values = list(values)
    require(bool(values) and all(math.isfinite(value) for value in values), "finite nonempty per-example losses required")
    result = math.fsum(values) / len(values)
    require(math.isfinite(result), "nonfinite mean loss")
    return result


def checkpoint_is_better(loss, epoch, best_loss, best_epoch):
    require(math.isfinite(loss), "nonfinite checkpoint loss")
    return best_loss is None or loss < best_loss or (loss == best_loss and epoch < best_epoch)


def _finite(torch, tensor, name):
    require(bool(torch.isfinite(tensor).all().item()), "nonfinite " + name)


def _extract(state):
    return {name: value.detach().cpu().contiguous().numpy().astype("<f4", copy=False).tobytes(order="C")
            for name, value in sorted(state.items())}


def _requested_samples(dataset, requested):
    """Bounded one-batch raw retention. The4a iterator verifies every actual read again."""
    keys = {canonical(identity): index for index, identity in enumerate(requested)}
    require(len(keys) == len(requested), "duplicate requested sample identity")
    found = {}
    for sample in dataset.iter_samples("fit"):
        key = canonical(sample_identity(sample))
        if key in keys:
            require(key not in found, "duplicate fit sample")
            found[key] = sample
            if len(found) == len(keys):
                break
    require(len(found) == len(keys), "admitted fit sample disappeared or changed identity")
    return [found[canonical(identity)] for identity in requested]


def _batch(samples, job, torch, numpy, shared, params):
    record = job.record()
    images, occupancy, bins = [], [], []
    for sample in samples:
        array = shared.preprocess(sample["raw"], record["dataset"]["frameFormat"], params)
        require(array.dtype == numpy.dtype("float32") and tuple(array.shape) == job.input_shape and array.flags.c_contiguous,
                "shared preprocessing returned incompatible float32 NCHW")
        require(bool(numpy.isfinite(array).all()), "nonfinite preprocessed input")
        images.append(array)
        occupancy.append(sample["occupancyTarget"])
        bins.append(sample["binIndex"])
        require(type(occupancy[-1]) is int and occupancy[-1] in (0, 1) and type(bins[-1]) is int
                and 0 <= bins[-1] < len(job.class_order), "admitted target shape/order mismatch")
    image = torch.from_numpy(numpy.concatenate(images, axis=0))
    target_occ = torch.tensor(occupancy, dtype=torch.float32, device="cpu").reshape(-1, 1)
    target_bins = torch.tensor(bins, dtype=torch.int64, device="cpu")
    return image, target_occ, target_bins


def _losses(model, batch, job, torch):
    image, occupancy, bins = batch
    logits_occ, logits_bins = model(image)
    size = image.shape[0]
    require(tuple(logits_occ.shape) == (size, 1) and tuple(logits_bins.shape) == (size, len(job.class_order)),
            "actual logits shapes differ from admitted two-head contract")
    for name, logits in (("occupancy logits", logits_occ), ("bin logits", logits_bins)):
        require(logits.dtype == torch.float32 and logits.device.type == "cpu", "CPU float32 logits required")
        _finite(torch, logits, name)
    weights = job.record()["optimisation"]["lossWeights"]
    occ = torch.nn.functional.binary_cross_entropy_with_logits(logits_occ, occupancy, reduction="none").reshape(-1)
    bin_loss = torch.nn.functional.cross_entropy(logits_bins, bins, reduction="none")
    losses = weights["occupancy"] * occ + weights["bins"] * bin_loss
    _finite(torch, losses, "per-example loss")
    return losses


def fit(job, dataset, stage_sha256, *, torch, numpy, shared):
    """Called only by admitted fresh worker. Never asks dataset for calibration/test samples."""
    record = job.record()
    opt = record["optimisation"]
    require(dataset.report()["jobSha256"] == job.sha256, "dataset/job identity mismatch")
    params = shared.load_params(record["preprocessing"]["record"])
    expected_binding = {shared.META_PREFIX + "schema": shared.SCHEMA,
                        shared.META_PREFIX + "paramsSha256": record["preprocessing"]["sha256"],
                        shared.META_PREFIX + "codeSha256": record["preprocessing"]["codeSha256"],
                        shared.META_PREFIX + "numpy": record["preprocessing"]["numpyVersion"]}
    shared.verify_binding(expected_binding, params, numpy_version=numpy.__version__)
    model = build_model(job, torch)
    for parameter in model.parameters():
        _finite(torch, parameter, "initialized weights")
    initial_descriptor, initial_blob = encode_weights(_extract(model.state_dict()), job, stage_sha256)
    del initial_blob
    optimizer = torch.optim.SGD(model.parameters(), lr=opt["learningRate"], momentum=opt["momentum"],
                                dampening=opt["dampening"], weight_decay=opt["weightDecay"], nesterov=opt["nesterov"],
                                maximize=False, foreach=False, differentiable=False, fused=False)
    identities = [sample_identity(sample) for sample in dataset.iter_samples("fit")]
    require(bool(identities) and len({canonical(identity) for identity in identities}) == len(identities), "unique nonempty fit index required")
    order_digest, epochs, updates = hashlib.sha256(), [], 0
    best_loss, best_epoch, selected = None, None, None
    batch_size = opt["batchSize"]
    for epoch in range(1, opt["epochs"] + 1):
        model.train()
        ordered = epoch_order(identities, seed=opt["seeds"]["dataOrder"], epoch=epoch)
        fit_losses = []
        for start in range(0, len(ordered), batch_size):
            requested = ordered[start:start + batch_size]
            for identity in requested:
                order_digest.update(canonical({"epoch": epoch, "sample": identity}) + b"\n")
            samples = _requested_samples(dataset, requested)
            batch = _batch(samples, job, torch, numpy, shared, params)
            optimizer.zero_grad(set_to_none=True)
            losses = _losses(model, batch, job, torch)
            loss = losses.mean()
            _finite(torch, loss, "mean training loss")
            fit_losses.extend(losses.detach().cpu().tolist())
            loss.backward()
            for parameter in model.parameters():
                require(parameter.grad is not None, "missing trainable parameter gradient")
                _finite(torch, parameter.grad, "gradient")
            optimizer.step()
            for parameter in model.parameters():
                _finite(torch, parameter, "updated weights")
            for state in optimizer.state.values():
                for value in state.values():
                    if torch.is_tensor(value):
                        _finite(torch, value, "SGD state")
            updates += 1
        row = {"epoch": epoch, "fitExamples": len(fit_losses), "fitMeanLoss": equal_example_mean(fit_losses),
               "selectionExamples": None, "selectionMeanLoss": None}
        if epoch in opt["selection"]["epochs"]:
            model.eval()
            selection_losses, pending = [], []
            with torch.no_grad():
                for sample in dataset.iter_samples("selection"):
                    pending.append(sample)
                    if len(pending) == batch_size:
                        selection_losses.extend(_losses(model, _batch(pending, job, torch, numpy, shared, params), job, torch).cpu().tolist())
                        pending.clear()
                if pending:
                    selection_losses.extend(_losses(model, _batch(pending, job, torch, numpy, shared, params), job, torch).cpu().tolist())
            selection_loss = equal_example_mean(selection_losses)
            row.update(selectionExamples=len(selection_losses), selectionMeanLoss=selection_loss)
            if checkpoint_is_better(selection_loss, epoch, best_loss, best_epoch):
                selected = {name: value.detach().cpu().clone() for name, value in sorted(model.state_dict().items())}
                best_loss, best_epoch = selection_loss, epoch
        epochs.append(row)
    require(selected is not None and updates == dataset.report()["trainingUpdates"], "incomplete optimizer/checkpoint work")
    descriptor, blob = encode_weights(_extract(selected), job, stage_sha256)
    model.load_state_dict(selected, strict=True)
    model.eval()
    # Report no host times/paths. This output is development-only; not a frozen camera model.
    import json
    first, final = json.loads(initial_descriptor), json.loads(descriptor)
    report = {"schema": "assured-aeb.training-fit-report/1", "jobSha256": job.sha256,
              "stageSha256": stage_sha256, "datasetReportSha256": hashlib.sha256(canonical(dataset.report())).hexdigest(),
              "manifestSha256": record["dataset"]["manifestSha256"], "classOrder": list(job.class_order),
              "architecture": record["architecture"], "optimisation": opt, "preprocessing": record["preprocessing"],
              "epochs": epochs, "updates": updates, "sampleOrderSha256": order_digest.hexdigest(),
              "selectedEpoch": best_epoch, "selectedLoss": best_loss,
              "initialNamedWeightsSha256": first["namedWeightsSha256"], "selectedNamedWeightsSha256": final["namedWeightsSha256"],
              "weightsSha256": final["weightsSha256"], "weightDescriptorSha256": hashlib.sha256(descriptor).hexdigest(),
              "purpose": record["identity"]["purpose"], "state": "trained-development-only"}
    return model, descriptor, blob, report
