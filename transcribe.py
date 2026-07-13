#!/usr/bin/env python3
"""
transcribe.py — Fill video rows in a Sheet-exported CSV with transcripts.

Flow:
  1. In Google Drive, download the recordings folder (right-click → Download
     → arrives as a zip). Unzip it somewhere, e.g. ./recordings/
  2. Download the response Sheet as CSV.
  3. Run:
       python transcribe.py --responses sheet_export.csv --media-dir recordings/ \
                            --out responses_transcribed.csv [--mock]
  4. Feed the output to the scorer:
       python run_dryrun.py --responses responses_transcribed.csv

Matching: the backend names each recording
    {student_id}__{prompt_id}__{question_id}__{timestamp}.webm
so rows are matched to files by the first three double-underscore fields.
If a (student, prompt, question) has several files (restarted session),
the lexically-latest timestamp wins.

Transcription runs LOCALLY via faster-whisper — no account, no API key, and
recordings never leave your machine. The first ever run downloads the model
(~150 MB for "base"); after that it works fully offline. Expect roughly
real-time-or-faster on a normal laptop CPU. --mock produces deterministic
placeholder transcripts without even installing faster-whisper.

Typed rows pass through untouched. Video rows that already have text in
`response` (e.g. "(recording failed: …)") are left alone and flagged.
"""

import argparse
import csv
import hashlib
import os
import sys

MEDIA_EXTS = {".webm", ".mp4", ".m4a", ".mp3", ".wav", ".ogg"}


def index_media(media_dir: str) -> dict:
    """(student_id, prompt_id, question_id) -> newest matching file path."""
    index = {}
    if not os.path.isdir(media_dir):
        raise FileNotFoundError(f"Media directory not found: {media_dir}")
    for name in os.listdir(media_dir):
        base, ext = os.path.splitext(name)
        if ext.lower() not in MEDIA_EXTS:
            continue
        parts = base.split("__")
        if len(parts) < 4:
            print(f"[warn] Unrecognized filename shape, skipped: {name}", file=sys.stderr)
            continue
        key = (parts[0], parts[1], parts[2])
        # parts[3] is the timestamp; ISO-derived strings sort lexically
        if key not in index or parts[3] > index[key][0]:
            index[key] = (parts[3], os.path.join(media_dir, name))
    return {k: v[1] for k, v in index.items()}


def mock_transcript(path: str) -> str:
    h = hashlib.sha256(os.path.basename(path).encode("utf-8")).hexdigest()[:8]
    return (f"[MOCK TRANSCRIPT {h}] I would start by making sure I understand the "
            f"situation before acting. I would speak with the person privately, "
            f"listen to their side, and then decide on a fair next step.")


def whisper_transcript(path: str, model_size: str, language: str, _cache={}) -> str:
    """Local transcription via faster-whisper. No account, no API key; the
    first ever run downloads the model (~150 MB for 'base'), then it works
    fully offline. The loaded model is cached across calls."""
    from faster_whisper import WhisperModel  # lazy import so --mock needs no package
    if model_size not in _cache:
        print(f"[info] Loading Whisper model '{model_size}' "
              f"(first run downloads it, then cached locally)…")
        _cache[model_size] = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _info = _cache[model_size].transcribe(path, language=language or None)
    return " ".join(seg.text.strip() for seg in segments).strip()


def main() -> int:
    ap = argparse.ArgumentParser(description="Transcribe video rows in a responses CSV.")
    ap.add_argument("--responses", required=True, help="Sheet-exported CSV")
    ap.add_argument("--media-dir", required=True, help="Folder of downloaded recordings")
    ap.add_argument("--out", default="responses_transcribed.csv")
    ap.add_argument("--whisper-model", default="base",
                    help="faster-whisper model size: tiny/base/small/medium (default base)")
    ap.add_argument("--language", default="en",
                    help="Spoken language code (default en); empty = auto-detect")
    ap.add_argument("--mock", action="store_true", help="Deterministic offline transcripts")
    args = ap.parse_args()

    try:
        media = index_media(args.media_dir)
    except FileNotFoundError as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    try:
        with open(args.responses, "r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            fieldnames = reader.fieldnames or []
    except OSError as e:
        print(f"[error] Could not read {args.responses}: {e}", file=sys.stderr)
        return 2

    if "response" not in fieldnames:
        print("[error] CSV has no 'response' column", file=sys.stderr)
        return 2
    if "transcript_status" not in fieldnames:
        fieldnames = fieldnames + ["transcript_status"]

    n_video = n_done = n_missing = n_skipped = n_failed = 0
    for row in rows:
        rtype = (row.get("response_type") or "").strip().lower()
        if rtype != "video":
            row["transcript_status"] = ""
            continue
        n_video += 1
        existing = (row.get("response") or "").strip()
        if existing:
            row["transcript_status"] = "skipped: response already present"
            n_skipped += 1
            continue
        key = ((row.get("student_id") or "").strip(),
               (row.get("prompt_id") or "").strip(),
               (row.get("question_id") or "").strip())
        path = media.get(key)
        if not path:
            row["transcript_status"] = "no matching recording file"
            n_missing += 1
            print(f"[warn] No recording found for {key}", file=sys.stderr)
            continue
        try:
            text = mock_transcript(path) if args.mock else whisper_transcript(path, args.whisper_model, args.language)
            row["response"] = text
            row["transcript_status"] = "mock" if args.mock else f"transcribed (whisper-{args.whisper_model})"
            n_done += 1
            print(f"  {key[0]} {key[1]}/{key[2]}  ← {os.path.basename(path)}"
                  f"  [{'mock' if args.mock else 'ok'}]")
        except Exception as e:
            row["transcript_status"] = f"error: {type(e).__name__}: {e}"
            n_failed += 1
            print(f"[warn] Transcription failed for {key}: {e}", file=sys.stderr)

    with open(args.out, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nVideo rows: {n_video}  transcribed: {n_done}  "
          f"no-file: {n_missing}  already-filled: {n_skipped}  failed: {n_failed}")
    print(f"Wrote {args.out} — feed it to run_dryrun.py")
    return 0 if n_failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
