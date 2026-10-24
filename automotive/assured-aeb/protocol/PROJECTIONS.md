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

`write_bundle` writes one file per unit to a fresh directory and its hash receipt last. It never overwrites an
existing bundle. A failed write leaves a partial artifact for diagnosis; a file or receipt alone grants no execution
or scientific authority. The owner delivers each runtime unit only its own file and admitted pin, outside the full
record/table/evidence working directory.

Full V21 requires the unit wiring audit of argv, environment, working directory, inbound flows and parameter
provenance. A successful file-generation or import test does not establish that composition boundary.
