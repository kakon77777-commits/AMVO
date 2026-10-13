# AMVO — AI Mathematics Verification Observatory

**Independent, evidence-first verification of externally published AI mathematics.**

AMVO is an open-source research observatory maintained by EveMissLab. It records public mathematical claims, source versions, bounded checks, verification evidence, corrections, and publication-ready status reports **without claiming authority over the original discovery**.

> A mathematical claim, a passing test, a kernel-checked formal theorem, a faithful translation of the original statement, and independent mathematical acceptance are different things.

## Status

**v0.1.5 foundation** — a layered registry (source, revision, claim, formal target, evidence, review, publication) with duplicate refusal and a migration from the v0.1 case format, source intake with declared immutable version pins for mathematical claims, opt-in replay of those pins against their public origin, an append-only ledger of withdrawals, replacements, corrections and objections, schema validation, deterministic bounded checks, auditable report generation, and a static dashboard. **No OpenAI, AMRAL, or other mathematical research result has been independently certified by this repository.**

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

The included synthetic arithmetic example demonstrates the verifier. The OpenAI public-repository intake is **metadata only** and has **not** been checked or endorsed. One snapshot record pins a public commit of that repository; replaying the pin confirms which version a later claim would refer to — it says nothing about any mathematics in it.

### Source pinning

New records of type `claim` must include `source.pin` (kind: `git_commit`, `arxiv_version`, or `sha256`) with a valid format. Accepting a record checks only the pin's shape; on its own a pin is reported as `declared_only`. Intake-only source records can remain unpinned and must not be presented as verified theorems.

The network is used only when asked for:

```bash
python -m amvo replay-pins --network --case <record-id>
```

This asks the origin (GitHub's commit API, arXiv's export API, or an allowlisted file host) whether the pinned version exists and matches, and appends one capture — metadata and hashes, never the source text — under `evidence/provenance/<record-id>/`. Only `api.github.com`, `export.arxiv.org` and `raw.githubusercontent.com` are contacted, over HTTPS with no credentials; every resolved address must be public and the connection goes to the address that was checked; redirects are refused and responses are capped at 4 MB. `source_pin_verified` becomes `true` only for a live capture whose observation matches the pin; a fixture replay (`--fixtures DIR`, used by the tests) never counts, and an unreachable origin is `unavailable`, never a pass. A verified pin establishes which public version is meant. It is not evidence that any statement in it is true.

### Layered registry (v0.2)

One paper can state many theorems, lemmas and conjectures, so AMVO files results by layer in `registry/`: Source → SourceRevision → Claim → FormalTarget / Evidence / Review → Publication. Each object refers to the ones below it by id and canonical hash, so evidence cannot rewrite its claim, a review cannot touch its source, and a publication can cite only evidence of its own claims. A claim needs a pinned revision. Duplicates are refused, and `python -m amvo locate --query <url or pin>` says where a result already lives before anything is added. The report (`python -m amvo registry-report`) counts sources, claims and checked claims separately and gives each claim statuses such as `NOT_CHECKED`, `BOUNDED_PASS`, `REPRODUCIBILITY_ONLY`, `SEMANTIC_ALIGNMENT_PENDING`, `OBJECTION_OPEN` or `WITHDRAWN` — never "verified". The v0.1 case files are kept unchanged and mapped by `python -m amvo migrate`. See [registry/README.md](registry/README.md).

### Corrections and withdrawals

A record is never edited to say it was withdrawn, replaced, corrected or disputed. `python -m amvo record-event` appends an event to `events/` instead (`withdraws`, `supersedes`, `corrects`, `rebuttal`). Each event is bound to the hash of the record it names and to the hash of the event before it, so a quietly edited record or a rewritten event makes every command fail, and CI refuses a pull request that changes or deletes a ledger file. The report keeps each record's computed outcome and shows its lineage beside it; the dashboard never counts a withdrawn or superseded record as a current result. See [events/README.md](events/README.md).

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

- `amvo/` — deterministic verification engine and CLI (offline unless `replay-pins --network`)
- `cases/` — public claim intake records and synthetic fixtures
- `evidence/provenance/` — append-only pin replay captures
- `events/` — append-only correction and withdrawal ledger
- `registry/` — layered v0.2 objects and migration manifests
- `schemas/` — JSON Schema contracts (v0.1 records, events, v0.2 registry)
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
