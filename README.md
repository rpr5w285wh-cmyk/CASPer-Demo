# CASPer AI-Reviewer Dry-Run Kit

Self-contained kit for the July 19 dry-run: CSV in, scored quartiles out.
No database, no framework, no cloud transcription. Two dependencies (`anthropic` for scoring, `faster-whisper` for local transcription).

## 30-second install (Windows)

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
set ANTHROPIC_API_KEY=sk-ant-...
```

(macOS/Linux: `source .venv/bin/activate` and `export ANTHROPIC_API_KEY=...`)

**No API key yet?** Everything runs offline with `--mock` (scoring AND
transcription) — validate the whole pipeline first. Live scoring needs
`ANTHROPIC_API_KEY`; transcription is local and needs no key at all
(first-ever run downloads the ~150 MB Whisper model, then it's offline).

## Smoke test (offline, 30 seconds)

```bat
python run_dryrun.py --responses sample_responses.csv --mock
python evaluation_harness.py --mock --target 0
```

You should see `results.csv`, `results.json`, and `session_log.txt` appear.

## July 19 — the 30-minute critical path

1. **Generate the prompt sheet** for the coach to send to students:
   ```bat
   python run_dryrun.py --preview-only --sample 5 --seed 42
   ```
   Copy the printed prompts into the message to students.

2. **Students run `collection_form.html`** — the full Casper format:
   system check, then Section 1 (4 video scenarios; per question a
   10-second countdown and 1 minute of auto-recording, uploaded to your
   Drive folder in the background), optional 10-minute break, then
   Section 2 (7 typed scenarios; 2 questions together, 3:30, auto-submit,
   5-minute break after the 4th). 30-second reflection before every
   scenario; no going back; paste disabled. Setup: `collection_setup.md`;
   verify with `collection_test.html`.

3. **Download the Sheet as CSV and the Drive recordings folder**, then
   fill video transcripts:
   ```bat
   python transcribe.py --responses export.csv --media-dir recordings --out responses_20260719.csv
   ```
   Columns: `timestamp, student_id, prompt_id, question_id,
   response_type, response, video_link` — one row per question. Delete
   `TEST-` rows first. Blank and failed rows are skipped by the scorer
   and noted in `session_log.txt`.

4. **Score everything:**
   ```bat
   python run_dryrun.py --responses responses_20260719.csv
   ```
   Add `--rulebook real_rulebook.json` if the real rulebook has replaced the
   sample. Outputs: `results.csv`, `results.json`, `session_log.txt`.

5. **Human comparison in Google Sheets:** paste `results.csv` into a Sheet.
   Nathan fills a `nathan_quartile` column next to `quartile`. Scoring is
   per question, so a full 11-scenario run is 22 marks per student —
   agree with Nathan on a sample. For video rows Nathan should watch the
   recording via `video_link`; note the AI scores only the transcript,
   so delivery and tone are invisible to it. Label video-row
   disagreements separately in the analysis. Add a
   `disagreement` column:
   ```
   =IF(ABS(D2 - K2) = 0, "", IF(ABS(D2 - K2) = 1, "off-by-1", "MISMATCH"))
   ```
   (adjust column letters), then conditional-format non-blank cells red.

## The three scripts

| Script | What it does |
|---|---|
| `ai_reviewer.py` | Scores ONE response. `python ai_reviewer.py --rulebook sample_rulebook.json --prompt "…" --response "…" [--mock]`. `--prompt`/`--response` accept literal text or a file path. |
| `run_dryrun.py` | Batch scoring from a CSV + prompt-sheet preview mode. Retries API errors once (2s backoff), logs and continues. |
| `evaluation_harness.py` | Runs `test_fixtures.json` through the reviewer; reports exact-match %, off-by-one %, per-quartile recall, avg confidence when wrong. Exits non-zero if exact-match < `--target` (default 60). |

## Swapping in real content

- **Rulebook:** replace `sample_rulebook.json` (preferred) or point `--rulebook`
  at the real file. Keep rule IDs stable (R1, R2, …). Markdown works too.
- **Fixtures:** replace the 6 placeholder rows in `test_fixtures.json` with
  real responses and Nathan's expected quartiles, then run
  `python evaluation_harness.py` (live mode) before the dry-run.
- **Prompts:** edit `sample_prompts.json` (fields: `prompt_id`, `text`
  = scenario, `questions` = exactly 2, `scenario_type`). The reviewer is
  fed the scenario plus the specific question the row answers
  (`question_id` A/B). ⚠️ The scenarios and questions in
  `collection_form.html` are hardcoded from this file — if you change
  prompts, update the form's `SCENARIOS` constant to match. Question
  labels are A/B everywhere; Q1–Q4 always means quartile.

## The collection mechanism (replaces JotForm)

| File | What it does |
|---|---|
| `collection_form.html` | Student-facing timed session mirroring the Casper typed section: fixed 5-scenario sequence, 30-second reflection, 2 questions shown together, 3:30 countdown with auto-submit, paste disabled, drafts auto-saved (refresh-safe — the clock keeps running), failed sends queued with a retry at the end. |
| `apps_script_backend.gs` | Paste-ready Google Apps Script: `doPost` takes one scenario submission and appends one row per question `[timestamp, student_id, prompt_id, question_id, response]` (lock-protected); `doGet` is a browser-openable health check. |
| `collection_test.html` | Internal test page: fires 3 automated `TEST-` scenario submissions (6 rows, one deliberately blank answer) plus a pre-filled manual one, with a pass/fail log. |
| `collection_setup.md` | Deployment guide (~20 min), including the CORS note (`text/plain`, never `application/json`) and the Drive recordings folder. |
| `transcribe.py` | Matches downloaded recordings (`student__prompt__question__ts.webm`) to video rows and fills transcripts using LOCAL Whisper (faster-whisper — no account, recordings stay on your machine); `--mock` skips even that. |

## Flags reference

- `--mock` — deterministic offline scoring (same input → same output)
- `--model` — defaults to `claude-sonnet-4-6`
- `--outdir` — where results files land (default: current folder)
- `needs_human_review` is set automatically when confidence < 0.6

See `deployment_steps.md` for the day-by-day plan and `known_risks.md` for
the failure modes to watch — including the safeguarding SOP for concerning
student disclosures.
