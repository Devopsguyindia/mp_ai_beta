#!/usr/bin/env python3
"""Quick verification that follow_up_prompts are returned by V3 /v3/ask.
Run with: python copilot-api/tests/verify_follow_up_prompts.py
Requires: backend running on http://127.0.0.1:8001, valid idcompany, OPENAI_API_KEY in .env
"""
import json
import os
import sys
import urllib.request

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def load_env():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")

load_env()

URL = os.getenv("V3_ASK_URL", "http://127.0.0.1:8001/v3/ask")
IDCOMPANY = int(os.getenv("VERIFY_IDCOMPANY", "212"))

TEST_PROMPTS = [
    "top 10 highest margin sales this year",
    "recent 10 sold items",
    "inventory count and qoh summary for this month",
]


def main():
    print("Verifying follow_up_prompts in V3 response")
    print(f"URL: {URL}, idcompany: {IDCOMPANY}")
    print("-" * 60)

    for i, question in enumerate(TEST_PROMPTS, 1):
        payload = {
            "idcompany": IDCOMPANY,
            "question": question,
            "debug": False,
            "include_chart": False,
        }
        req = urllib.request.Request(
            URL,
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=45) as r:
                body = json.loads(r.read().decode())
        except Exception as e:
            print(f"[{i}] FAIL: {question}")
            print(f"     Error: {e}")
            continue

        fp = body.get("follow_up_prompts")
        insights = body.get("insights") or []
        has_followup_insight = any(
            (i.get("title") or "").lower() == "follow-up" for i in insights
        )

        if isinstance(fp, list) and len(fp) > 0:
            print(f"[{i}] OK: {question}")
            print(f"     follow_up_prompts: {fp}")
        else:
            status = "no follow_up_prompts"
            if has_followup_insight:
                status += " (but Follow-up insight present - LLM may have omitted array)"
            print(f"[{i}] {status}: {question}")
            print(f"     insights count: {len(insights)}")

    print("-" * 60)
    print("Done. Check that at least one prompt returns follow_up_prompts.")


if __name__ == "__main__":
    main()
