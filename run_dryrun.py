#!/usr/bin/env python3
"""
run_dryrun.py — Orchestrate a CASPer AI-reviewer dry-run.

Modes:
  1) Preview (no scoring, no API):
       python run_dryrun.py --preview-only --sample 5 --seed 42
     Prints N randomly-sampled prompts from sample_prompts.json for the coach
     to send to students.

  2) Scoring run:
       python run_dryrun.py --responses responses_20260719.csv [--mock] [--model M]
     Reads a CSV with columns: student_id, prompt_id, response
     Writes: results.csv, results.json, session_log.txt

Errors on individual rows (API failures, malformed rows) are retried once
(2s backoff), then logged and skipped — the run never crashes on one bad row.
"""

import argparse
import csv
import datetime
import json
import os
import random
import sys
import time

from ai_reviewer import score_response, compose_prompt_text, DEFAULT_MODEL

REQUIRED_COLUMNS = {"student_id", "prompt_id", "response"}
RESULT_FIELDS = ["quartile", "rationale", "rule_ids_cited", "confidence", "needs_human_review"]


def now_iso() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- preview

def load_prompts(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        prompts = json.load(f)
    if not isinstance(prompts, list):
        raise ValueError(f"{path} must contain a JSON array of prompt objects")
    return prompts


def preview(prompts_path: str, sample_n: int, seed: int) -> int:
    try:
        prompts = load_prompts(prompts_path)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"[error] Could not load prompts from {prompts_path}: {e}", file=sys.stderr)
        return 2
    rng = random.Random(seed)
    n = min(sample_n, len(prompts))
    chosen = rng.sample(prompts, n)
    print(f"=== PROMPT SHEET — {n} prompts (seed={seed}) — send these to students ===\n")
    for p in chosen:
        print(f"[{p.get('prompt_id', '?')}]  ({p.get('scenario_type', 'unspecified')})")
        print(p.get("text", "(missing text)").strip())
        for label, q in zip(("A", "B"), p.get("questions", [])):
            print(f"  Question {label}: {q}")
        print("-" * 72)
    print("\nStudents answer via the timed collection_form.html session (2 questions per scenario, 3:30 each)")
    return 0


# ---------------------------------------------------------------- scoring run

def load_responses(path: str, log) -> list:
    """Load and validate the responses CSV. Malformed rows are logged and skipped."""
    rows = []
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        headers = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - headers
        if missing:
            raise ValueError(
                f"CSV is missing required columns: {sorted(missing)}. "
                f"Found: {sorted(headers)}. "
                "Expected a Google Sheet export from the collection pipeline with one "
                "row per prompt (see known_risks.md, risk 3).")
        for i, row in enumerate(reader, start=2):  # header is line 1
            sid = (row.get("student_id") or "").strip()
            pid = (row.get("prompt_id") or "").strip()
            resp = (row.get("response") or "").strip()
            if resp.startswith("(recording failed"):
                log(f"{now_iso()}  SKIP line {i}: {sid}/{pid} recording failure marker — nothing to score")
                continue
            if not sid or not pid or not resp:
                reason = ("blank response — likely a timed-out scenario"
                          if sid and pid else "missing student_id/prompt_id")
                log(f"{now_iso()}  SKIP line {i}: {reason}")
                continue
            rows.append({"student_id": sid, "prompt_id": pid, "response": resp,
                         **{k: v for k, v in row.items() if k not in REQUIRED_COLUMNS}})
    return rows


def build_prompt_index(prompts_path: str) -> dict:
    """prompt_id -> full prompt entry (scenario text + questions list)."""
    if not os.path.isfile(prompts_path):
        return {}
    try:
        return {p.get("prompt_id"): p for p in load_prompts(prompts_path)}
    except (ValueError, json.JSONDecodeError):
        return {}


def score_with_retry(row: dict, prompt_text: str, args, log) -> tuple:
    """Returns (result_dict_or_None, error_str_or_None)."""
    last_err = None
    for attempt in (1, 2):
        try:
            result = score_response(row["response"], prompt_text, args.rulebook,
                                    model=args.model, mock=args.mock)
            return result, None
        except Exception as e:
            last_err = f"{type(e).__name__}: {e}"
            if attempt == 1:
                log(f"{now_iso()}  RETRY {row['student_id']}/{row['prompt_id']} after error: {last_err}")
                time.sleep(2)
    return None, last_err


