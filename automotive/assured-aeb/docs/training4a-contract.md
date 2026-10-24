# Training4a admission API (candidate)

This offline-only increment admits immutable metadata and verifies bounded stored frames. It creates no trained
model, tensor, fitted temperature, threshold, export, frozen metadata or candidate publication. All real numeric
protocol values remain TODO. The small example producer in `tests/training4a_fixture.py` is entirely TEST-ONLY.
Use accepted `review-wp09-training-pipeline.md` for the full 4a–4e design and `review-wp09-training4a.md` for scope,
design checkpoints, checks actually performed and pending gates.

Call `TrainingJob.from_bytes(data, max_record_bytes=...)` and `SourceLocations.from_bytes(data,
max_record_bytes=...)` with explicit positive engineering caps and canonical UTF-8 JSON bytes. Canonical means
Python JSON sorted keys, compact separators, ASCII escapes and no trailing newline. Duplicate keys, unsafe
numbers, unknown/missing members and unsupported methods are refused. `record()` returns a private copy;
job `sha256`, `class_order`, `input_shape`, `frame_bytes` and `parameter_count` are read-only scalar/tuple properties.
The job binds the running named closure of training_record/training_io/dataset_consumer, not an arbitrary source
label. A code change requires a new job closure digest.

The job root is exactly `schema, identity, dataset, separation, trainingPartition, preprocessing, architecture,
optimisation, calibrationFit, oodFit, verification, environments`, with schema `assured-aeb.training-job/1`.
Exact nested member sets are:

| Record | Members |
| --- | --- |
| identity | candidateId, purpose, codeClosureSha256, inputRecordsSha256 |
| dataset | manifestSha256, sourceIndexSha256, labelParams, labelParamsSha256, frameFormat, frameFormatSha256 |
| separation | record, sha256 |
| separation.record | schema, categories, evaluationSections |
| separation.record.categories | characterisation, training, calibration, pilot, evaluation |
| trainingPartition | fit, selection |
| preprocessing | record, sha256, codeSha256, numpyVersion |
| architecture | inputName, occupancyOutput, binOutput, convBlocks, occupancyBias, binBias, initialization |
| architecture.convBlocks[] | outChannels, kernel, stride, padding, dilation, bias |
| architecture.initialization | method, low, high |
| optimisation | method, epochs, batchSize, learningRate, momentum, dampening, weightDecay, nesterov, lossWeights, device, numWorkers, intraOpThreads, interOpThreads, seeds, deterministicAlgorithms, selection |
| optimisation.lossWeights | occupancy, bins |
| optimisation.seeds | torch, numpy, dataOrder, initialization |
| optimisation.selection | epochs, method, weighting |
| calibrationFit | method, status, reference, occupancyTemperatures, binTemperatures, population, weighting, ties |
| oodFit | method, fitRule, status, reference, quantile, population, comparison |
| verification | rawLogits, calibratedProbabilities, minimumDecisionAgreement, exactRepeatCount, sampleSelection, independentReference, coverage, metricAcceptance, occupancyThreshold |
| verification.rawLogits / calibratedProbabilities | absolute, relative |
| verification.independentReference | method, maximumSamples |
| verification.coverage | fit, selection, calibration, test |
| verification.coverage.<partition> | classes, targetAbsentMin, adjacentNegativeMin |
| verification.coverage.<partition>.classes | exactly the derived class names |
| verification.metricAcceptance | occupancyNllMax, binNllMax, occupancyBrierMax, binBrierMax, oodFalseAlarmMax |
| verification.occupancyThreshold | value, reference, comparison |
| environments | training, u4, limits |
| environments.training / u4 | identitySha256, lockSha256, sourceRevision, python, sites |
| environments.limits | recordBytes, sourceBytes, compressedFrameBytes, rawFrameBytes, samples, modelParameters, tensorElements, epochs, batchSize, memoryBytes, diskBytes, outputBytes, workerTimeoutS |

