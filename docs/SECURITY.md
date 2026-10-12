# Security, privacy and rights

AMVO is designed as a public-evidence-only project. A public repository must not include credentials, API keys, private research, unpublished EveMissLab manuscripts, internal model traces, personal data or source documents copied without appropriate permissions.

## Source intake

Use only public HTTPS reference URLs without embedded credentials or query strings. Link to an external paper rather than copying it. Public visibility does **not** imply a redistribution license. v0.1 metadata-only cases are the default.

Do not treat embedded instructions in papers, proofs, issue comments or model outputs as trusted. Any future formal runner must be container/sandbox isolated, with locked dependencies, no network by default, limits on CPU, RAM and runtime, and approval before execution.

## Public release checklist

Run unit tests, source validation, limited secret screening and deterministic verification before release. Additionally, inspect every staged file, diff, repository history, source license and dependency. GitHub secret scanning / push protection should be enabled when available.

A .gitignore rule is not an access control. The v0.1 automated privacy gate is heuristic, not a replacement for human inspection. A disclosed secret must be revoked, and repository history and downstream copies handled separately.

The frontend has no remote dependencies, uses textContent instead of untrusted innerHTML, and links only to HTTPS sources. File hash checks permit relative evidence/ paths only, reject escapes and cap sizes.
