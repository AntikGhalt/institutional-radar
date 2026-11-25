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
