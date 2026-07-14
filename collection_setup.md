# Collection Setup — Form → Apps Script → Google Sheet

Replaces JotForm entirely. Total setup time: ~15 minutes. Do this by
**Friday 7/17** so the rehearsal uses the real pipe.

## 1. Create the Sheet

1. Create a fresh Google Sheet named e.g. `CASPer Dry-Run Responses`.
2. Leave it empty — the backend writes the header row automatically on the
   first submission: `timestamp`, `student_id`, `prompt_id`, `question_id`,
   `response_type`, `response`, `video_link`, `mock`. Each scenario
   submission produces TWO rows (question A and question B).

   > ⚠️ **Create the Sheet fresh AFTER deploying this backend version.**
   > This version added the `mock` column. If a Sheet already exists with
   > the old 7-column header, recreate it (or archive the tab and start a
   > new one) — appending 8-column rows under a 7-column header silently
   > misaligns the data.
3. Copy the Sheet ID from the URL — the long string between `/d/` and `/edit`:
   `https://docs.google.com/spreadsheets/d/`**`THIS_PART`**`/edit`

## 1b. Create the recordings folder (video)

1. Create a folder in Google Drive, e.g. `CASPer Recordings`.
2. Copy its ID from the URL (`https://drive.google.com/drive/folders/`**`THIS_PART`**).
3. Keep it private — recordings of students are sensitive; do not turn on
   link sharing.

## 2. Install the backend

1. In that Sheet: **Extensions → Apps Script**.
2. Delete any starter code; paste the full contents of `apps_script_backend.gs`.
3. Replace `PLACEHOLDER_SHEET_ID` (step 1) and `PLACEHOLDER_FOLDER_ID` (step 1b).
4. Save (Ctrl+S / ⌘S).

## 3. Deploy as a Web App

1. **Deploy → New deployment**.
2. Gear icon → type **Web app**.
3. *Execute as:* **Me**. *Who has access:* **Anyone**.
4. **Deploy**, authorize when prompted — it now needs Sheets AND Drive
   access (for saving recordings). If you deployed an earlier version,
   Google will re-prompt for the Drive scope on the new deployment.
   Copy the Web App URL (`https://script.google.com/macros/s/…/exec`).

> ⚠️ If you later edit the script, you must **Deploy → Manage deployments →
> Edit → New version** — saving alone does not update the live URL.

## 4. Wire up the form

1. Open `collection_form.html` in a text editor.
2. Replace `PLACEHOLDER_APPS_SCRIPT_URL` with the Web App URL.
3. Replace `PLACEHOLDER_MICHAEL_EMAIL` with your email (shown to students
   if a submission fails).
4. Make the same two replacements in `collection_test.html`.

> ⚠️ Do not change the form's `Content-Type: text/plain` header to
> `application/json`. Apps Script web apps don't answer CORS preflight
> (OPTIONS) requests, so a JSON content type makes every browser submission
> fail. The plain-text body still carries JSON and the backend parses it.

## 5. Host the form

Any static option works — the POST is cross-origin-friendly as deployed:

- **Netlify Drop** (fastest): drag `collection_form.html` onto
  https://app.netlify.com/drop → share the URL.
- **GitHub Pages:** commit it to a repo with Pages enabled.
- **Email attachment:** students save the file and open it locally
  (double-click). The POST works from a `file://` page too.

## 5b. Link formats (for whoever sends the links)

Students are identified by the email they enter on the intro screen
(`student_id` = trimmed, lowercased email). The URL can prefill it so a
typo can't break the linkage:

| Link | Behaviour |
|---|---|
| `…/collection_form.html` | Plain student link. Email required before the test can start. |
| `…/collection_form.html?sid=jane%40example.com&mock=1` | **Preferred per-student link.** Prefills the email (still editable) and tags every row and recording with `mock=1`. Send `mock=2` links for the second sitting — same email, repeat submissions are always appended, never blocked. |
| `…/collection_form.html?review=1` | Reviewer link: real timings, extra skip buttons, email optional. |
| `…/collection_form.html?demo=1` | 2-minute walkthrough: short timers, 1 video + 1 typed scenario, email optional, rows prefixed `DEMO-`. |

URL-encode the email in `sid` (`@` → `%40`). The student sees
"Submitting as jane@example.com — Mock 2" on the system-check screen —
tell them to flag it if that's not them.

## 6. Smoke-test the backend

1. Open the Web App URL directly in a browser → you should see the
   JSON message that the endpoint is live (that's `doGet`).
2. Open `collection_test.html` → click **Send 4 test submissions** →
   all four should report OK.
3. Check the Sheet: 7 new `TEST-` rows (1 video + 6 typed; TEST-B's
   answer B is deliberately blank — blank cells must record), and the
   Drive folder: one tiny `TEST-V__V1__A__…` file.
4. Also run one full pass through `collection_form.html` as a student
   would: system check, 4 video scenarios (camera permission, 10-second
   countdown, 1-minute auto-recording), the break screens, then 7 typed
   scenarios with the 3:30 timer. Let one typed scenario time out and
   deny the camera once mid-test to confirm both failure paths record.

## 7. Test end-to-end into the scorer

1. In Drive: right-click the recordings folder → **Download** → unzip to
   a local folder, e.g. `recordings/`.
2. In the Sheet: **File → Download → .csv** → save as e.g. `export.csv`.
3. Transcribe the video rows (fills the blank `response` cells):
   ```bat
   python transcribe.py --responses export.csv --media-dir recordings --out responses_full.csv --mock
   ```
   (`--mock` = placeholder transcripts. Drop it for real transcription,
   which runs locally — no account or key; the first-ever run downloads
   the Whisper model, ~150 MB, then it's fully offline. Add
   `--whisper-model small` for better accuracy at ~2× the time.)
4. Score everything:
   ```bat
   python run_dryrun.py --responses responses_full.csv --mock
   ```
   Video rows are scored on their transcripts; recording-failure rows and
   blank timed-out answers are skipped and logged.
5. Confirm the results files generate, then delete `TEST-` rows from the
   Sheet and the fake file from the Drive folder.

## Run-day notes (Sunday 7/19)

- The Sheet fills live as students submit — you can watch responses arrive.
- Duplicate rows can occur if a student restarts the session; keep the
  **last** rows per (student_id, prompt_id, question_id) when cleaning,
  or let Nathan adjudicate.
- If a submission fails mid-test, the form queues it and keeps going —
  students see a retry button on the final screen, and unsent answers
  stay saved in their browser. Manual fallback remains email to Michael.
