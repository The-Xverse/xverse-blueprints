"""Small immutable Fusion binding derived from verified canonical postprocess metadata.

Trusted unit composition must supply metadata from the same digest-verified frozen
model used by CameraInference.load, before readiness. Parsing here verifies the
owned code/record binding; it does not attest the origin of an arbitrary mapping.
No model session, vector, full postprocess record or scientific default is retained.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from . import postprocess as PP


@dataclass(frozen=True, slots=True, init=False)
class ModelOutputBinding:
    bin_labels: tuple[str, ...]
    postprocess_sha256: str

    def __init__(self, metadata: Mapping[str, str]) -> None:
        if not isinstance(metadata, Mapping):
            raise TypeError("frozen model metadata is required")
        detached = dict(metadata)
        PP.verify_binding(detached)
        post = PP.parse(detached)
        object.__setattr__(self, "bin_labels", post.bin_labels)
        object.__setattr__(self, "postprocess_sha256", post.sha256)
