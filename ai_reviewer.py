#!/usr/bin/env python3
"""
ai_reviewer.py — Score a single CASPer-style response against a Marking Rulebook.

Usage:
    python ai_reviewer.py --rulebook sample_rulebook.json --prompt "..." --response "..." [--model M] [--mock]

--prompt and --response accept either literal text OR a path to a text file
(if the value is an existing file path, the file is read).

Output: a single JSON object on stdout:
    {quartile, rationale, rule_ids_cited, confidence, needs_human_review, raw_model_output?}

Exit codes: 0 = scored OK, 2 = input error (missing file etc.), 3 = API/parse failure after fallback.
"""

import argparse
import hashlib
import json
import os
import re
import sys

DEFAULT_MODEL = "claude-sonnet-4-6"
CONFIDENCE_FLOOR = 0.6  # below this -> needs_human_review

SYSTEM_TEMPLATE = """You are an expert CASPer (situational judgment test) reviewer. You score student responses using ONLY the Marking Rulebook provided below. Do not invent rules; cite rule IDs exactly as they appear in the rulebook.

=== MARKING RULEBOOK (authoritative) ===
{rulebook}
=== END RULEBOOK ===

Scoring instructions:
1. Read the scenario prompt and the student's response.
2. Apply the quartile anchors (Q1 = weakest, Q4 = strongest) and the numbered rules.
3. Respect each rule's "when to apply" / "when NOT to apply" guidance and severity band.
4. Output ONLY a fenced JSON code block, no other text, with exactly these fields:

```json
{{
  "quartile": <integer 1-4, 1=weakest, 4=strongest>,
  "rationale": "<one paragraph explaining the score, referencing rule IDs>",
  "rule_ids_cited": ["R1", "R4"],
  "confidence": <float 0.0-1.0, your confidence in this quartile assignment>
}}
```"""

USER_TEMPLATE = """SCENARIO PROMPT:
{prompt}

STUDENT RESPONSE:
{response}

Score this response now. Remember: output ONLY the fenced JSON block."""


# ---------------------------------------------------------------- rulebook

