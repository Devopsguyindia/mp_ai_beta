from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = ROOT / "prompt_coverage" / "prompt_dataset_v1.jsonl"
CONTRACTS_PATH = ROOT / "prompt_coverage" / "prompt_to_sql_contracts.json"
OUT_DIR = ROOT / "tests" / "output"


def _post_json(url: str, payload: dict[str, Any], timeout_s: int) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    try:
        with request.urlopen(req, timeout=timeout_s) as resp:
            status = int(resp.status)
            raw = resp.read().decode("utf-8")
            return status, json.loads(raw)
    except error.HTTPError as e:
        raw = e.read().decode("utf-8") if e.fp else "{}"
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"error": raw}
        return int(e.code), payload


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _intent_soft_match(expected_intent: str, actual_intent: str) -> bool:
    e = expected_intent.strip().lower()
    a = actual_intent.strip().lower()
    if e == a:
        return True
    # Soft match with synonym groups to avoid false negatives from paraphrased LLM intent labels.
    synonym_groups = {
        "recent": {"recent", "latest", "last", "newest"},
        "items": {"item", "items", "artwork", "artworks", "lines"},
        "customers": {"customer", "customers", "buyer", "buyers", "collector", "collectors"},
        "artists": {"artist", "artists"},
        "sales": {"sale", "sales", "sold"},
        "revenue": {"revenue", "gross", "income"},
        "top": {"top", "highest", "best", "rank"},
        "inventory": {"inventory", "stock"},
        "count": {"count", "how_many", "total"},
        "layaway": {"layaway"},
        "outstanding": {"outstanding", "overdue", "due"},
        "customer": {"customer", "customers", "collector", "collectors", "buyer", "buyers", "client"},
        "artist": {"artist", "artists"},
        "vendor": {"vendor", "vendors", "supplier", "suppliers"},
        "ltv": {"ltv", "lifetime", "value", "spend"},
        "inactive": {"inactive", "dormant"},
        "repeat": {"repeat", "returning"},
        "segment": {"segment", "segments"},
        "quality": {"quality", "data_quality", "completeness", "missing"},
        "commission": {"commission", "settlement", "royalty"},
        "payables": {"payables", "dues", "outstanding", "invoice"},
    }
    tokens = [t for t in e.split("_") if t and t not in {"sales", "inventory", "customer", "artist", "vendor"}]
    for token in tokens:
        group = synonym_groups.get(token, {token})
        if not any(g in a for g in group):
            return False
    return True


def _contract_map() -> dict[str, dict[str, Any]]:
    payload = _load_json(CONTRACTS_PATH)
    return {c["contract_id"]: c for c in payload.get("contracts", [])}


def _check_contract(sql: str, contract: dict[str, Any]) -> bool:
    low = sql.lower()
    preferred = [r.lower() for r in contract.get("preferred_relations", [])]
    if preferred and not any(r in low for r in preferred):
        return False
    if contract.get("enforce_limit"):
        if " limit " not in f" {low} ":
            return False
    return True


def run(
    base_url: str,
    idcompany: int,
    max_prompts: int | None,
    timeout_s: int,
    copilots_filter: set[str] | None = None,
) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prompts = _load_jsonl(DATASET_PATH)
    if copilots_filter:
        prompts = [p for p in prompts if p.get("copilot") in copilots_filter]
    if max_prompts is not None:
        prompts = prompts[:max_prompts]
    contracts = _contract_map()

    total = len(prompts)
    passed = 0
    failures: list[dict[str, Any]] = []
    by_copilot: dict[str, dict[str, int]] = {}

    for p in prompts:
        payload = {"idcompany": idcompany, "question": p["question"], "debug": True}
        status, resp = _post_json(f"{base_url.rstrip('/')}/chat", payload, timeout_s=timeout_s)

        if status != 200:
            cp = str(p.get("copilot", "unknown"))
            by_copilot.setdefault(cp, {"total": 0, "passed": 0, "failed": 0})
            by_copilot[cp]["total"] += 1
            by_copilot[cp]["failed"] += 1
            failures.append(
                {
                    "prompt_id": p["prompt_id"],
                    "question": p["question"],
                    "reason": "http_non_200",
                    "status": status,
                    "response": json.dumps(resp, ensure_ascii=True),
                }
            )
            continue

        debug = (resp.get("debug") or {})
        guard = (debug.get("guardrails") or {})
        sql = str(debug.get("generated_sql") or "")
        matched_intent = str(debug.get("matched_intent") or "")
        expected_intent = str(p.get("intent_id") or "")
        expected_contract = contracts.get(p.get("expected_contract_id", ""), {})

        checks = {
            "guard_ok": bool(guard.get("ok") is True),
            "select_only": sql.strip().lower().startswith("select"),
            "idcompany_param": "%(idcompany)s" in sql,
            "intent_match": _intent_soft_match(expected_intent, matched_intent),
            "contract_match": _check_contract(sql, expected_contract),
        }
        failed_checks = [k for k, ok in checks.items() if not ok]
        if failed_checks:
            cp = str(p.get("copilot", "unknown"))
            by_copilot.setdefault(cp, {"total": 0, "passed": 0, "failed": 0})
            by_copilot[cp]["total"] += 1
            by_copilot[cp]["failed"] += 1
            failures.append(
                {
                    "prompt_id": p["prompt_id"],
                    "question": p["question"],
                    "reason": "check_failed",
                    "failed_checks": ",".join(failed_checks),
                    "expected_intent": expected_intent,
                    "actual_intent": matched_intent,
                    "sql": sql,
                }
            )
            continue

        cp = str(p.get("copilot", "unknown"))
        by_copilot.setdefault(cp, {"total": 0, "passed": 0, "failed": 0})
        by_copilot[cp]["total"] += 1
        by_copilot[cp]["passed"] += 1
        passed += 1

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    by_copilot_rates: dict[str, dict[str, float | int]] = {}
    for cp, stats in by_copilot.items():
        rate = round((stats["passed"] / stats["total"]) * 100, 2) if stats["total"] else 0.0
        by_copilot_rates[cp] = {**stats, "pass_rate": rate}
    summary = {
        "timestamp_utc": ts,
        "base_url": base_url,
        "idcompany": idcompany,
        "total": total,
        "passed": passed,
        "failed": total - passed,
        "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
        "by_copilot": by_copilot_rates,
    }
    (OUT_DIR / f"regression-summary-{ts}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    csv_path = OUT_DIR / f"regression-failures-{ts}.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["prompt_id", "question", "reason", "status", "failed_checks", "expected_intent", "actual_intent", "sql", "response"],
        )
        writer.writeheader()
        for row in failures:
            writer.writerow(row)

    print(json.dumps(summary, indent=2))
    print(f"Failure report: {csv_path}")
    return 0 if not failures else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NL->SQL prompt regression suite.")
    parser.add_argument("--base-url", default="http://localhost:8001", help="Copilot API base URL")
    parser.add_argument("--idcompany", type=int, required=True, help="Tenant/company id for tests")
    parser.add_argument("--max-prompts", type=int, default=None, help="Limit prompts for quick runs")
    parser.add_argument("--timeout-s", type=int, default=30, help="HTTP timeout seconds")
    parser.add_argument(
        "--copilots",
        default="",
        help="Comma separated copilots to run (sales,inventory,customer,artist,vendor)",
    )
    args = parser.parse_args()
    copilots = {c.strip() for c in args.copilots.split(",") if c.strip()} if args.copilots else None
    return run(args.base_url, args.idcompany, args.max_prompts, args.timeout_s, copilots_filter=copilots)


if __name__ == "__main__":
    raise SystemExit(main())

