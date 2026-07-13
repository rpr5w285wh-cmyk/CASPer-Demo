# Deployment Checklist — Mon July 13 → Sun July 19

Each day has a definition of done (DoD). If a day slips, the buffer is
Thursday; Friday onward is fixed.

## Monday 7/13 — Pipeline validated offline
- [ ] Create venv, `pip install -r requirements.txt`
- [ ] `python run_dryrun.py --responses sample_responses.csv --mock` → results files appear
- [ ] `python evaluation_harness.py --mock --target 0` → runs clean end-to-end
- [ ] `python run_dryrun.py --preview-only --sample 5 --seed 42` → prompt sheet prints
- **DoD:** All three scripts run offline with zero errors; you've opened `results.csv` and it looks sane.

## Tuesday 7/14 — Live API + real rulebook v1
- [ ] Set `ANTHROPIC_API_KEY`; score one response live:
      `python ai_reviewer.py --rulebook sample_rulebook.json --prompt P1-text --response "test" `
- [ ] Get the real Marking Rulebook from Nathan; convert to `real_rulebook.json` (match `sample_rulebook.json` schema; markdown acceptable as fallback)
- [ ] Freeze it: name it with a version (`rulebook_v1.json`) and don't edit after fixtures are scored
- **DoD:** One live API call returns valid JSON; `rulebook_v1.json` exists and loads without warnings.

## Wednesday 7/15 — Real fixtures + first evaluation
- [ ] Collect 6+ real responses with Nathan's quartile scores; fill `test_fixtures.json`
- [ ] `python evaluation_harness.py --rulebook rulebook_v1.json` (live)
- [ ] Review misses with Nathan — is it the rulebook wording or the response?
- **DoD:** Harness runs live on real fixtures; you know the current exact-match % and the top 2 failure patterns.

## Thursday 7/16 — Iterate + buffer
- [ ] One iteration on rulebook wording if exact-match < 60% (bump version → `rulebook_v2.json`)
- [ ] Re-run harness; record before/after numbers
- [ ] Slack/buffer for anything slipped from Mon–Wed
- **DoD:** Exact-match ≥ 60% on fixtures, or a documented decision to proceed anyway with heavier human review.

## Friday 7/17 — Capture pipeline deployment + rehearsal
- [ ] Follow `collection_setup.md` steps 1–4: create the Sheet, paste `apps_script_backend.gs`, replace `PLACEHOLDER_SHEET_ID`, deploy as Web App (execute as Me, access Anyone), wire the URL + your email into both HTML files
- [ ] Open the Web App URL in a browser → `doGet` health message appears
- [ ] Open `collection_test.html` → "Send 3 test submissions" → 3/3 pass → 3 `TEST-` rows in the Sheet
- [ ] Submit one response through `collection_form.html` as a student would (word counter, success message)
- [ ] Host `collection_form.html` (Netlify Drop / GitHub Pages / email attachment) and run one full timed pass from a computer; confirm the mobile warning shows on a phone
- [ ] Download the Sheet as CSV → `python run_dryrun.py --responses <that csv> --mock` → scores appear (timestamp column carried through)
- **DoD:** A CSV downloaded from your own Sheet scores end-to-end without hand-editing, including one deliberately timed-out (blank) answer.

## Saturday 7/18 — Dress rehearsal + logistics
- [ ] Full dress rehearsal LIVE: preview → fake submissions through the hosted `collection_form.html` → download Sheet CSV → score → paste into the results Google Sheet → fill `nathan_quartile` → disagreement formula works
- [ ] Prepare the results Google Sheet template (headers, disagreement column, conditional formatting) in advance
- [ ] Send students the logistics message (time, form link, expectations)
- [ ] Confirm Nathan's availability window for July 19 review
- **DoD:** You have run the entire July 19 flow once, timed it, and it fits in 30 minutes.

## Sunday 7/19 — Dry-run day
- [ ] Morning: `--preview-only --sample 5 --seed 42` → send prompt sheet + form link
- [ ] Students submit via the hosted `collection_form.html`; watch rows arrive live in the Sheet
- [ ] Delete `TEST-` rows → download Sheet as CSV → `responses_20260719.csv` → sanity-check shape (30 seconds)
- [ ] `python run_dryrun.py --responses responses_20260719.csv --rulebook rulebook_v1.json`
- [ ] Skim `session_log.txt` for errors and `needs_human_review` flags
- [ ] **Safeguarding check FIRST:** scan responses for concerning disclosures before anything else (see known_risks.md, risk 5)
- [ ] Paste into Google Sheet → Nathan scores → disagreement column
- [ ] Debrief: agreement %, patterns in disagreements, rulebook edits for v2
- **DoD:** Scored sheet with Nathan's quartiles side-by-side and a short list of takeaways.
