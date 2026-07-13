# GitHub Pages deployment — prototype for team feedback

## Quick path: front-end-only demo (no backend, ~10 min)

The form detects that `PLACEHOLDER_APPS_SCRIPT_URL` is unfilled and runs in
front-end-only mode: nothing is uploaded, and the end screen summarizes what
WOULD have been submitted (rows + recording sizes) — describe the Sheet/Drive
backend verbally from that screen.

```bash
cd casper_dryrun_build
git init && git add . && git commit -m "CASPer simulator prototype"
git remote add origin https://github.com/<you>/casper-simulator.git
git push -u origin main
```
Repo → Settings → Pages → **Deploy from a branch** → `main` / `root` → Save.
Two minutes later, share:

**`https://<you>.github.io/casper-simulator/collection_form.html?demo=1`**

That's the 2-minute walkthrough (short timers, 1 video + 1 typed scenario).
Camera access works because Pages is HTTPS. Test it yourself once first.
When the backend is ready later, fill the placeholders, push, hard-refresh
(Ctrl+F5) — same URL becomes fully live.

---

## Full path: with live backend

Order matters: the backend must exist BEFORE you push, because the Web App
URL gets baked into the HTML.

## 1. Backend first (~15 min)
Follow `collection_setup.md` steps 1–4: create the Sheet + Drive recordings
folder, paste `apps_script_backend.gs`, replace `PLACEHOLDER_SHEET_ID` and
`PLACEHOLDER_FOLDER_ID`, deploy as Web App (execute as Me, access Anyone).
Then in BOTH `collection_form.html` and `collection_test.html`, replace
`PLACEHOLDER_APPS_SCRIPT_URL` and `PLACEHOLDER_MICHAEL_EMAIL`.

## 2. Push and enable Pages (~5 min)
```bash
cd casper_dryrun_build
git init && git add . && git commit -m "CASPer simulator prototype"
git remote add origin https://github.com/<you>/casper-simulator.git
git push -u origin main
```
Repo → Settings → Pages → Source: **Deploy from a branch** → `main` / `root`
→ Save. The site appears at `https://<you>.github.io/casper-simulator/`
within a couple of minutes (later pushes can take a minute to show — hard-
refresh with Ctrl+F5 if you see stale files).

## 3. Smoke test on the live URL (~5 min)
1. `…/collection_test.html` → Send 4 test submissions → rows in Sheet,
   fake file in Drive.
2. `…/collection_form.html?demo=1` → run the 2-minute demo yourself once,
   including a real recording → check the webm lands in Drive and plays.

## 4. Links for the meeting
- **Demo (2 min):** `…/collection_form.html?demo=1` — short timers,
  1 video + 1 typed scenario, submissions land prefixed `DEMO-`.
- **Full test:** `…/collection_form.html` — the real 45–60 min format.

## Notes
- GitHub Pages is HTTPS, which is required for camera/microphone access —
  this is why Pages beats emailing the file around.
- Free-plan Pages sites are public. The URL is obscure but not secret:
  anyone holding it can submit rows to your Sheet and files to your Drive
  folder. Fine for a prototype week; don't post the link publicly, and
  delete `DEMO-` rows before any real analysis.
- Your contact email is visible in the page source once deployed.
- The Python scripts in the repo don't run on Pages — they're there for
  the team to read; you run them locally.