`identity.inputRecordsSha256` hashes the canonical object containing only dataset/separation/preprocessing.
Other record identities use SHA256 of canonical JSON; observer/run-parameter/scenario identities hash their actual
file bytes, while label-list and manifest identities retain the owning canonical-list/manifest contracts.
Label parameters use the exact current `LabelParams` record; frame format is exactly schema/width/height/encoding,
BGRA8; separation record schema is `assured-aeb.training-separation/1`. Preprocessing is the existing shared compat
record and actual source binding, called with the explicit expected numpy version to avoid importing numpy.
That expected version and environment identity/lock digests are declarations here; 4b–4e must verify the genuine
environment/interpreter/framework bindings. 4a does not open an interpreter or attest an environment tree.

Supported methods are purpose synthetic-verification/development-training; uniform initialization; CPU SGD,
zero workers and deterministicAlgorithms=true; checkpoint minimum-selection-loss-earliest-epoch with equal-examples;
temperature-grid-nll with delegated-design status/reference, calibration population, equal-examples and
smallest-temperature ties; max-probability/nearest-rank OOD with delegated-design status/reference, calibration
population and strict-greater comparison; all-admitted verification, scalar-and-direct-numpy independent reference,
and greater-or-equal occupancy comparison. Other values and method-specific extras are refused. All sizes/rates/
weights/grids/q/tolerances/coverage are explicit validated inputs; no calibration or metric is computed here.
Five P-4 lists and selection epochs are sorted unique; seed representations are uint32. Float arithmetic inputs
must be finite/representable; initialization bounds must also fit float32. Parameter/positive convolution sizes,
activation bounds and training-update count are derived, not independently adjustable values.

Source locations have schema `assured-aeb.training-source-locations/1` and exact members
`schema, manifest, labelParams, frameFormat, separation, sourceIndex, runs`. Top-level source fields are absolute
file paths. `runs` maps exactly the manifest run IDs to `scenario, labels, observer, runParams, store` absolute
locators. Source index has schema `assured-aeb.training-source-index/1` and exact `schema, runs`; each run is exactly
`runId, scenarioSha256, labelsSha256, observerSha256, runParamsSha256, exclusions`. Exclusions are supplied nonempty
reason strings to nonnegative integer counts. They are retained as supplied, never inferred from unlabelled counts.
No path is treated as an identity or embedded into model metadata by 4a.

`admit_dataset(job, locations)` checks actual bounded source bytes, private labels, observer line/frame/time,
P-4 and seed-disjoint run partitions, genuine manifest /3 rules and explicit coverage. It then streams a bounded
verification pass over every labelled stored frame without retaining raw corpus bytes. The existing owner manifest
validator receives byte-identical temporary scenario snapshots to keep its unbounded path reopen away from mutable
sources; the temporary directory is removed automatically. Original files/stores are never written or swept.
An unlabelled stored frame is excluded and counted, never assigned a negative label. Every fit/selection/calibration/
test partition must contain admitted labels. Canonical traversal/order and the final short batch determine the
reported number of future fit updates; no optimizer has run.

The result provides `report()` (private JSON-safe copy) and `iter_samples(partition)`. The iterator accepts only
fit/selection/calibration/test, rereads/verifies one frame at a time and yields runId/frame/raw bytes/private label/
occupancyTarget/binIndex. Each file must be a bounded regular file, one complete zlib stream with no trailing or
concatenated payload, exact BGRA byte length and matching digest. Store roots/shards/final files cannot be symlinks;
the reader never creates directories or sweeps writer temporaries. Files changed after admission are checked again.

The report binds job/manifest/source-index/separation digests, class order, per-run/partition class and negative
counts, unlabelled counts, supplied recorder exclusions, future training-update count and owner manifest reports.
It records no pixels, source paths or invented exclusion reason. Byte pins and consumed-label coherence cannot
prove recorder#6 world-map/source/traversal truth or replay planar geometry. Shared non-evaluation sections stay
reported as limited independence. Framework/process memory/isolation, 4b–4e actual execution, #5 corruption work,
#7 real-model quality and AD-27 scientific freeze remain separate gates. No engineering admission grants those.
