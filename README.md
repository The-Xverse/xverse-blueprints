# xverse-blueprints

X-Verse vNext is a multi-industry cyber-physical systems experimentation platform under development.

Owns reproducible domain/use-case experiments. Automotive and research behavior belong here or in profiles, never in the platform core. No executable blueprint is implemented in M0.

## Current maturity
This repository contains engineering setup and M0 discovery documentation. Runtime capabilities,
XDL, compatibility wrappers, and executable blueprints are architectural targets, not implemented
features. Legacy capabilities documented by M0 have not been executed or certified by this work.

## Engineering workflow
Spec Kit **0.14.0** is initialized with its official generic integration, Bash scripts, templates,
and bundled workflow. The generic integration uses `.specify/commands` because this workspace's
`.agents` and `.codex` directories are read-only. No permissions or agent directories were changed.

Read [engineering rules](AGENTS.md) and the [constitution](.specify/memory/constitution.md).
Ask the agent to read and follow `.specify/commands/speckit.<stage>.md`, supplying the feature
request as its input. Stages: constitution, specify, clarify, plan, tasks, analyze, implement.
Follow implementation with a separate architecture review. These Markdown commands are not shell
executables; slash-command discovery is not assumed for the generic integration.

The [M0 feature](../xverse-platform/specs/001-legacy-repository-inventory/spec.md) and its tasks live only in
xverse-platform. Run M0 prerequisite and evidence checks from that repository; companion
repositories intentionally have no active feature pointer until their own first capability.
See the [M0 quickstart](../xverse-platform/specs/001-legacy-repository-inventory/quickstart.md).

## Architecture and review gates
Dependencies flow from blueprints through domain profiles and XDL/platform APIs to runtime
abstractions. Existing production repositories remain read-only. Features must pass architecture,
compatibility, runtime (when applicable), test, reproducibility, and documentation gates.

Platform [ADR-0018](../xverse-platform/docs/adr/ADR-0018-platform-first-delivery-sequence.md) now
requires the main platform capability baselines and stable extension contracts before target-specific
legacy integration and parity work resume. Blueprint capabilities will consume accepted platform
contracts without introducing reverse dependencies.
The platform [SADS traceability register](../xverse-platform/docs/architecture/SADS_REQUIREMENTS_TRACEABILITY.md)
allocates all requirements from the supplied architecture reference; blueprint features retain the
applicable IDs without treating target requirements as implementation evidence.

See [architecture guidance](../xverse-platform/docs/architecture/XVERSE_VNEXT_ARCHITECTURE_AND_CODEX_GUIDANCE.md)
and the [legacy inventory](../xverse-platform/docs/legacy/REPOSITORY_INVENTORY.md). Relative cross-repository
links assume sibling checkouts with their repository names, as in this workspace.

M0 documents are intended for public-safe review. Referenced private GitHub evidence requires
existing repository access. Review of inventory boundaries, classifications, interfaces, and
dependencies is required before M1. Changes from this delivery remain local and unpublished.

## License
See [LICENSE](LICENSE); the existing license is unchanged.

## M0 review status

The user confirmed the cross-repository M0 review on 2026-09-20. See the
[decision record](../xverse-platform/docs/reviews/M0_REVIEW_CHECKLIST.md) and
[supplemental references](../xverse-platform/docs/architecture/REFERENCE_REGISTER.md).
M1 specification/design can begin; no additional runtime capability is implemented by this confirmation.
