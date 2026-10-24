"""WP14b0 stdlib controls. ALL numbers/model outputs/identities are TEST-ONLY.

Real source owners produce every envelope; the inference callable is deterministic/model-free,
not an ORT/calibration-quality claim. Full owning/topology verification is coordinator-scheduled.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import types
import unittest

from assured_aeb import adas_contract as A, camera_chain as CC, camera_inference as CI
from assured_aeb import fusion_aeb as F, parameters as P, radar_zone as R, role_contract as C, vc_functional as V
import test_u4_untrusted as UFixture

BASE = "b21824a06bf1264aefa201001cb73fc7d13087c6"
LABELS = ("no-obstacle", "overlap", "bin-0", "bin-1", "bin-2", "beyond")
PROVENANCE = {"modelDigest": "a"*64, "preprocessParamsSha256": "b"*64, "postprocessSha256": "c"*64}


def projection(threshold=0.5):
    # Explicit TEST-ONLY producer parameters; no protocol defaults or real-data value selection.
    values = {"vehicle.egoFrontM": 2.4, "radar.mountM": [2.0,0.0], "radar.closingSpeedSign": -1,
              "fusion.corridor.halfWidthM": 1.5, "fusion.corridor.maxRangeM": 80.0,
              "fusion.cameraFreshnessNs": 1000, "fusion.radarFreshnessNs": 1000,
              "fusion.occupancyThreshold": threshold, "fusion.distanceBinEdgesM": [10.0,20.0,40.0],
              "fusion.associationToleranceM": 1.0, "aeb.distanceUncertaintyM": 0.5, "aeb.speedUncertaintyMps": 0.5,
              "aeb.latencyNs": 100, "aeb.decelerationMps2": 6.0, "aeb.marginM": 1.0, "aeb.brakeLevel": 1.0,
              "aeb.releaseSpeedMps": 0.5, "aeb.releaseAbsentCycles": 3,
              "arbiter.requestFreshnessNs": 1000, "arbiter.holdWindowNs": 1000, "arbiter.mrcSource": "none"}
    return P.Projection(dict(schema=P.PROJECTION,protocolRecordSha256="d"*64,unit="adas-hpc",entries=values))


def inputs(directory, probability=0.8):
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
    result = {"occupancyProbability":probability,"binProbabilities":[0.05,0.05,0.05,0.05,0.7,0.1],
              "predictedBin":"bin-2","oodScore":0.3,"oodFlag":False}
    with CI.SpoolReader(root) as spool:
        perception = CI.CameraInference(infer=lambda frame:copy.deepcopy(result),frame_length=len(pixels),
            spool=spool,provenance=PROVENANCE,bin_labels=LABELS).step(f07)
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
            out = F.FusionRiskAeb(projection()).step(1000,perception=camera,radar=radar)
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
                out=F.FusionRiskAeb(projection(threshold)).step(1000,perception=camera,radar=radar)
            self.assertEqual(out["sources"]["camera"]["occupancyDecisionConfidence"],expected)
            self.assertEqual(out["sources"]["camera"]["distanceClassConfidence"],0.7)
        self.assertEqual(A.confidences({"occupancyProbability":True},threshold=0.5,bin_labels=LABELS),(None,None))

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
            self.assertIsNone(A.confidences(result,threshold=0.5,bin_labels=LABELS)[1])

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
            camera,radar=inputs(directory);out=F.FusionRiskAeb(projection()).step(1000,perception=camera,radar=radar)
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
            camera,radar=inputs(directory);out=F.FusionRiskAeb(projection()).step(1000,perception=camera,radar=radar)
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
        with tempfile.TemporaryDirectory() as directory:
            camera,radar=inputs(directory)
        before,after=old.FusionRiskAeb(projection()),F.FusionRiskAeb(projection())
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
