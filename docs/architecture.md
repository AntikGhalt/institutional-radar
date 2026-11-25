# Architecture and operating model

The weekly flow and schedule are documented in the README. Sunday IDs identify immutable collection.json files. The reviewer creates a data-only PR; trusted main validates schema, exact collection hash, date window and source domains without executing PR code or merging. The independent auditor checks facts, integrates the validated review, and records audit.json using Git blob hashes. A validated open PR can be used as data when main has no review, but never as audited approval. Missing review produces a raw-candidate workbook and diagnostics; missing audit prohibits verified ICS, not email delivery.

## Modules
- common.py: repository/source configuration, paths, canonical hash and date handling.
- collection.py and calendars.py: bounded public fetches, adapters and immutable snapshots.
- validation.py, accept_review.py and audit.py: shared validation, read-only PR gate and exact-hash approval.
- handoff.py: retrieve validated data and original Claude revision; history.py: compare with last sent nonempty digest; metrics.py: exact-key differences.
- digest.py, rendering.py, spreadsheet.py, calendar_links.py: present HTML, XLSX, CSV and calendar outputs.
- delivery.py: persistent reservation and SMTP; radar.py: CLI/orchestration.

The finalizer renders production output once, persists individual ICS files, digest manifest, metrics and reservation on main, then sends the reserved bytes. The final receipt indicates SMTP accepted, not that the inbox delivered. Test emails and local previews do not write production receipts. The Monday watchdog checks missed workflows and actionable source changes independently; it can propose but not merge a maintenance PR.

Event identity is normalized institution, title and full date. Repeated titles on separate dates get distinct UIDs; an explicitly verified move reuses the previous UID when available. Cancellation requires official evidence. A unique unmatched same-title date change is a hint, excluded from verified ICS until resolved; omissions alone are not cancellations. Calendar imports cannot guarantee updates/deletions in the recipient's client.

Metrics are based on raw Python candidates, original Claude PR content and exact audited final content. The pre-edit PR head in audit.json is preferred. Legacy first-commit comparisons are labelled estimates; unavailable attribution stays null. A rename/date change may appear as removal plus addition. health.json records separate handoff and parser-quality states; only handoff failures count toward critical streaks. No prior record means no evidence of previous consecutive failures.
