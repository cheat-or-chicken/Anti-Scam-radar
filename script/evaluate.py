"""Offline reproducible fixture evaluation; synthetic metrics are not real-world accuracy."""

import argparse
import asyncio
import json
from pathlib import Path

from script.config import Settings
from script.models import PageContext
from script.pipeline import analyze


async def evaluate_file(path: str) -> dict:
    dataset = json.loads(Path(path).read_text())
    matrix = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    failures = []
    for case in dataset["cases"]:
        analysis = await analyze(PageContext.model_validate(case["context"]), Settings(audit_enabled=False))
        predicted = analysis.decision.risk_score >= 35 and not analysis.decision.trusted_domain
        expected = case["label"] == "suspicious"
        key = ("tp" if expected else "fp") if predicted else ("fn" if expected else "tn")
        matrix[key] += 1
        if predicted != expected:
            failures.append(case["id"])
    negatives = matrix["fp"] + matrix["tn"]
    positives = matrix["tp"] + matrix["fn"]
    return {
        "dataset_type": dataset["type"],
        "threshold": 35,
        "count": len(dataset["cases"]),
        **matrix,
        "false_positive_rate": matrix["fp"] / negatives if negatives else None,
        "recall": matrix["tp"] / positives if positives else None,
        "failures": failures,
        "limitation": "Synthetic regression fixtures only; not a real-world accuracy estimate.",
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default="fixtures/golden.json")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(evaluate_file(args.input)), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