def run_scoring(args) -> int:
    log_path = os.path.join(args.outdir, "session_log.txt")
    os.makedirs(args.outdir, exist_ok=True)
    log_file = open(log_path, "a", encoding="utf-8")

    def log(line: str):
        print(line)
        log_file.write(line + "\n")
        log_file.flush()

    try:
        rows = load_responses(args.responses, log)
    except (OSError, ValueError) as e:
        log(f"{now_iso()}  FATAL: {e}")
        log_file.close()
        return 2

    if not rows:
        log(f"{now_iso()}  FATAL: no valid rows found in {args.responses}")
        log_file.close()
        return 2

    prompt_index = build_prompt_index(args.prompts)
    log(f"{now_iso()}  START run: {len(rows)} rows, mock={args.mock}, model={args.model}")

    results = []
    for row in rows:
        entry = prompt_index.get(row["prompt_id"])
        if entry:
            prompt_text = compose_prompt_text(entry, row.get("question_id", ""))
        else:
            prompt_text = f"(prompt text unavailable for id {row['prompt_id']})"
        result, err = score_with_retry(row, prompt_text, args, log)
        out = dict(row)
        if result:
            for k in RESULT_FIELDS:
                out[k] = result.get(k)
            out["error"] = ""
            qid = f"/{row['question_id']}" if row.get("question_id") else ""
            log(f"{now_iso()}  {row['student_id']}  {row['prompt_id']}{qid}  "
                f"Q{result['quartile']}  conf={result['confidence']:.2f}")
        else:
            for k in RESULT_FIELDS:
                out[k] = ""
            out["error"] = err
            qid = f"/{row['question_id']}" if row.get("question_id") else ""
            log(f"{now_iso()}  {row['student_id']}  {row['prompt_id']}{qid}  ERROR  {err}")
        results.append(out)

    # results.csv — rule_ids_cited serialized as semicolon list for spreadsheet friendliness
    csv_path = os.path.join(args.outdir, "results.csv")
    fieldnames = list(results[0].keys())
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            r_csv = dict(r)
            if isinstance(r_csv.get("rule_ids_cited"), list):
                r_csv["rule_ids_cited"] = ";".join(r_csv["rule_ids_cited"])
            writer.writerow(r_csv)

    json_path = os.path.join(args.outdir, "results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    n_ok = sum(1 for r in results if not r["error"])
    n_flag = sum(1 for r in results if r.get("needs_human_review") is True)
    log(f"{now_iso()}  DONE: {n_ok}/{len(results)} scored, {n_flag} flagged for human review")
    log(f"{now_iso()}  Wrote {csv_path}, {json_path}")
    log_file.close()
    return 0


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description="CASPer dry-run orchestrator.")
    ap.add_argument("--responses", help="CSV of student responses (student_id, prompt_id, response)")
    ap.add_argument("--rulebook", default="sample_rulebook.json", help="Rulebook path")
    ap.add_argument("--prompts", default="sample_prompts.json", help="Prompts JSON path")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--mock", action="store_true", help="Offline deterministic scoring")
    ap.add_argument("--outdir", default=".", help="Where to write results files")
    ap.add_argument("--preview-only", action="store_true", help="Print sampled prompts, no scoring")
    ap.add_argument("--sample", type=int, default=5, help="Prompts to sample in preview mode")
    ap.add_argument("--seed", type=int, default=42, help="RNG seed for preview sampling")
    args = ap.parse_args()

    if args.preview_only:
        return preview(args.prompts, args.sample, args.seed)

    if not args.responses:
        ap.error("--responses is required unless --preview-only is set")
    if not os.path.isfile(args.responses):
        print(f"[error] Responses file not found: {args.responses}", file=sys.stderr)
        return 2
    return run_scoring(args)


if __name__ == "__main__":
    sys.exit(main())
