"""TEST-ONLY binding from the existing genuine model fixture's postprocess metadata."""
import copy

from assured_aeb import postprocess as PP
from assured_aeb.model_output_binding import ModelOutputBinding
from fixtures.make_camera_model import POSTPROCESS


def model_metadata(labels=None):
    record = copy.deepcopy(POSTPROCESS)
    if labels is not None:
        record["binLabels"] = list(labels)
    return PP.metadata_entry(record)


def model_binding(labels=None):
    return ModelOutputBinding(model_metadata(labels))
