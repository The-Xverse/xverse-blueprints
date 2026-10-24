"""WP14b0 stdlib controls. ALL numbers/model outputs/identities are TEST-ONLY.

Real source owners produce every envelope; the inference callable is deterministic/model-free,
not an ORT/calibration-quality claim. Full owning/topology verification is coordinator-scheduled.
"""
from __future__ import annotations

from model_output_fixture import model_binding, model_metadata

import copy
from dataclasses import FrozenInstanceError, fields
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest

from assured_aeb import adas_contract as A, camera_chain as CC, camera_inference as CI
from assured_aeb import fusion_aeb as F, parameters as P, radar_zone as R, role_contract as C, vc_functional as V
from assured_aeb import model_contract as MC, postprocess as PP
from assured_aeb.model_output_binding import ModelOutputBinding
from fixtures.make_camera_model import model_bytes
import test_u4_untrusted as UFixture

BASE = "b21824a06bf1264aefa201001cb73fc7d13087c6"
LABELS = ("no-obstacle", "overlap", "bin-0", "bin-1", "bin-2", "beyond")
PROVENANCE = {"modelDigest": "a"*64, "preprocessParamsSha256": "b"*64,
              "postprocessSha256": model_binding().postprocess_sha256}


def projection(threshold=0.5):
    # Explicit TEST-ONLY producer parameters; no protocol defaults or real-data value selection.
    values = {"vehicle.egoFrontM": 2.4, "radar.mountM": [2.0,0.0], "radar.closingSpeedSign": -1,
              "fusion.corridor.halfWidthM": 1.5, "fusion.corridor.maxRangeM": 80.0,
              "fusion.cameraFreshnessNs": 1000, "fusion.radarFreshnessNs": 1000,
              "fusion.occupancyThreshold": threshold, "fusion.distanceBinEdgesM": [10.0,20.0,40.0],
              "fusion.associationToleranceM": 1.0, "aeb.distanceUncertaintyM": 0.5, "aeb.speedUncertaintyMps": 0.5,
              "aeb.latencyNs": 100, "aeb.decelerationMps2": 6.0, "aeb.marginM": 1.0, "aeb.brakeLevel": 1.0,
              "aeb.releaseSpeedMps": 0.5, "aeb.releaseAbsentCycles": 3,
              "arbiter.requestFreshnessNs": 1000, "arbiter.holdWindowNs": 1000}
    return P.Projection(dict(schema=P.PROJECTION,protocolRecordSha256="d"*64,unit="adas-hpc",entries=values))


