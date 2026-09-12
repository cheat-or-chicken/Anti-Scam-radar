"""Frozen, prefix-only multi-case evaluation with explicit incomplete runs."""

import argparse
import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from ChatRoom.detector import ROOT, Detector


def boundaries(labels):
    payment = labels.get("first_payment_completed_turn") or labels.get("first_L3_turn")
    candidates = [
        labels.get(k)
        for k in (
            "first_harm_completed_turn",
            "first_sensitive_banking_exposure_turn",
            "first_control_handover_turn",
        )
    ]
    candidates.append(payment)
    return payment, min((x for x in candidates if x is not None), default=None)


def run_case(path, output, repeat):
    data = json.loads(path.read_text())
    labels = json.loads(path.with_name(path.name.replace(".replay.json", ".annotations.json")).read_text())[
        "labels"
    ]
    destination = output / f"run{repeat}"
    destination.mkdir(parents=True, exist_ok=True)
    detector = Detector(log_dir=destination / "traces")
    sid = detector.create_session()
    results, errors = [], []
    for i, raw in enumerate(data["messages"], 1):
        result = detector.analyze(sid, {**raw, "turn": i})
        if result["status"] == "analysis_error":
            errors.append({"turn": i, "attempts": result["attempts"]})
            result = detector.analyze(sid, {**raw, "turn": i})
        results.append(result)
        if result["status"] == "analysis_error":
            break
    payment, harm = boundaries(labels)
    complete = len(results) == len(data["messages"]) and all(r["status"] == "ok" for r in results)
    first = next(
        (r["turn"] for r in results if r.get("decision") and r["decision"]["status"] == "warn"), None
    )
    normal = labels["case_type"] == "benign"
    summary = dict(
        file=path.name,
        repeat=repeat,
        case_type=labels["case_type"],
        completed=complete,
        turns_analyzed=len(results),
        total_turns=len(data["messages"]),
        first_alert_turn=first,
        payment_turn=payment,
        harm_turn=harm,
        before_payment=(first is not None and first < payment)
        if complete and not normal and payment
        else None,
        before_harm=(first is not None and first < harm) if complete and not normal and harm else None,
        detected_by_end=(first is not None) if complete and not normal else None,
        false_alarm=(first is not None) if complete and normal else None,
        harm_lead=(harm - first) if first is not None and harm is not None and not normal else None,
        payment_lead=(payment - first) if first is not None and payment is not None and not normal else None,
        warning_downgrade_turns=[
            r["turn"]
            for a, r in zip(results, results[1:])
            if a.get("decision")
            and r.get("decision")
            and a["decision"]["status"] == "warn"
            and r["decision"]["status"] != "warn"
        ],
        mean_seconds=round(sum(r["elapsed_seconds"] for r in results) / len(results), 3),
        recovered_or_failed_turns=errors,
        model=detector.model,
        prompt_hash=detector.prompt_hash,
        detector_sha256=hashlib.sha256((ROOT / "ChatRoom/detector.py").read_bytes()).hexdigest(),
    )
    target = destination / path.name.replace(".replay.json", ".results.json")
    target.write_text(json.dumps(dict(summary=summary, results=results), ensure_ascii=False, indent=2))
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--suite", default="data/evaluation_suites/expanded-v1.json")
    parser.add_argument("--output", default="reports/expanded-v1")
    parser.add_argument("--workers", type=int, default=9)
    args = parser.parse_args()
    suite = json.loads((ROOT / args.suite).read_text())
    assert (
        hashlib.sha256((ROOT / "ChatRoom/detector.py").read_bytes()).hexdigest()
        == suite["detector_frozen_sha256"]
    )
    for name in suite["cases"]:
        assert (
            hashlib.sha256((ROOT / "data/reconstructed" / name).read_bytes()).hexdigest()
            == suite["file_hashes"][name]
        )
    output = ROOT / args.output
    output.mkdir(parents=True, exist_ok=True)
    tasks = [
        (ROOT / "data/reconstructed" / n, r) for r in range(1, suite["repeats"] + 1) for n in suite["cases"]
    ]
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        reports = list(pool.map(lambda task: run_case(task[0], output, task[1]), tasks))
    (output / "summary.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2))
    if not all(r["completed"] for r in reports):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
