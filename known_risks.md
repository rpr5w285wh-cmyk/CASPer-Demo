# Known Risks — CASPer AI-Reviewer Dry-Run

## 1. Rulebook version drift
- **Trigger:** Rulebook edited after fixtures were scored, or Nathan reviews against a different version than the AI used. Scores stop being comparable; "disagreements" are actually version mismatches.
- **Mitigation:** Version the file name (`rulebook_v1.json`, `rulebook_v2.json`) and never edit in place. Freeze the version by Thursday 7/16. `session_log.txt` records each run; note the rulebook filename in the Google Sheet header. If the rulebook changes, re-run the harness before trusting new scores.

## 2. AI-vs-human disagreement > 40%
- **Trigger:** On July 19, more than 40% of rows differ from Nathan by ≥1 quartile (i.e., exact-match < 60%), or any 2-quartile misses cluster on one rule.
- **Mitigation:** This is a *finding*, not a failure — the dry-run's purpose is to measure it. Pre-commit to the response: (a) treat AI scores as draft-only, Nathan's are authoritative; (b) categorize each disagreement (rulebook wording vs. genuine judgment gap vs. parse issue) using the `rationale` and `rule_ids_cited` columns; (c) feed patterns into rulebook v2. Catch it early by running `evaluation_harness.py` on real fixtures Wednesday, not discovering it Sunday.

## 3. Collection pipeline failure (form → Apps Script → Sheet)
- **Trigger:** Students hit the form's error message on run day. Usual causes: `PLACEHOLDER_APPS_SCRIPT_URL` never replaced; script edited but not re-deployed as a **new version** (the live URL keeps serving the old code); deployment access not set to "Anyone"; or the POST content type changed to `application/json` (breaks in-browser because Apps Script doesn't answer CORS preflight — it must stay `text/plain`).
- **Mitigation:** Full rehearsal Friday 7/17 with `collection_test.html` (3 automated submissions + Sheet check) — never first-touch the pipe on run day. The Sheet fills live, so on July 19 watch rows arrive as students submit; silence = problem, caught in minutes. Built-in fallback: the form's error message tells students to email their response to Michael, so no response is ever lost — paste stragglers into the Sheet manually. The downloaded CSV is one-row-per-prompt by construction, and `run_dryrun.py` still fails fast with a column-name error if anything is off. Remember to delete `TEST-` rows before scoring.

## 4. API rate limits / API failures mid-run
- **Trigger:** 429s or 5xx errors during the batch run; symptoms: `RETRY` then `ERROR` lines in `session_log.txt`, blank quartiles in `results.csv`.
- **Mitigation:** Volume is small (a class × 5 prompts), so limits are unlikely but possible on a new key. Built-in: one retry with 2s backoff per row; failures are logged and the run continues. Recovery: filter `results.csv` for `error` rows, save them as a new CSV, re-run just those. Verify the API key works Tuesday, not Sunday. Fall back to `--mock` only to test plumbing, never for real scores.

## 5. Safeguarding disclosures in student responses
- **Trigger:** A student response contains indications of self-harm, abuse, or risk to themselves or others — possible in judgment-scenario answers even when the prompt doesn't invite it.
- **Mitigation — escalation SOP (agree on this BEFORE July 19):**
  1. **A named human reads every response before/alongside AI scoring** on run day — the AI reviewer is not a safeguarding filter and must not be relied on to catch disclosures.
  2. If a concerning disclosure appears: **stop treating it as test data.** Do not paste it into the shared Google Sheet.
  3. Escalate the same day to the designated safeguarding lead (agree who this is in advance — coach, program director) following the organization's existing duty-of-care process for minors/students.
  4. Document what was seen, when, and who was notified; keep it out of the results files.
  5. The student's scoring row can be marked `needs_human_review` and excluded from agreement stats.
- **Note:** decide in advance whether students are minors and what the legal reporting obligations are in your jurisdiction — this shapes step 3.

## 6. Video upload size and quota
- **Trigger:** Recordings fail to upload on slow connections, or Apps Script rejects large payloads. A 1-minute recording at the form's constrained bitrate is ~7 MB (~9 MB as base64); Apps Script POST bodies cap at 50 MB, so single recordings are safe, but a slow uplink can leave several uploads queued at test end.
- **Mitigation:** Uploads run in the background and never block the test; unsent recordings persist in the browser (IndexedDB) with a retry button on the final screen and are flushed again during break screens. The end screen tells students to keep the tab open until the count clears. Drive quota: 8 recordings × ~7 MB × class size — trivial for a cohort, but delete old sessions periodically. If a student's uploads all fail, their videos exist only in their browser: have them retry from the same browser, or fall back to re-recording the failed questions in a fresh session.

## 7. Transcript-only AI scoring of video responses
- **Trigger:** Systematic AI-vs-Nathan disagreement concentrated on video rows.
- **Mitigation:** Expected, not a bug — the AI sees the Whisper transcript; Nathan sees delivery, tone, and composure via the Drive link. Tag video rows separately in the disagreement analysis and set expectations with Nathan before he marks. Whisper also occasionally mis-hears words; when a rationale seems to misread a response, check the recording before blaming the rulebook.
