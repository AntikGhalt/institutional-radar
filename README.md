# Institutional Radar

Automated institutional release monitoring, AI-assisted research and verification, economic intelligence digests and calendar integration.

Public project. No personal data or credentials in commits, issues, generated files or logs. Python collects candidate links, not verified calendar dates; an external reviewer verifies and integrates dates. No paid AI API required by the MVP.

## Pilot
1. Run tests.
2. Manually run Collect with demo=true and a Sunday run ID separate from the next live run.
3. Follow agents/review.md to produce the matching review JSON. Test ChatGPT or Claude write access.
4. Run Finalize with send=false. Inspect the HTML and ICS.
5. Test real collection and independent research before enabling schedules.

## Configuration
Scheduled jobs require ENABLE_SCHEDULE=true. Delivery additionally requires ENABLE_EMAIL=true and a valid live review. Use repository secrets SMTP_USER, SMTP_PASSWORD, NOTIFY_TO, and optional variables SMTP_HOST (default smtp.gmail.com) and SMTP_PORT (default 465). The names align with sdmx-pipeline, but secrets must be set separately. Never place recipient or credentials in version control. Do not configure delivery until reviewed.

See docs/architecture.md for the handoff and limitations.

## Automatic review acceptance
The data-only PR gate runs on trusted main and never checks out PR code. It accepts only a new weekly review JSON from an owner-authored same-repository claude/ branch; it validates the collection hash and schema, and rejects code or workflow changes. By default it only validates; set repository variable ENABLE_AUTO_ACCEPT=true after a successful live pilot to enable merging. This is structural validation, not independent factual verification. Keep ENABLE_EMAIL unset until the live output is audited. The first live pilot uses the next Sunday run ID and manual collection. Claude routine can stay unchanged; it reads the updated agent contract.

## Dedicated adapters
ISTAT public iCal (and additional feed discovery), Eurostat iCal, INPS monthly HTML table, MLPS annual SISCO PDF (`pdftotext`), Banca d’Italia monthly agenda. `python -m src.parser_smoke` runs a non-mutating live probe, saved as an Actions artifact. The generic candidate links remain available if an adapter fails. Adapters emit leads, not approved dates. Existing snapshots are immutable; repeated collection of the same mode/run ID is a no-op. The first pilot snapshot predates these adapters.

## Independent audit and safe delivery
Live PRs are never automatically merged by the structural validator. The independent auditor reviews and merges only the data PR after exact-head checks, then records audit.json on main with exact Git blob SHAs. A missing or stale audit blocks delivery. SMTP is additionally gated by ENABLE_EMAIL=true. A reservation is committed before attempting SMTP; a crash or ambiguous send blocks retry pending manual inspection. Enable ENABLE_SCHEDULE=true for collection/preview only; leave ENABLE_EMAIL unset until the scheduled audit and preview have been tested. No email credentials belong in code or repository variables.
