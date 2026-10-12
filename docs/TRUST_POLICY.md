# Evidence levels and verdict policy

**Claim scope, evidence scope, and publication scope must never be silently upgraded.**

| Level | Checked | Not implied |
|---|---|---|
| S0 | source identity, author, version, public reference | mathematical truth |
| S1 | artifact SHA-256 identity | mathematical correctness |
| S2 | explicit finite exact computation | general theorem |
| S3 (future) | pinned formal-kernel proof and stated assumptions | semantic alignment |
| S4 (future) | original-language/formal-target mapping | novelty |
| S5 (future) | independent mathematical route, literature and objections | universal consensus |
| S6 (future) | editorial and publication rights review | proof of a stronger theorem |

Executable v0.1 supports S0–S2 only. Reports always include:
- exact record SHA-256 and source version;
- every check type, result and bounded scope;
- formal_kernel = not_run;
- semantic_alignment = not_assessed;
- independent_theorem_review = not_assessed;
- theorem_proved = false.

Terms:
- not_checked — source indexed; no checks completed.
- bounded_checks_pass — all declared finite checks passed; **not** theorem certification.
- checks_not_passed — at least one check failed or could not safely run.

## Corrections and attribution

Preserve source provenance and counter-evidence. Record withdrawals and corrections without silently rewriting history. Distinguish original mathematical discoverer, AI model and human contributors, independent checker, formalizer, reviewer and editor. Access to private results is not a right to claim research priority.

Any formal proof claim needs specific theorem text, pinned checker and dependencies, axiom audits and separate semantic interpretation checks before publication.
