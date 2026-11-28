# Date sweep — the suite at simulated dates, before and after the test corrections

Made 2026-11-28 with `m8/tools/fakedate_plugin.py` (the Python clock shifted; the database's own clock is not). Full data: `date-sweep.json`.

`tests/test_docling_integration.py::test_docling_extract_smoke` fails under the plugin at every date, the control included — an artefact of the plugin (pandas' compiled date code rejects the substituted class). It passes without the plugin and is left out of the counts below.

## Before — `cca3e0d`

| Simulated date and time | Failed (artefact excluded) | pytest summary |
|---|---|---|
| 2026-09-16T18:30:00+05:30 | 0 | 1 failed, 4425 passed, 177 skipped, 19 warnings |
| 2026-11-30T18:30:00+05:30 | 5 | 6 failed, 4420 passed, 177 skipped, 19 warnings |
| 2026-12-06T18:30:00+05:30 | 13 | 14 failed, 4412 passed, 177 skipped, 19 warnings |
| 2026-12-31T18:30:00+05:30 | 18 | 19 failed, 4407 passed, 177 skipped, 19 warnings |
| 2027-01-01T18:30:00+05:30 | 13 | 14 failed, 4411 passed, 178 skipped, 19 warnings |
| 2027-02-28T18:30:00+05:30 | 18 | 19 failed, 4407 passed, 177 skipped, 19 warnings |
| 2027-03-01T02:00:00+05:30 | 13 | 14 failed, 4411 passed, 178 skipped, 19 warnings |
| 2027-06-15T18:30:00+05:30 | 14 | 15 failed, 4411 passed, 177 skipped, 19 warnings |
| 2028-02-29T18:30:00+05:30 | 21 | 22 failed, 4404 passed, 177 skipped, 19 warnings |

| Test | Fails at |
|---|---|
| `tests/test_account_family.py::test_f01_profile_cards_by_state[expired]` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_account_family.py::test_f03_settings_identity_and_auto_plan_by_tier[expired-False]` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_account_family.py::test_f03_settings_identity_and_auto_plan_by_tier[expired-True]` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_admin_users.py::test_grant_creates_row_and_audit_atomically` | 2027-06-15, 2028-02-29 |
| `tests/test_browse_laws_family.py::test_f03_banner_slot_by_viewer` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_calendar_family.py::test_f03_markers_by_state[expired-choices]` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_calendar_family.py::test_f03_markers_by_state[expired-monthly]` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_calendar_family.py::test_f04_create_entry_points_follow_the_capability[expired-choices-False]` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_calendar_family.py::test_f04_create_entry_points_follow_the_capability[expired-choices-True]` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_entitlement_m3a.py::test_legacy_active_is_not_a_playground_tier` | 2028-02-29 |
| `tests/test_entitlement_m3b.py::test_legacy_active_gets_subscribe_gate_not_a_tier` | 2028-02-29 |
| `tests/test_expired_calendar_screen9.py::test_expired_calendar_canonical_month_uses_live_state` | 2026-11-30, 2026-12-31, 2027-02-28, 2028-02-29 |
| `tests/test_halted_calendar_screen9.py::test_halted_calendar_canonical_month_uses_live_state` | 2026-11-30, 2026-12-31, 2027-02-28, 2028-02-29 |
| `tests/test_phone_expired_calendar_screen5.py::test_phone_expired_calendar_mixed_due_today_keeps_constitution_today_card` | 2026-11-30, 2026-12-31, 2027-02-28, 2028-02-29 |
| `tests/test_phone_halted_calendar_screen5.py::test_guest_free_plus_pro_expired_calendar_are_not_halted_phone_05` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_phone_plus_calendar_screen5.py::test_phone_plus_calendar_mixed_due_today_keeps_constitution_today_card` | 2026-11-30, 2026-12-31, 2027-02-28, 2028-02-29 |
| `tests/test_phone_plus_calendar_screen5.py::test_phone_plus_calendar_overdue_done_and_future_constitution` | 2026-11-30, 2026-12-31, 2027-02-28, 2028-02-29 |
| `tests/test_playground_family.py::test_f05_home_markers_by_state[expired-choices]` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_playground_family.py::test_f05_home_markers_by_state[expired-monthly]` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_playground_family.py::test_f05_read_only_homes_change_only_their_month_phrases_under_choices[expired]` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |
| `tests/test_today_family.py::test_f02_signed_in_first_run_per_tier[expired]` | 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15, 2028-02-29 |

## After — `0f36525` (full suite)

| Simulated date and time | Failed (artefact excluded) | pytest summary |
|---|---|---|
| 2026-11-30T18:30:00+05:30 | 0 | 1 failed, 4425 passed, 177 skipped, 19 warnings |
| 2026-12-06T18:30:00+05:30 | 0 | 1 failed, 4425 passed, 177 skipped, 19 warnings |
| 2026-12-31T18:30:00+05:30 | 0 | 1 failed, 4425 passed, 177 skipped, 19 warnings |
| 2027-03-01T02:00:00+05:30 | 0 | 1 failed, 4424 passed, 178 skipped, 19 warnings |
| 2028-02-29T18:30:00+05:30 | 0 | 1 failed, 4425 passed, 177 skipped, 19 warnings |

The fifteen affected modules were also run at 2026-11-30, 2026-12-06, 2026-12-31, 2027-01-01, 2027-02-28, 2027-03-01 02:00, 2027-06-15 and 2028-02-29 on the corrected working tree (`after_affected_modules` in the JSON). That run still showed the two desktop Calendar tests failing on a month's last day; they were corrected afterwards and are covered by the full-suite runs above and by a run of their two modules at 2026-11-29, 2026-11-30, 2026-12-31, 2027-01-01, 2027-02-28 and 2028-02-29 (19 passed, 6 skipped at each).

On the first day of a month one more test skips itself (`tests/test_calendar_family.py`: "needs a past day in the current month"); that is an existing conditional skip, not a failure.

**What this does not show.** Dates other than these; times of day other than 18:30 and 02:00 IST; a machine in another zone (CI runs in UTC); anything the database's own clock decides.
