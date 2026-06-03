"""
Run all 200 synthetic questions through all 4 ThaiLLM model containers,
grade against labels.json, and print a comparison report.

Usage:
    python3 scripts/benchmark_thaillm.py            # all reachable model containers
    python3 scripts/benchmark_thaillm.py 8000       # only the container on port 8000

Paths are overridable via env: LLM_BENCH_QUESTIONS, LLM_BENCH_LABELS, LLM_BENCH_RESULTS.
"""
import csv
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

QUESTIONS_CSV = Path(os.environ.get("LLM_BENCH_QUESTIONS", "/Users/tew/Downloads/synthetic/questions.csv"))
LABELS_JSON   = Path(os.environ.get("LLM_BENCH_LABELS",    "/Users/tew/Downloads/synthetic/labels.json"))
RESULTS_DIR   = Path(os.environ.get("LLM_BENCH_RESULTS",   "/Users/tew/Downloads/synthetic/results"))

MODELS = {
    8000: "typhoon-s-thaillm-8b-instruct",
    8001: "openthaigpt-thaillm-8b-instruct-v7.2",
    8002: "pathumma-thaillm-qwen3-8b-think-3.0.0",
    8003: "thalle-0.2-thaillm-8b-fa",
}

CONCURRENCY = 4   # requests per container at a time
TIMEOUT     = 300 # seconds per question


def load_questions() -> list[dict]:
    with open(QUESTIONS_CSV, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def load_labels() -> dict:
    with open(LABELS_JSON, encoding="utf-8") as f:
        return json.load(f)


def ask(port: int, qid: str, question: str) -> tuple[str, str, int]:
    """Returns (qid, answer, tokens). On error answer starts with '[error:'."""
    data = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/agent/thaillm",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            d = json.loads(r.read().decode("utf-8"))
        return qid, d.get("answer", ""), d.get("total_output_token_count", 0)
    except urllib.error.HTTPError as e:
        return qid, f"[error: HTTP {e.code}]", 0
    except Exception as e:
        return qid, f"[error: {e}]", 0


def reachable(port: int) -> bool:
    """Return True if a gateway container answers /health on this port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=3) as r:
            return r.status == 200
    except Exception:
        return False


def grade(answer: str, label: dict) -> bool:
    ans_lower = answer.lower()
    for group in label.get("must_contain_any_of", []):
        keywords = [kw for kw in group if kw is not None]
        if keywords and not any(kw.lower() in ans_lower for kw in keywords):
            return False
    for kw in (label.get("must_not_contain") or []):
        if kw is not None and kw.lower() in ans_lower:
            return False
    return True


def run_model(port: int, questions: list[dict], labels: dict) -> list[dict]:
    model = MODELS[port]
    rows: list[dict] = []
    total = len(questions)
    done = 0

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futures = {ex.submit(ask, port, q["id"], q["question"]): q for q in questions}
        for fut in as_completed(futures):
            qid, answer, tokens = fut.result()
            label = labels.get(qid, {})
            passed = grade(answer, label)
            rows.append({
                "id": qid,
                "tier": label.get("tier", "?"),
                "answer": answer,
                "gold_answer": label.get("gold_answer", ""),
                "passed": passed,
                "tokens": tokens,
            })
            done += 1
            status = "PASS" if passed else "FAIL"
            print(f"  [{model[:20]:20}] {done:3}/{total}  {status}  {qid}", flush=True)

    return rows


def summarize(rows: list[dict]) -> dict:
    tiers: dict[str, dict] = {}
    for r in rows:
        t = r["tier"]
        if t not in tiers:
            tiers[t] = {"pass": 0, "total": 0}
        tiers[t]["total"] += 1
        if r["passed"]:
            tiers[t]["pass"] += 1
    overall_pass  = sum(r["passed"] for r in rows)
    overall_total = len(rows)
    return {"tiers": tiers, "total": overall_total, "pass": overall_pass}


def save_csv(rows: list[dict], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["id", "tier", "answer", "gold_answer", "passed", "tokens"])
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    questions = load_questions()
    labels    = load_labels()
    print(f"Loaded {len(questions)} questions, {len(labels)} labels\n")

    all_summaries: dict[str, dict] = {}
    t0 = time.time()

    def run_and_save(port: int, model: str) -> tuple[str, dict]:
        print(f"\n=== {model} (port {port}) ===", flush=True)
        mt = time.time()
        rows = run_model(port, questions, labels)
        elapsed = time.time() - mt
        summary = summarize(rows)
        save_csv(rows, RESULTS_DIR / f"{model}.csv")
        print(f"  [{model[:30]}] Done in {elapsed:.0f}s — {summary['pass']}/{summary['total']} passed", flush=True)
        return model, summary

    # Ports: optional CLI args (e.g. `... 8000 8003`), else all known. Skip unreachable.
    requested = [int(a) for a in sys.argv[1:] if a.isdigit()] or list(MODELS)
    ports = [p for p in requested if p in MODELS and reachable(p)]
    skipped = [p for p in requested if p not in ports]
    if skipped:
        print(f"Skipping unreachable/unknown ports: {skipped}")
    if not ports:
        print("No reachable model containers. Start at least one and retry.")
        return

    with ThreadPoolExecutor(max_workers=len(ports)) as ex:
        futures = [ex.submit(run_and_save, port, MODELS[port]) for port in ports]
        for fut in as_completed(futures):
            model, summary = fut.result()
            all_summaries[model] = summary

    total_elapsed = time.time() - t0

    # --- final report ---
    print("\n" + "="*70)
    print(f"{'MODEL':<45} {'PASS':>5} {'TOTAL':>6} {'%':>6}")
    print("-"*70)
    for model, s in all_summaries.items():
        pct = 100 * s["pass"] / s["total"] if s["total"] else 0
        print(f"{model:<45} {s['pass']:>5} {s['total']:>6} {pct:>5.1f}%")

    print("\nPer-tier breakdown:")
    all_tiers = sorted({t for s in all_summaries.values() for t in s["tiers"]})
    header = f"{'MODEL':<45} " + "  ".join(f"{t:>10}" for t in all_tiers)
    print(header)
    print("-" * len(header))
    for model, s in all_summaries.items():
        row = f"{model:<45} "
        for t in all_tiers:
            td = s["tiers"].get(t, {"pass": 0, "total": 0})
            pct = 100 * td["pass"] / td["total"] if td["total"] else 0
            row += f"  {td['pass']}/{td['total']}({pct:.0f}%)"
        print(row)

    print(f"\nTotal wall-clock: {total_elapsed:.0f}s")
    print(f"Results saved to: {RESULTS_DIR}/")


if __name__ == "__main__":
    main()
