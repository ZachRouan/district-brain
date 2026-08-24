# Security Policy

District Brain exists to keep a school district's documents inside the district and to
show each person only what their role entitles them to. A bug in that boundary matters
more than any other bug in this project.

## Reporting a vulnerability

Please **do not open a public issue** for anything that could let a user see a document,
chunk, original file, or audit entry outside their scope, or that weakens the tier
discipline (student data must never enter this system before Tier 3 is approved).

Report it privately through GitHub's **Security → Report a vulnerability** form on this
repository. Include the steps to reproduce against the synthetic demo corpus
(`manage.py seed_demo`). Never include real district documents, real student data, or
real audit logs in a report.

You will get an acknowledgement within a few days. Fixes ship with a regression test in
`tests/`, and the finding is recorded in `docs/security-hardening-tier1.md` (or its
successor) once resolved.

## Scope

In scope: anything under this repository — retrieval scoping (`chat/retrieval.py`), the
download view, the admin console, ingestion of untrusted documents, the audit log and its
export, the LLM prompt assembly, and the deployment guidance in `docs/runbook.md`.

Out of scope: vulnerabilities in third-party components (Django, pgvector, llama.cpp,
sentence-transformers) — report those upstream — and issues that require an already
compromised superuser or database.

## Supported versions

The `main` branch. There are no release branches yet; deploy from `main` and pull fixes
by fast-forwarding.
