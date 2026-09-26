"""Score discovery against the synthetic ground truth and write results/metrics.json.

A predicted item matches a ground-truth item when their evidence overlaps (shared statement
refs or AIS rows) and their types are in the same family. Precision and recall are reported
overall and per type, for rules-only and for rules + the configured LLM provider.

Usage: uv run python eval/score.py [--provider ollama|anthropic|none]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from anvesha import config  # noqa: E402
from anvesha.discover.inventory import Item  # noqa: E402
from anvesha.pipeline import load_demo, run  # noqa: E402

FAMILIES = {
    "life_insurance": "insurance",
    "term_insurance": "insurance",
    "health_insurance": "insurance",
    "home_loan": "loan",
    "personal_loan": "loan",
    "loan": "loan",
    "subscription": "subscription",
    "cloud_storage": "subscription",
}


def family(t: str) -> str:
    return FAMILIES.get(t, t)


def _refs(item: Item) -> set[str]:
    return {e.ref for e in item.evidence}


def _truth_refs(t: dict) -> set[str]:
    return set(t["statement_refs"]) | set(t["ais_refs"])


def _ratio(a: int, b: int) -> float | None:
    return round(a / b, 3) if b else None


def score(items: list[Item], truth: dict) -> dict:
    gt = truth["items"]
    closed = truth["closed_items"]
    matched_gt: dict[str, str] = {}
    tp_items, fp_items, closed_hits = [], [], []
    for item in (i for i in items if i.origin != "manual"):
        refs = _refs(item)
        best, overlap = None, 0
        for t in gt + closed:
            n = len(refs & _truth_refs(t))
            if n > overlap and family(t["type"]) == family(item.type):
                best, overlap = t, n
        if best is None:
            fp_items.append(item)
        elif best in closed:
            closed_hits.append(
                {"id": best["id"], "flagged_possibly_closed": item.status == "possibly_closed"}
            )
        elif best["id"] in matched_gt:
            fp_items.append(item)  # duplicate of an item already found
        else:
            matched_gt[best["id"]] = item.id
            tp_items.append((item, best))
    per_type: dict[str, dict] = {}
    for t in gt:
        row = per_type.setdefault(t["type"], {"truth": 0, "found": 0, "predicted": 0, "correct": 0})
        row["truth"] += 1
        row["found"] += t["id"] in matched_gt
    for item in (i for i in items if i.origin != "manual"):
        row = per_type.setdefault(item.type, {"truth": 0, "found": 0, "predicted": 0, "correct": 0})
        row["predicted"] += 1
    for item, _t in tp_items:
        per_type[item.type]["correct"] += 1
    for row in per_type.values():
        row["recall"] = _ratio(row["found"], row["truth"])
        row["precision"] = _ratio(row["correct"], row["predicted"])
    tp, fp = len(tp_items), len(fp_items)
    return {
        "precision": _ratio(tp, tp + fp),
        "recall": _ratio(tp, len(gt)),
        "true_positives": tp,
        "false_positives": fp,
        "ground_truth_items": len(gt),
        "exact_type_accuracy": _ratio(sum(i.type == t["type"] for i, t in tp_items), tp),
        "found": sorted(matched_gt),
        "missed": [
            {"id": t["id"], "type": t["type"], "institution": t["institution"], "hard": t["hard"]}
            for t in gt
            if t["id"] not in matched_gt
        ],
        "false_positive_items": [
            {"type": i.type, "institution": i.institution, "origin": i.origin} for i in fp_items
        ],
        "found_by_llm": sorted(t["id"] for i, t in tp_items if i.origin == "llm"),
        "closed_items": closed_hits,
        "items_debiting_after_death": sum(i.still_debiting for i in items),
        "per_type": dict(sorted(per_type.items())),
    }


def _llm_run(statement, ais, meta, truth, provider: str, model: str | None) -> dict:
    dod = date.fromisoformat(meta["date_of_death"])
    t0 = time.perf_counter()
    try:
        result = score(run(statement, ais, meta["bank"], dod, provider, model), truth)
    except Exception as exc:  # the report should say why the LLM run is missing
        result = {"error": f"{type(exc).__name__}: {exc}"}
    result["seconds"] = round(time.perf_counter() - t0, 2)
    result["provider"] = provider
    result["model"] = model or (
        config.OLLAMA_MODEL if provider == "ollama" else config.ANTHROPIC_MODEL
    )
    return result


def evaluate(provider: str, models: list[str] | None = None) -> dict:
    """Rules-only, then rules + LLM for the provider (and each extra Ollama model)."""
    statement, ais, meta, truth = load_demo()
    dod = date.fromisoformat(meta["date_of_death"])
    runs = {}
    t0 = time.perf_counter()
    runs["rules_only"] = score(run(statement, ais, meta["bank"], dod, "none"), truth)
    runs["rules_only"]["seconds"] = round(time.perf_counter() - t0, 2)
    if provider != "none":
        models = models or [None]
        for n, model in enumerate(models):
            key = "rules_plus_llm" if n == 0 else f"rules_plus_llm__{model}"
            runs[key] = _llm_run(statement, ais, meta, truth, provider, model)
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "persona": meta["name"],
        "method": "Evidence-overlap match with same type family; see eval/score.py.",
        "runs": runs,
    }


def _summary(name: str, r: dict) -> str:
    if "error" in r:
        return f"{name}: not available ({r['error']})"
    return (
        f"{name}: recall {r['true_positives']}/{r['ground_truth_items']} = {r['recall']}, "
        f"precision {r['precision']} ({r['false_positives']} false positives), "
        f"missed {[m['id'] for m in r['missed']]}"
    )


def metrics_markdown(metrics: dict) -> str:
    lines = [
        "| Run | Found | Recall | Precision | False positives | Missed | Closed SIP flagged |",
        "|---|---|---|---|---|---|---|",
    ]
    for key, r in metrics["runs"].items():
        name = "Rules only" if key == "rules_only" else "Rules + LLM"
        if "provider" in r:
            name += f" ({r['provider']}: `{r['model']}`)"
        if "error" in r:
            lines.append(f"| {name} | not available: {r['error']} | | | | | |")
            continue
        missed = ", ".join(f"{m['id']} {m['type']}" for m in r["missed"]) or "none"
        flagged = all(c["flagged_possibly_closed"] for c in r["closed_items"])
        lines.append(
            f"| {name} | {r['true_positives']}/{r['ground_truth_items']} | {r['recall']} | "
            f"{r['precision']} | {r['false_positives']} | {missed} | "
            f"{'yes' if flagged else 'no'} |"
        )
    lines.append("")
    lines.append(f"_Generated {metrics['generated_at']} by `eval/score.py`._")
    return "\n".join(lines)


def update_readme(metrics: dict, readme: Path = config.ROOT / "README.md") -> None:
    if not readme.exists():
        return
    text = readme.read_text(encoding="utf-8")
    start, end = "<!-- metrics:start -->", "<!-- metrics:end -->"
    if start not in text or end not in text:
        return
    head, rest = text.split(start, 1)
    _, tail = rest.split(end, 1)
    readme.write_text(f"{head}{start}\n{metrics_markdown(metrics)}\n{end}{tail}", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", default=config.LLM_PROVIDER)
    parser.add_argument(
        "--models", nargs="*", help="Ollama models to compare; the first is the headline run."
    )
    args = parser.parse_args()
    metrics = evaluate(args.provider, args.models)
    config.RESULTS_DIR.mkdir(exist_ok=True)
    config.METRICS_PATH.write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    update_readme(metrics)
    for name, r in metrics["runs"].items():
        print(_summary(name, r))
    print(f"written: {config.METRICS_PATH}")


if __name__ == "__main__":
    main()
