# Synthetic bot-analysis validation

All messages in these fixtures are generated examples, not real conversations. Each was imported, saved, reloaded, and analyzed for the explicitly selected sender.

| Scenario | Selected texts | Possible behavior signals actually observed |
| --- | ---: | --- |
| repeated_scheduled | 20 | Repeated text may reflect automation; Regular timing may reflect scheduling |
| irregular_unique | 20 | None |
| rapid_fragments | 12 | High message burst rate |
| human_routine | 12 | Regular timing may reflect scheduling |
| small_sample | 4 | None |
| missing_timestamps | 12 | None |

The human-routine fixture intentionally triggers regular timing. The rapid-fragment fixture can represent ordinary human conversation. These examples demonstrate why a signal must not be treated as a bot verdict.

Thresholds remain engineering heuristics: at least eight attributed messages; repetition ≥40% and an identical group ≥3; regular timing within one file with positive gaps, mean 5–3600 seconds and CV ≤0.10; burst ≥10 messages within 60 seconds. No classifier accuracy, precision, recall or bot probability has been established.

Missing timestamps prevent timing analysis. Small samples are insufficient. Unknown sender labels and screenshot OCR are not automatically attributed. Separate files are not combined for timing; same-text/same-time cross-file overlaps can undercount legitimate duplicates. Multiple conversations inside a single export can still distort timing.

Absence of configured signals does not establish that an account is human or safe. The application never determines anonymous identity or retrieves private messages.
