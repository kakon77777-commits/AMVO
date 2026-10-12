# AMVO architecture v0.1

AMVO = **AI Mathematics Verification Observatory**. It is not a journal and does not replace independent peer review.

AMRAL is a separate autonomous mathematical research initiative. AMVO must not directly mount AMRAL private storage. OCME, SREG and ISQL may supply public tools or interfaces later, but v0.1 is not coupled to any of them.

## Execution

Public intake files in cases/
-> schema and attribution checks
-> deterministic finite verifier
-> signed-by-content reproducibility report (case SHA-256)
-> static JSON and HTML dashboard.

The first version is **offline** and runs only Python standard-library code. It never downloads papers, invokes proprietary models, runs downloaded proof scripts, or claims Lean kernel verification.

## Data objects

- Source: public URL, author, publisher, original title, version and capture date.
- Claim: natural-language statement and precisely bounded scope.
- Rights: metadata-only or human-reviewed clearance to reproduce content.
- Review: intake workflow status; never a proof result.
- Checks: precisely defined computational identities and artifact integrity.
- Report: outcome and scope of each check plus theorem-status disclaimers.

## Trust boundaries

A schema-valid claim is not a mathematical result. A correct checksum is not proof validity. A bounded exact identity does not establish a theorem beyond that identity. A future Lean kernel result would certify the particular theorem encoded, not automatically its translation, novelty or scope.

## Determinism

Verification outputs exclude execution timestamps and encode canonical sorted UTF-8 JSON. Identical inputs produce byte-identical reports.

## Future integrations (not implemented)

- version-pinned source intake and correction history;
- isolated Lean/Coq runners with explicit allowlist, no outbound network and resource limits;
- natural-language-to-formal alignment review;
- independent mathematical replication and conflict disclosures;
- public, export-only sister-project interoperability;
- AI-assisted editorial publication with separate fact and rights review.
