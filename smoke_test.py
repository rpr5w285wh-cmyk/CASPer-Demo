#!/usr/bin/env python3
"""
smoke_test.py — Guardrail checks for the public CASPer demo repo.

Asserts, with no network and no third-party packages:
  1. Every prompt (sample_prompts.json + the SCENARIOS array baked into
     collection_form.html) has a valid question_type ("scenario"/"personal"),
     and training_only, when present, is a boolean.
  2. No training-only prompt can be served to a student: the HTML filters
     ALL_SCENARIOS on the flag, and run_dryrun.py --preview-only excludes
     flagged prompts from the printed prompt sheet.
  3. --mock scoring runs fully offline (no anthropic import, deterministic).

Run:  python3 smoke_test.py
Exits 0 on success, 1 on the first failure.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROMPTS_PATH = os.path.join(HERE, "sample_prompts.json")
FORM_PATH = os.path.join(HERE, "collection_form.html")
VALID_QUESTION_TYPES = {"scenario", "personal"}

failures = []


def check(name: str, ok: bool, detail: str = ""):
    print(("PASS" if ok else "FAIL") + " - " + name + (f" ({detail})" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def parse_html_scenarios(html: str) -> list:
    """Extract the ALL_SCENARIOS entries (prompt_id, question_type, training_only)
    from the inline JS array. Regex-based on purpose: no JS runtime needed."""
    m = re.search(r"const ALL_SCENARIOS = \[(.*?)\n\];", html, re.S)
    if not m:
        return []
    entries = []
    for e in re.finditer(r'\{\s*prompt_id:"([^"]+)"([^{]*?)(?:questions:)', m.group(1), re.S):
        head = e.group(2)
        qt = re.search(r'question_type:"([^"]+)"', head)
        entries.append({
            "prompt_id": e.group(1),
            "question_type": qt.group(1) if qt else None,      # absent tolerated -> defaults to "scenario"
            "training_only": bool(re.search(r"training_only:\s*true", head)),
        })
    return entries


def main() -> int:
    # ---- 1. Data-model validity -------------------------------------------
    with open(PROMPTS_PATH, encoding="utf-8") as f:
        prompts = json.load(f)
    check("sample_prompts.json parses and is non-empty", isinstance(prompts, list) and len(prompts) > 0)
    bad_qt = [p.get("prompt_id") for p in prompts
              if p.get("question_type", "scenario") not in VALID_QUESTION_TYPES]
    check("every JSON prompt has a valid question_type", not bad_qt, f"bad: {bad_qt}")
    bad_flag = [p.get("prompt_id") for p in prompts
                if not isinstance(p.get("training_only", False), bool)]
    check("training_only is boolean when present (JSON)", not bad_flag, f"bad: {bad_flag}")

    with open(FORM_PATH, encoding="utf-8") as f:
        html = f.read()
    html_entries = parse_html_scenarios(html)
    check("HTML ALL_SCENARIOS array found and parsed", len(html_entries) >= 2,
          f"parsed {len(html_entries)} entries")
    bad_html_qt = [e["prompt_id"] for e in html_entries
                   if (e["question_type"] or "scenario") not in VALID_QUESTION_TYPES]
    check("every HTML prompt has a valid question_type", not bad_html_qt, f"bad: {bad_html_qt}")

    # ---- 2. training_only can never reach a student -----------------------
    check("HTML serves SCENARIOS filtered on training_only",
          "const SCENARIOS = ALL_SCENARIOS.filter(s => !s.training_only);" in html)
    served_flagged = [e["prompt_id"] for e in html_entries if e["training_only"]]
    check("no training-only prompt_id in the HTML scenario array", not served_flagged,
          f"flagged in public HTML: {served_flagged}")

    # Behavioral check on the prompt-sheet generator: a flagged prompt must be
    # excluded from --preview-only output, with a stderr note.
    flagged = {"prompt_id": "TRAIN-X1", "section": "typed", "scenario_type": "smoke_test",
               "question_type": "scenario", "training_only": True,
               "text": "Synthetic smoke-test prompt. Must never be printed.",
               "questions": ["placeholder A?", "placeholder B?"]}
    with tempfile.TemporaryDirectory() as td:
        tmp_prompts = os.path.join(td, "prompts.json")
        with open(tmp_prompts, "w", encoding="utf-8") as f:
            json.dump(prompts + [flagged], f)
        proc = subprocess.run(
            [sys.executable, os.path.join(HERE, "run_dryrun.py"), "--preview-only",
             "--prompts", tmp_prompts, "--sample", "999"],
            capture_output=True, text=True, timeout=60)
        check("--preview-only exits 0", proc.returncode == 0, proc.stderr.strip()[:200])
        check("--preview-only excludes the training-only prompt", "TRAIN-X1" not in proc.stdout)
        check("--preview-only notes the exclusion on stderr",
              "excluded 1 training-only" in proc.stderr, f"stderr: {proc.stderr.strip()[:200]}")
        servable_ids = {p["prompt_id"] for p in prompts if not p.get("training_only")}
        missing = [pid for pid in servable_ids if f"[{pid}]" not in proc.stdout]
        check("--preview-only still prints every servable prompt", not missing, f"missing: {missing}")

    # ---- 3. --mock scoring is offline and deterministic -------------------
    sys.path.insert(0, HERE)
    from ai_reviewer import score_response
    r1 = score_response("smoke test response", "smoke test prompt", "sample_rulebook.json", mock=True)
    r2 = score_response("smoke test response", "smoke test prompt", "sample_rulebook.json", mock=True)
    check("--mock scoring returns a valid quartile", r1.get("quartile") in (1, 2, 3, 4))
    check("--mock scoring is deterministic", r1 == r2)
    check("--mock scoring never imports anthropic", "anthropic" not in sys.modules)

    print()
    if failures:
        print(f"SMOKE TEST FAILED: {len(failures)} check(s): {failures}")
        return 1
    print("SMOKE TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
