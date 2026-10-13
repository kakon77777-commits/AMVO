# AMVO — AI Mathematics Verification Observatory

**Independent, evidence-first verification of externally published AI mathematics.**

AMVO is an open-source research observatory maintained by EveMissLab. It records public mathematical claims, source versions, bounded checks, verification evidence, corrections, and publication-ready status reports **without claiming authority over the original discovery**.

> A mathematical claim, a passing test, a kernel-checked formal theorem, a faithful translation of the original statement, and independent mathematical acceptance are different things.

## Status

**v0.1.2 foundation** — source intake with declared immutable version pins for mathematical claims, schema validation, deterministic bounded checks, auditable report generation, and a static dashboard. **No OpenAI, AMRAL, or other mathematical research result has been independently certified by this repository.**

## Quick start

Requires Python 3.11+; runtime uses only the Python standard library.

```bash
python -m unittest discover -s tests -v
python -m amvo validate
python -m amvo verify --output build/verification.json
python -m amvo build-site --output site
python -m http.server 8000 --directory site
```

Open http://localhost:8000/ after starting the server.

The included synthetic arithmetic example demonstrates the verifier. The OpenAI public-repository intake is **metadata only** and has **not** been checked or endorsed.

### Source pinning

New records of type `claim` must include `source.pin` (kind: `git_commit`, `arxiv_version`, or `sha256`) with a valid format. **A declared pin is not remotely checked by the offline v0.1.2 engine.** Pin acceptance verifies only data shape; remote provenance replay is a subsequent milestone. Intake-only source records can remain unpinned and must not be presented as verified theorems.

Delivered phases and their evidence are recorded in the [Phase Log](docs/PHASE_LOG.md). For the next iteration, see the [Local Agent Handoff](docs/LOCAL_AGENT_HANDOFF_2026-10-13.md), [Engineering Master Plan](docs/ENGINEERING_MASTER_PLAN_2026-10-13.md), [Acceptance Matrix](docs/ACCEPTANCE_MATRIX_2026-10-13.md), and [Source & Review Contract](docs/SOURCE_AND_REVIEW_CONTRACT_2026-10-13.md).

## Evidence model

| Layer | AMVO meaning |
|---|---|
| Intake | Public origin, author, reference, version and rights recorded |
| Reproducibility | Exact inputs, commands, hashes and observed result |
| Bounded computational check | Only the explicitly checked finite statement |
| Formal kernel validation | The precise theorem as encoded by a proof assistant |
| Semantic alignment | Formal theorem compared with the original research claim |
| Independent mathematical assessment | Scope, dependencies, novelty and unresolved objections reviewed |

**The v0.1 executable currently implements intake, metadata checks, and limited deterministic exact arithmetic.** Higher layers are explicitly *not established*, never inferred from passing local tests.

## Public/private boundary

AMVO must only import **publicly releasable artifacts**. It must not mirror private AMRAL research, unpublished EveMissLab manuscripts, internal prompts, credentials, user data, or model traces. External source papers remain the property of their authors and are linked by URL; redistribution requires a separate license review.

AMRAL (autonomous mathematical research) and AMVO (external verification) are sibling projects with independent repositories and trust boundaries. Model or tool integration may be added later but is not required for this first release.

## Project map

- `amvo/` — offline, deterministic verification engine and CLI
- `cases/` — public claim intake records and synthetic fixtures
- `schemas/` — JSON Schema contract
- `web/` — static dashboard template
- `tests/` — regression and abuse-case coverage
- `docs/` — evidence policy, architecture, security, roadmap
- `.github/workflows/` — CI with read-only permissions

## Principles

1. Verify claims, not personalities or institutional affiliation.
2. Record contrary evidence and corrections; never quietly overwrite history.
3. A successful computation proves only the statement actually computed.
4. Treat external documents and proposed proof scripts as untrusted inputs.
5. Record author attribution and separate authorship, verification, explanation and publication.
6. No default auto-upgrade from `PASS` to “theorem proved.”
7. Do not claim fresh formal proof checking until the kernel is actually run.

## License

AMVO's **original code** is MIT licensed (see `LICENSE`). Third-party papers, proofs, code, illustrations and datasets are **not** automatically covered by that license.

_The project is a verification infrastructure, not an academic journal or a declaration that any Millennium Prize problem has been resolved._