def inputs(directory, probability=0.8, *, metadata=None, model_digest=None):
    metadata = model_metadata() if metadata is None else metadata
    PP.verify_binding(metadata)
    post = PP.parse(metadata)
    now = 1000
    pixels = bytes(range(256))*4
    digest = hashlib.sha256(pixels).hexdigest()
    fmt = {"schema":"xverse-compat.camera-frame-format/1","width":16,"height":16,"encoding":"bgra8"}
    stage = CC.CorruptionStage(CC.CorruptionSchedule.from_record(
        {"schema":CC.CORRUPTION,"seed":7,"frameFormat":fmt,"events":[]}))
    stage.bind_origin(now)
    camera_item = {"type":"item","flowId":"camera","sequence":1,"originNs":now,"frame":7,
                   "value":{"width":16,"height":16,"fovDeg":90.0,"rawSha256":digest,"rawLength":len(pixels)}}
    delivered, raw = stage.process(camera_item,pixels)
    camera = CC.SmartCamera(CC.SmartCameraParams.from_record({"schema":CC.CAMERA_CHECKS,"frameFormat":fmt,
        "stats":{"statsStride":1,"darkLevel":8,"brightLevel":247,"sharpnessBoxLog2":1},
        "thresholds":{"minMeanLuma":0.0,"maxMeanLuma":255.0,"minStdLuma":0.0,"maxStdLuma":255.0,
                      "maxDarkFraction":1.0,"maxBrightFraction":1.0,"minHighFrequencyVariance":0.0,"maxHighFrequencyVariance":65536.0}}))
    zone = R.FrontZone(R.FrontZoneParams.from_record({"schema":R.FRONT_ZONE,"cameraFreshnessWindowNs":1000,"radarFreshnessWindowNs":1000}))
    f07 = dict(zone.step(now,[("smart-camera-evidence",camera.step(now,delivered,raw))]))[CI.STREAM]
    root = Path(directory);(root/digest[:2]).mkdir()
    (root/digest[:2]/digest).write_bytes(pixels)
    probabilities = {"no-obstacle":0.05,"overlap":0.05,"bin-0":0.05,"bin-1":0.05,"bin-2":0.7,"beyond":0.1}
    result = {"occupancyProbability":probability,"binProbabilities":[probabilities[label] for label in post.bin_labels],
              "predictedBin":"bin-2","oodScore":0.3,"oodFlag":False}
    with CI.SpoolReader(root) as spool:
        perception = CI.CameraInference(infer=lambda frame:copy.deepcopy(result),frame_length=len(pixels),
            spool=spool,provenance=dict(PROVENANCE,modelDigest=PROVENANCE["modelDigest"] if model_digest is None else model_digest,
                                       postprocessSha256=post.sha256),bin_labels=post.bin_labels).step(f07)
    assert perception["state"] == "NOMINAL"
    sensor = R.SmartRadar(R.SmartRadarParams.from_record({"schema":R.RADAR_CHECKS,
        "spec":{"rangeM":100.0,"horizontalFovDeg":30.0,"verticalFovDeg":10.0,"maxVelocityMps":100.0,"maxDetections":500},
        "thresholds":{"minCount":1,"maxCount":200}}),"radar-adas")
    item = {"type":"item","flowId":"radar-adas","sequence":1,"originNs":now,"frame":1,
            "value":{"detections":[[0.0,0.0,40.0,-10.0]],"count":1}}
    radar = dict(zone.step(now,[("smart-radar-evidence",sensor.step(now,item))]))["f08-radar-adas"]
    return perception,radar


def legacy_product(record):
    result = copy.deepcopy(record)
    result["schema"] = A.HISTORICAL_SCHEMA
    for key in ("inputQuality","occupancyDecisionConfidence","distanceClassConfidence"):
        result["sources"]["camera"].pop(key)
    result["sources"]["radar"].pop("checks")
    return result


