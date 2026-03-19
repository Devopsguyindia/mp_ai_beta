#!/usr/bin/env python3
"""
Run 10 diverse inventory copilot prompts against V3 /v3/ask and record results.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

# Add project root for dotenv
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def load_env():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")


def post_v3_ask(question: str, idcompany: int = 48, copilot: str = "inventory") -> dict:
    url = os.getenv("V3_ASK_URL", "http://127.0.0.1:8001/v3/ask")
    payload = {
        "idcompany": idcompany,
        "question": question,
        "copilot": copilot,
        "debug": True,
        "include_chart": False,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# 10 diverse inventory prompts targeting inventory copilot
INVENTORY_PROMPTS = [
    "Inventory aging report top 10",
    "How many items are in stock in last 30 days?",
    "Total inventory quantity on hand for last 90 days",
    "Show 10 oldest unsold items",
    "Top 10 unsold items by asking price",
    "Highest value unsold inventory top 8",
    "Items older than 360 days top 10",
    "Inventory count and qoh summary for last 7 days",
    "Location discrepancy report for inventory top 10",
    "List items with zero quantity on hand",
]


def main():
    load_env()
    output_dir = ROOT / "tests" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "v3-inventory-prompt-test-results.txt"

    results = []
    sql_model = os.getenv("OPENAI_MODEL_SQL", "n/a")
    router_model = "planner (keyword)"

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("V3 Inventory Copilot Prompt Test Results\n")
        f.write("=" * 80 + "\n\n")

        for i, prompt in enumerate(INVENTORY_PROMPTS, 1):
            row = {
                "prompt_num": i,
                "prompt": prompt,
                "status": "fail",
                "router_model": router_model,
                "sql_model": sql_model,
                "generation_path": "n/a",
                "selected_copilot": "n/a",
                "routed_intent": "n/a",
                "planner": None,
                "memory": None,
                "schema": None,
                "sql": None,
                "insight": None,
                "error": None,
            }
            try:
                resp = post_v3_ask(prompt)
                debug = resp.get("debug") or {}
                trace = debug.get("trace") or {}
                row["status"] = "success"
                row["selected_copilot"] = debug.get("selected_copilot", "n/a")
                row["routed_intent"] = debug.get("routed_intent", "n/a")
                row["generation_path"] = debug.get("generation_path", "n/a")
                row["rows_returned"] = debug.get("rows_returned", 0)
                row["planner"] = trace.get("planner")
                row["memory"] = trace.get("memory")
                row["schema"] = trace.get("schema")
                row["sql"] = trace.get("sql")
                row["insight"] = trace.get("insight")
            except urllib.error.HTTPError as e:
                row["error"] = f"HTTP {e.code}: {(e.read() or b'').decode()[:200]}"
            except Exception as ex:
                row["error"] = str(ex)[:200]

            results.append(row)
            line = (
                f"{i}. {prompt}\n"
                f"   Status: {row['status']}\n"
                f"   selected_copilot: {row['selected_copilot']}\n"
                f"   routed_intent: {row['routed_intent']}\n"
                f"   generation_path: {row['generation_path']}\n"
                f"   router_model: {row['router_model']}\n"
                f"   sql_model: {row['sql_model']}\n"
            )
            if row.get("rows_returned") is not None:
                line += f"   rows_returned: {row['rows_returned']}\n"
            if row.get("error"):
                line += f"   error: {row['error']}\n"
            def _fmt(v):
                s = json.dumps(v, default=str, ensure_ascii=True)
                return s if len(s) <= 1200 else s[:1200] + "..."
            line += "\n"
            line += "   1. Planner Agent: " + (_fmt(row.get("planner")) or "n/a") + "\n"
            line += "   2. Memory Agent: " + (_fmt(row.get("memory")) or "n/a") + "\n"
            line += "   3. Schema Agent: " + (_fmt(row.get("schema")) or "n/a") + "\n"
            line += "   4. SQL Agent: " + (_fmt(row.get("sql")) or "n/a") + "\n"
            line += "   5. Insight Agent: " + (_fmt(row.get("insight")) or "n/a") + "\n\n"
            f.write(line)
            f.flush()
            print(line.strip())

        f.write("\n" + "=" * 80 + "\n")
        success_count = sum(1 for r in results if r["status"] == "success")
        f.write(f"Summary: {success_count}/{len(results)} succeeded\n")

    print(f"\nResults written to {out_path}")
    return 0 if success_count == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
