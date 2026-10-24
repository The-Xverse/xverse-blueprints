# Runtime parameter projections (WP-17b)

`projection_builder.build` is an offline full-record consumer. It requires an admitted protocol object, exact reviewed
table bytes and SHA-256, and the expected role-to-unit inventory from the reviewed runtime plan. Its outputs union
only each unit's own role entries. Oracle/scenario/fault/metric categories and controlled forbidden namespaces are
refused. This mechanical check does not approve arbitrary membership or infer the meaning of a mislabeled parameter.
The actual table is fixed with AD-27; none is authored here.

`runtime_projection.verified_projection` imports only the standard library. A unit supplies its admitted file digest,
protocol digest, own unit id and exact own consumed identifier set. Missing/extra values, foreign unit/protocol,
changed bytes and ambiguous/non-finite JSON are refused. It returns the existing closed WP-13 projection record;
typed value/range validation remains with the role's parameter declarations. It receives no full record or table.

`write_bundle(directory, outputs, receipt, *, expected_table_sha256, protocol_record_sha256)` requires both
independent admitted pins, with no defaults. It validates the closed `projection-pins.schema.json` receipt contract,
compares its table/protocol digests with those pins, and checks every decoded file's schema, unit, protocol digest,
byte hash and exact identifier set before creating a directory. The receipt's own claims cannot authenticate the
reviewed table; admitted pins come from the owner's verified inputs, not a runtime message or a mutated receipt.

The helper snapshots immutable output bytes and canonical receipt bytes, then writes one file per unit to a fresh
directory and the checked receipt last. It never overwrites an existing bundle. The unit name `projection-pins` is
reserved for the receipt filename and refused before publication (also by the builder/table schema). A later I/O
failure leaves an unaccepted partial artifact for diagnosis; no durability, execution or scientific authority follows
from a file or receipt alone. The owner delivers each runtime unit only its own file and admitted pin, outside the
full record/table/evidence working directory.

Full V21 requires the unit wiring audit of argv, environment, working directory, inbound flows and parameter
provenance. A successful file-generation or import test does not establish that composition boundary.
