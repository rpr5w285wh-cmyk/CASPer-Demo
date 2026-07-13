#!/usr/bin/env python3
"""
evaluation_harness.py — Measure AI-reviewer agreement against expected quartiles.

Usage:
    python evaluation_harness.py [--fixtures test_fixtures.json] [--rulebook sample_rulebook.json]
                                 [--target 60] [--mock] [--model M]

Reads test_fixtures.json: [{prompt_id, response, expected_quartile, notes}, ...]
Reports: exact-match %, off-by-one %, per-quartile recall, avg confidence when wrong.
Exits non-zero if exact-match < --target (default 60%).

Note: --mock produces hash-based placeholder scores, so mock-mode agreement is
meaningless as accuracy — use it only to validate the pipeline (add --target 0).
"""

import argparse
import json
import os
import sys
from collections import defaultdict

from ai_reviewer import score_response, compose_prompt_text, DEFAULT_MODEL


def load_fixtures(path: str) -> list:
    with open(path, "r", encoding="utf-8") as f:
        fixtures = json.load(f)
    if not isinstance(fixtures, list) or not fixtures:
        raise ValueError(f"{path} must be a non-empty JSON array")
    valid = []
    for i, fx in enumerate(fixtures):
        if not isinstance(fx, dict) or "response" not in fx or "expected_quartile" not in fx:
            print(f"[warn] fixture #{i} missing response/expected_quartile — skipped", file=sys.stderr)
            continue
        try:
            fx["expected_quartile"] = max(1, min(4, int(fx["expected_quartile"])))
        except (ValueError, TypeError):
            print(f"[warn] fixture #{i} has non-integer expected_quartile — skipped", file=sys.stderr)
            continue
        valid.append(fx)
    if not valid:
        raise ValueError("No valid fixtures after validation")
    return valid


def build_prompt_index(prompts_path: str) -> dict:
    if not os.path.isfile(prompts_path):
        return {}
    try:
        with open(prompts_path, "r", encoding="utf-8") as f:
            return {p.get("prompt_id"): p for p in json.load(f)}
    except (ValueError, json.JSONDecodeError, OSError):
        return {}


def main() -> int:
    ap = argparse.ArgumentParser(description="CASPer AI-reviewer evaluation harness.")
    ap.add_argument("--fixtures", default="test_fixtures.json")
    ap.add_argument("--rulebook", default="sample_rulebook.json")
    ap.add_argument("--prompts", default="sample_prompts.json")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--target", type=float, default=60.0,
                    help="Minimum exact-match %% to pass (default 60)")
    args = ap.parse_args()

    try:
        fixtures = load_fixtures(args.fixtures)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"[error] {e}", file=sys.stderr)
        return 2

    prompt_index = build_prompt_index(args.prompts)

    exact = 0
    off_by_one = 0
    errors = 0
    wrong_confidences = []
    per_q_total = defaultdict(int)   # expected quartile -> count
    per_q_hit = defaultdict(int)     # expected quartile -> exact matches
    rows = []

    for fx in fixtures:
        pid = fx.get("prompt_id", "?")
        expected = fx["expected_quartile"]
        entry = prompt_index.get(pid)
        if entry:
            prompt_text = compose_prompt_text(entry, fx.get("question_id", ""))
        else:
            prompt_text = f"(prompt text unavailable for id {pid})"
        per_q_total[expected] += 1
        try:
            result = score_response(fx["response"], prompt_text, args.rulebook,
                                    model=args.model, mock=args.mock)
        except Exception as e:
            errors += 1
            rows.append((pid, expected, "ERR", "-", f"{type(e).__name__}: {e}"))
            continue
        got = result["quartile"]
        conf = result["confidence"]
        if got == expected:
            exact += 1
            per_q_hit[expected] += 1
            status = "EXACT"
        elif abs(got - expected) == 1:
            off_by_one += 1
            wrong_confidences.append(conf)
            status = "OFF-BY-1"
        else:
            wrong_confidences.append(conf)
            status = "MISS"
        rows.append((pid, expected, got, f"{conf:.2f}", status))

    n = len(fixtures)
    scored = n - errors
    exact_pct = 100.0 * exact / n
    within_one_pct = 100.0 * (exact + off_by_one) / n
    avg_conf_wrong = (sum(wrong_confidences) / len(wrong_confidences)) if wrong_confidences else None

    print(f"\n=== Evaluation ({'MOCK' if args.mock else args.model}) — {n} fixtures ===")
    print(f"{'prompt_id':<12}{'expected':>9}{'got':>6}{'conf':>7}  status")
    for pid, exp, got, conf, status in rows:
        print(f"{str(pid):<12}{exp:>9}{str(got):>6}{conf:>7}  {status}")

    print(f"\nExact-match agreement:   {exact}/{n}  ({exact_pct:.1f}%)")
    print(f"Within-one agreement:    {exact + off_by_one}/{n}  ({within_one_pct:.1f}%)")
    if errors:
        print(f"Errors (not scored):     {errors}")
    print("Per-quartile recall:")
    for q in sorted(per_q_total):
        total, hit = per_q_total[q], per_q_hit[q]
        print(f"  Q{q}: {hit}/{total}  ({100.0 * hit / total:.0f}%)")
    if avg_conf_wrong is not None:
        print(f"Avg confidence when wrong: {avg_conf_wrong:.2f}")
    else:
        print("Avg confidence when wrong: n/a (no wrong answers)")

    if args.mock:
        print("\n[note] Mock mode: scores are hash-based placeholders. "
              "Agreement numbers validate the pipeline, not the reviewer.")

    passed = exact_pct >= args.target
    print(f"\nTarget: exact-match >= {args.target:.0f}%  ->  {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