def load_rulebook(path: str) -> str:
    """Load rulebook as a string to embed in the system prompt.
    JSON files are validated + pretty-printed; anything else is read as markdown."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Rulebook not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read()
    if path.lower().endswith(".json"):
        try:
            data = json.loads(raw)
            return json.dumps(data, indent=2, ensure_ascii=False)
        except json.JSONDecodeError as e:
            print(f"[warn] {path} is not valid JSON ({e}); using raw text as markdown fallback",
                  file=sys.stderr)
            return raw
    return raw  # markdown fallback


def read_text_or_file(value: str) -> str:
    """If value is a path to an existing file, read it; otherwise treat as literal text."""
    if value and os.path.isfile(value):
        with open(value, "r", encoding="utf-8") as f:
            return f.read()
    return value


def compose_prompt_text(entry: dict, question_id: str = "") -> str:
    """Build the prompt text sent to the reviewer from a sample_prompts.json entry.
    Entries have a scenario in 'text' and (new format) a 2-item 'questions' list;
    question_id 'A'/'B' selects one. Falls back gracefully for old entries."""
    scenario = (entry or {}).get("text", "").strip()
    role = (entry or {}).get("role", "").strip()
    if role:
        scenario = f"ROLE: {role}\n{scenario}"
    questions = (entry or {}).get("questions") or []
    qid = (question_id or "").strip().upper()
    idx = {"A": 0, "B": 1}.get(qid, -1)
    if 0 <= idx < len(questions):
        return f"SCENARIO: {scenario}\n\nQUESTION ({qid}): {questions[idx]}"
    if questions:
        listed = "\n".join(f"- {q}" for q in questions)
        return f"SCENARIO: {scenario}\n\nQUESTIONS:\n{listed}"
    return scenario


# ---------------------------------------------------------------- parsing

def _coerce_quartile(value) -> int:
    """Coerce quartile to int and clamp to 1-4. Defaults to 1 on garbage."""
    try:
        if isinstance(value, bool):  # bool is an int subclass; reject explicitly
            q = 1
        elif isinstance(value, (int, float)):
            q = int(round(float(value)))
        elif isinstance(value, str):
            m = re.search(r"-?\d+", value)
            q = int(m.group()) if m else 1
        else:
            q = 1
    except (ValueError, TypeError):
        q = 1
    return max(1, min(4, q))


def _coerce_confidence(value) -> float:
    try:
        c = float(value)
    except (ValueError, TypeError):
        c = 0.0
    return max(0.0, min(1.0, c))


def parse_model_output(text: str) -> dict:
    """Extract the JSON verdict from model output.
    Handles: fenced ```json blocks with surrounding prose, bare fences,
    naked JSON objects, and malformed fields (coerced/clamped).
    Raises ValueError only if no JSON object can be recovered at all."""
    candidates = []

    # 1) fenced blocks, ```json or plain ```
    for m in re.finditer(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE):
        candidates.append(m.group(1).strip())

    # 2) any {...} spans, largest first (greedy brace matching)
    brace_spans = re.findall(r"\{.*\}", text, re.DOTALL)
    candidates.extend(sorted(brace_spans, key=len, reverse=True))

    parsed = None
    for cand in candidates:
        try:
            obj = json.loads(cand)
            if isinstance(obj, dict):
                parsed = obj
                break
        except json.JSONDecodeError:
            continue

    if parsed is None:
        raise ValueError("No parseable JSON object found in model output")

    rule_ids = parsed.get("rule_ids_cited", [])
    if isinstance(rule_ids, str):
        rule_ids = [r.strip() for r in re.split(r"[,;]", rule_ids) if r.strip()]
    elif not isinstance(rule_ids, list):
        rule_ids = []
    rule_ids = [str(r) for r in rule_ids]

    rationale = parsed.get("rationale", "")
    if not isinstance(rationale, str):
        rationale = json.dumps(rationale, ensure_ascii=False)

    result = {
        "quartile": _coerce_quartile(parsed.get("quartile")),
        "rationale": rationale.strip() or "(model provided no rationale)",
        "rule_ids_cited": rule_ids,
        "confidence": _coerce_confidence(parsed.get("confidence")),
    }
    result["needs_human_review"] = result["confidence"] < CONFIDENCE_FLOOR
    return result


# ---------------------------------------------------------------- scoring

def mock_score(prompt: str, response: str) -> dict:
    """Deterministic offline score derived from the response text.
    Same input -> same output, so mock runs are reproducible."""
    h = hashlib.sha256((response or "").strip().encode("utf-8")).hexdigest()
    quartile = (int(h[:8], 16) % 4) + 1
    confidence = round(0.5 + (int(h[8:16], 16) % 50) / 100.0, 2)  # 0.50-0.99
    n_rules = (int(h[16:18], 16) % 3) + 1
    rule_ids = [f"R{(int(h[18 + i], 16) % 8) + 1}" for i in range(n_rules)]
    rule_ids = sorted(set(rule_ids))
    result = {
        "quartile": quartile,
        "rationale": (f"[MOCK] Deterministic placeholder score (quartile {quartile}). "
                      f"No API call was made. Cited rules are pseudo-random: {', '.join(rule_ids)}."),
        "rule_ids_cited": rule_ids,
        "confidence": confidence,
    }
    result["needs_human_review"] = result["confidence"] < CONFIDENCE_FLOOR
    return result


def api_score(prompt: str, response: str, rulebook_text: str, model: str) -> dict:
    """Call the Anthropic API and parse the verdict. Raises on failure."""
    import anthropic  # imported lazily so --mock works without the package/API key
    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    msg = client.messages.create(
        model=model,
        max_tokens=1024,
        system=SYSTEM_TEMPLATE.format(rulebook=rulebook_text),
        messages=[{"role": "user",
                   "content": USER_TEMPLATE.format(prompt=prompt, response=response)}],
    )
    raw = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
    result = parse_model_output(raw)
    result["raw_model_output"] = raw
    return result


def score_response(response: str, prompt: str, rulebook_path: str,
                   model: str = DEFAULT_MODEL, mock: bool = False) -> dict:
    """Public entry point used by run_dryrun.py and evaluation_harness.py."""
    if mock:
        return mock_score(prompt, response)
    rulebook_text = load_rulebook(rulebook_path)
    return api_score(prompt, response, rulebook_text, model)


# ---------------------------------------------------------------- CLI

def main() -> int:
    ap = argparse.ArgumentParser(description="Score one CASPer response against a rulebook.")
    ap.add_argument("--rulebook", required=True, help="Path to rulebook (.json preferred, .md fallback)")
    ap.add_argument("--prompt", required=True, help="Prompt text, or path to a text file")
    ap.add_argument("--response", required=True, help="Response text, or path to a text file")
    ap.add_argument("--model", default=DEFAULT_MODEL, help=f"Model ID (default {DEFAULT_MODEL})")
    ap.add_argument("--mock", action="store_true", help="Deterministic offline score, no API call")
    args = ap.parse_args()

    try:
        prompt = read_text_or_file(args.prompt)
        response = read_text_or_file(args.response)
        if not args.mock:
            load_rulebook(args.rulebook)  # fail fast on missing rulebook
    except FileNotFoundError as e:
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 2

    try:
        result = score_response(response, prompt, args.rulebook, model=args.model, mock=args.mock)
    except Exception as e:  # API error, parse failure, missing key, etc.
        print(json.dumps({"error": f"{type(e).__name__}: {e}"}), file=sys.stderr)
        return 3

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