class InterfaceTests(unittest.TestCase):
    def test_real_owner_chain_emits_minimal_detached_native_v2(self):
        with tempfile.TemporaryDirectory() as directory:
            camera,radar = inputs(directory)
            out = F.FusionRiskAeb(projection(), model_output_binding=model_binding()).step(1000,perception=camera,radar=radar)
        self.assertEqual(A.validate(out),out)
        self.assertEqual(out["schema"],"assured-aeb.adas-cycle/2")
        quality = out["sources"]["camera"]["inputQuality"]
        self.assertEqual(set(quality),set(A.QUALITY_KEYS));self.assertIs(quality["fresh"],True)
        self.assertNotIn("indicators",quality)
        self.assertEqual(out["sources"]["camera"]["occupancyDecisionConfidence"],0.8)
        self.assertEqual(out["sources"]["camera"]["distanceClassConfidence"],0.7)
        self.assertEqual(out["sources"]["camera"]["provenance"],PROVENANCE)
        self.assertEqual(out["sources"]["radar"]["checks"],radar["checks"])
        radar["checks"]["sensorSelfCheck"]["logical"]["failed"].append("changed")
        self.assertEqual(out["sources"]["radar"]["checks"]["sensorSelfCheck"]["logical"]["failed"],[])
        self.assertNotIn("binProbabilities",out["sources"]["camera"])
        self.assertNotIn("oodScore",out["sources"]["camera"])

    def test_occupancy_confidence_follows_actual_admitted_decision_including_zero(self):
        for p,threshold,expected in ((0,0.5,1),(0,0,0),(0.6,0.8,0.4),(0.8,0.8,0.8)):
            with tempfile.TemporaryDirectory() as directory:
                camera,radar=inputs(directory,p)
                out=F.FusionRiskAeb(projection(threshold), model_output_binding=model_binding()).step(1000,perception=camera,radar=radar)
            self.assertEqual(out["sources"]["camera"]["occupancyDecisionConfidence"],expected)
            self.assertEqual(out["sources"]["camera"]["distanceClassConfidence"],0.7)
        self.assertEqual(A.confidences({"occupancyProbability":True,"provenance":PROVENANCE},
                                     threshold=0.5,binding=model_binding()),(None,None))

    def test_unknown_metadata_never_becomes_a_favorable_default(self):
        valid={name:"pass" for name in A.QUALITY_KEYS};valid.update(sequence="ok",fresh=False)
        self.assertIs(A.camera_quality(valid)["fresh"],False)
        for key,value in (("fresh",1),("sequence",True),("sensorLogical","unknown"),("sensorStatistical",[])):
            mutated=copy.deepcopy(valid);mutated[key]=value
            self.assertIsNone(A.camera_quality(mutated)[key])
        self.assertEqual(A.camera_quality({**valid,"newClass":"pass"}),dict.fromkeys(A.QUALITY_KEYS))
        self.assertEqual(A.camera_quality(None),dict.fromkeys(A.QUALITY_KEYS))
        for result in ({"binProbabilities":[0.2],"predictedBin":"bin-0"},
                       {"binProbabilities":[True]*6,"predictedBin":"bin-0"},
                       {"binProbabilities":[0.2]*6,"predictedBin":"undeclared"}):
            result["provenance"] = PROVENANCE
            self.assertIsNone(A.confidences(result,threshold=0.5,binding=model_binding())[1])

    def test_real_permuted_model_metadata_and_camera_owner_bind_selected_confidence(self):
        labels=("no-obstacle","overlap","bin-2","bin-0","bin-1","beyond")
        # Same genuine frozen-model metadata flow as the static phase of CI.load; no session/ORT claim.
        from xverse_compat.inference.loader import verified_bytes
        frozen=model_bytes(metadata_override=model_metadata(labels))
        digest="sha256:"+hashlib.sha256(frozen).hexdigest()
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"model.onnx";path.write_bytes(frozen)
            actual=MC.inspect(verified_bytes(path,digest))
            binding=ModelOutputBinding(actual.metadata)
            camera,radar=inputs(directory,metadata=actual.metadata,model_digest=digest[len("sha256:"):])
        self.assertEqual(binding.bin_labels,labels)
        self.assertNotEqual(binding.postprocess_sha256,model_binding().postprocess_sha256)
        self.assertEqual(actual.outputs[1][1],[1,len(labels)])
        self.assertEqual(camera["binProbabilities"],[0.05,0.05,0.7,0.05,0.05,0.1])
        self.assertEqual(camera["predictedBin"],"bin-2")
        self.assertEqual(camera["provenance"]["postprocessSha256"],binding.postprocess_sha256)
        self.assertEqual(camera["provenance"]["modelDigest"],digest[len("sha256:"):])
        out=F.FusionRiskAeb(projection(),model_output_binding=binding).step(1000,perception=camera,radar=radar)
        self.assertEqual(out["sources"]["camera"]["distanceClassConfidence"],0.7)
        self.assertEqual(out["sources"]["camera"]["occupancyDecisionConfidence"],0.8)
        A.validate(out)
        self.assertNotIn("binProbabilities",out["sources"]["camera"])
        self.assertNotIn("binLabels",out["sources"]["camera"])

    def test_binding_is_metadata_derived_frozen_detached_and_refuses_unrelated_pairs(self):
        metadata=model_metadata();binding=ModelOutputBinding(metadata)
        self.assertEqual({field.name for field in fields(binding)},{"bin_labels","postprocess_sha256"})
        metadata[PP.META_KEY]="changed"
        self.assertEqual(binding,model_binding())
        with self.assertRaises(FrozenInstanceError):binding.bin_labels=tuple(reversed(LABELS))
        with self.assertRaises(TypeError):ModelOutputBinding([])
        with self.assertRaises(TypeError):ModelOutputBinding(LABELS,"c"*64)
        with self.assertRaises(TypeError):ModelOutputBinding(bin_labels=LABELS,postprocess_sha256="c"*64)
        for bad in ({}, {**model_metadata(),PP.CODE_KEY:"0"*64},
                    {**model_metadata(),PP.META_KEY:"{}"},
                    {**model_metadata(),PP.META_KEY:json.dumps(json.loads(model_metadata()[PP.META_KEY]),indent=2)}):
            with self.assertRaises(ValueError):ModelOutputBinding(bad)
        with self.assertRaises(TypeError):F.FusionRiskAeb(projection())
        for bad in (None, LABELS, {"bin_labels":LABELS,"postprocess_sha256":binding.postprocess_sha256}):
            with self.assertRaises(TypeError):F.FusionRiskAeb(projection(),model_output_binding=bad)
        for labels in (LABELS[:-1],(*LABELS[:-1],"bin-3"),(*LABELS,"bin-3")):
            with self.assertRaises(ValueError):F.FusionRiskAeb(projection(),model_output_binding=model_binding(labels))

    def test_provenance_mismatch_is_unavailable_without_productive_change(self):
        with tempfile.TemporaryDirectory() as directory:camera,radar=inputs(directory)
        wrong=model_binding(("no-obstacle","overlap","bin-2","bin-0","bin-1","beyond"))
        good=F.FusionRiskAeb(projection(),model_output_binding=model_binding())
        mismatched=F.FusionRiskAeb(projection(),model_output_binding=wrong)
        for now,cp,rp in ((1000,camera,radar),(1001,None,None),(1500,None,radar),(2001,None,radar)):
            valid,unavailable=good.step(now,perception=cp,radar=rp),mismatched.step(now,perception=cp,radar=rp)
            self.assertEqual(legacy_product(valid),legacy_product(unavailable))
            self.assertIsNone(unavailable["sources"]["camera"]["distanceClassConfidence"])
            self.assertIsNone(unavailable["sources"]["camera"]["occupancyDecisionConfidence"])
            self.assertEqual(unavailable["sources"]["camera"]["provenance"],camera["provenance"])
            A.validate(unavailable)

    def test_bound_confidence_indexes_selected_label_instead_of_maximum(self):
        with tempfile.TemporaryDirectory() as directory:camera,_=inputs(directory)
        camera["predictedBin"]="bin-0"  # Deliberate TEST-ONLY consumer stimulus, independent of argmax.
        self.assertEqual(A.confidences(camera,threshold=0.5,binding=model_binding()),(0.8,0.05))

    def test_original_f08_typed_contradictions_are_preserved_not_laundered(self):
        with tempfile.TemporaryDirectory() as directory: _,radar=inputs(directory)
        for form in ({"verdict":"pass","failed":["contradiction"]},{"verdict":"fail","failed":[]}):
            checks=copy.deepcopy(radar["checks"]);checks["sensorSelfCheck"]["logical"]=form
            checks["fresh"]=False
            self.assertEqual(A.radar_checks(checks),checks)
        for change in (lambda c:c.update(fresh=1),lambda c:c["sensorSelfCheck"].update(fourth={"verdict":"pass","failed":[]}),
                       lambda c:c["integrity"].update(verdict="unknown")):
            checks=copy.deepcopy(radar["checks"]);change(checks)
            self.assertIsNone(A.radar_checks(checks))

    def test_active_closed_consumers_refuse_legacy_unknown_and_spoofed_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            camera,radar=inputs(directory);out=F.FusionRiskAeb(projection(), model_output_binding=model_binding()).step(1000,perception=camera,radar=radar)
        for interface,producer,consumer in (("proposal-basis","fusion-risk-aeb","proposer"),
            ("adas-cycle","fusion-risk-aeb","vc-ingress"),("adas-cycle","vc-ingress","functional-arbiter"),
            ("adas-cycle","vc-ingress","evidence-validator")):
            binding=C.EndpointBinding(interface,producer,consumer)
            self.assertEqual(binding.consume(out,received_producer=producer),out)
            for schema in (A.HISTORICAL_SCHEMA,"assured-aeb.adas-cycle/3"):
                with self.assertRaises(C.ContractError):binding.consume(dict(out,schema=schema),received_producer=producer)
            with self.assertRaises(C.ContractError):binding.consume(out,received_producer="proposer")
            with self.assertRaises(C.ContractError):binding.consume(dict(out,source="proposer"),received_producer=producer)
        for mutate in (lambda r:r.update(extra=True),lambda r:r["sources"]["camera"].pop("inputQuality"),
                       lambda r:r["sources"]["camera"].update(occupancyDecisionConfidence=True),
                       lambda r:r["sources"]["radar"]["checks"].update(fresh=1)):
            altered=copy.deepcopy(out);mutate(altered)
            with self.assertRaises(ValueError):A.validate(altered)
        with self.assertRaises(C.ContractError):C.EndpointBinding("adas-cycle","proposer","functional-arbiter").consume(out,received_producer="proposer")
        i,p,w=UFixture.roles();self.assertIsNotNone(UFixture.chain(i,p)[1])
        i,p,w=UFixture.roles();basis=UFixture.genuine_basis();basis["schema"]=A.HISTORICAL_SCHEMA
        self.assertIsNone(UFixture.chain(i,p,basis=basis)[1])

    def test_actual_arbiter_rejects_legacy_or_incomplete_metadata_without_upcast(self):
        with tempfile.TemporaryDirectory() as directory:
            camera,radar=inputs(directory);out=F.FusionRiskAeb(projection(), model_output_binding=model_binding()).step(1000,perception=camera,radar=radar)
        for changed in (dict(out,schema=A.HISTORICAL_SCHEMA),dict(out,schema="assured-aeb.adas-cycle/9"),
                        {key:value for key,value in out.items() if key!="sources"}):
            arbiter=V.FunctionalArbiter(projection())
            selector={"schema":V.SELECTOR,"source":"configuration-manager","sequence":1,"originNs":1000,"configuration":"C_NOMINAL"}
            arbiter.step(1000,[("selector-command",selector),("adas-cycle",changed)])
            self.assertIn("request-refused",arbiter.evidence[-1]["flags"])
            self.assertEqual(arbiter.evidence[-1]["kind"],"no-valid-source")
            # Refused envelope never became accepted assurance evidence or consumed a valid request sequence.
            arbiter.step(1001,[("adas-cycle",dict(out,brakeRequest=0.7))])
            self.assertEqual(arbiter.evidence[-1]["kind"],"fresh")
            self.assertEqual(arbiter.evidence[-1]["value"],0.7)

    def test_functional_equivalence_to_prechange_owner_and_metadata_origin(self):
        source=subprocess.check_output(["git","show",BASE+":automotive/assured-aeb/assured_aeb/fusion_aeb.py"],text=True)
        old=types.ModuleType("assured_aeb._wp14b0_prechange_control");old.__package__="assured_aeb"
        exec(compile(source,"pre14b0_fusion.py","exec"),old.__dict__)
        for labels,mismatch in ((LABELS,False),
                (("no-obstacle","overlap","bin-2","bin-0","bin-1","beyond"),False),(LABELS,True)):
            metadata=model_metadata(labels)
            with tempfile.TemporaryDirectory() as directory:camera,radar=inputs(directory,metadata=metadata)
            binding=model_binding(tuple(reversed(labels))) if mismatch else ModelOutputBinding(metadata)
            before,after=old.FusionRiskAeb(projection()),F.FusionRiskAeb(projection(),model_output_binding=binding)
            for now,cp,rp in ((1000,camera,radar),(1001,None,None),(1500,None,radar),(2001,None,radar)):
                old_out,new_out=before.step(now,perception=cp,radar=rp),after.step(now,perception=cp,radar=rp)
                self.assertEqual(legacy_product(new_out),old_out)
                self.assertEqual(new_out["sources"]["camera"]["originNs"],1000)
                A.validate(new_out)

    def test_new_reader_kinds_are_narrow_explicit_and_default_free(self):
        for value in ("a"*64,):
            p=P.Projection(dict(schema=P.PROJECTION,protocolRecordSha256="b"*64,unit="vc-functional",entries={"test.digest":value}))
            self.assertEqual(p.take({"test.digest":("digest",)})["test.digest"],value)
        for value in ("A"*64,"sha256:"+"a"*64,"a"*64+"\n",True,0):
            p=P.Projection(dict(schema=P.PROJECTION,protocolRecordSha256="b"*64,unit="vc-functional",entries={"test.digest":value}))
            with self.assertRaises(ValueError):p.take({"test.digest":("digest",)})
        for value in (-2,-1.5,0,0.5,2):
            p=P.Projection(dict(schema=P.PROJECTION,protocolRecordSha256="b"*64,unit="vc-functional",entries={"test.value":value}))
            self.assertEqual(p.take({"test.value":("finite-number",)})["test.value"],value)
        for value in (True,"1",None,10**1000):
            p=P.Projection(dict(schema=P.PROJECTION,protocolRecordSha256="b"*64,unit="vc-functional",entries={"test.value":value}))
            with self.assertRaises(ValueError):p.take({"test.value":("finite-number",)})
        for value in (float("inf"),float("-inf"),float("nan")):
            with self.assertRaises(ValueError):
                P.Projection(dict(schema=P.PROJECTION,protocolRecordSha256="b"*64,unit="vc-functional",entries={"test.value":value}))
        with self.assertRaises(ValueError):p.take({"test.missing":("finite-number",)})

    def test_schema_documents_match_exact_current_wire_aliases(self):
        root=Path(__file__).resolve().parents[1]/"schemas/roles"
        for interface in ("adas-cycle","proposal-basis"):
            self.assertEqual(json.loads((root/(interface+".schema.json")).read_text()),A.schema_document(interface))
            self.assertEqual(C.URN_TO_SCHEMAS["urn:xverse:assured-aeb:"+interface+":v2"],(A.SCHEMA,))
            self.assertEqual(C.HISTORICAL_WIRE_SCHEMAS[interface],A.HISTORICAL_SCHEMA)
            self.assertNotIn("urn:xverse:assured-aeb:"+interface+":v1",C.URN_TO_SCHEMAS)
            self.assertEqual(C.HISTORICAL_URN_TO_SCHEMAS["urn:xverse:assured-aeb:"+interface+":v1"],(A.HISTORICAL_SCHEMA,))

    def test_generated_topology_advertises_only_the_two_material_payload_versions(self):
        import topology
        base=Path(__file__).resolve().parents[1]
        pins=json.loads((base/"xdl/pins.json").read_text())["artifacts"]
        seen=set()
        for arm in topology.ARMS:
            for form in topology.FORMS:
                for name,document in topology.documents(arm,pins,form=form).items():
                    self.assertEqual(json.loads((base/"xdl"/arm/form/name).read_text()),document)
                    for interface in document.get("spec",{}).get("interfaces",[]):
                        identity=interface["id"]
                        version="v2" if identity in ("adas-cycle","proposal-basis") else "v1"
                        self.assertEqual(interface["payloadSchema"],"urn:xverse:assured-aeb:"+identity+":"+version)
                        policy=interface.get("extensions",{}).get(topology.XCOM,{}).get("policy")
                        if policy and "schemaId" in policy:
                            self.assertEqual(policy["schemaVersion"],"2.0.0" if identity in ("adas-cycle","proposal-basis") else "1.0.0")
                        if version=="v2":seen.add(identity)
        self.assertEqual(seen,{"adas-cycle","proposal-basis"})
