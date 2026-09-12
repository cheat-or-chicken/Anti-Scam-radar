"""Live, prefix-only evaluation. Labels never enter Detector inputs."""

import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ChatRoom.detector import ROOT, Detector


def evaluate(path, output, model=None):
    data = json.loads(path.read_text())
    labels = json.loads(path.with_name(path.name.replace(".replay.json", ".annotations.json")).read_text())[
        "labels"
    ]
    detector = Detector(model=model, log_dir=output / "traces")
    sid = detector.create_session()
    results = []
    for i, raw in enumerate(data["messages"], 1):
        result = detector.analyze(sid, {**raw, "turn": i})
        results.append(result)
        if result["status"] == "analysis_error":
            print(path.name[:2], i, result["attempts"], flush=True)
            # Infrastructure failure is not a classification failure; stop spending on this case.
            break
        print(path.name[:2], i, result["decision"]["status"], flush=True)
    first = next((r["turn"] for r in results if r["decision"] and r["decision"]["status"] == "warn"), None)
    normal = labels["case_type"] == "benign"
    payment = labels.get("first_payment_completed_turn") or labels.get("first_L3_turn")
    complete = len(results) == len(data["messages"]) and all(r["status"] == "ok" for r in results)
    report = {
        "file": path.name,
        "session_id": sid,
        "model": detector.model,
        "prompt_hash": detector.prompt_hash,
        "completed": complete,
        "turns_analyzed": len(results),
        "total_turns": len(data["messages"]),
        "first_alert_turn": first,
        "payment_turn": payment,
        "lead_turns": payment - first if first is not None and not normal else None,
        "false_alarm": first is not None if normal and complete else None,
        "evaluation_status": "completed" if complete else "blocked",
        "passed": complete and (first is None if normal else first is not None and first < payment),
        "first_warning": next(
            (r["decision"] for r in results if r["decision"] and r["decision"]["status"] == "warn"), None
        ),
    }
    (output / (path.name[:2] + ".results.json")).write_text(
        json.dumps({"summary": report, "results": results}, ensure_ascii=False, indent=2)
    )
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="var/dialogue-evaluation")
    parser.add_argument("--model", default=None)
    args = parser.parse_args()
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    files = [
        next((ROOT / "data/reconstructed").glob(prefix + "*.replay.json")) for prefix in ["B1_", "B2_", "N1_"]
    ]
    with ThreadPoolExecutor(max_workers=3) as pool:
        reports = list(pool.map(lambda p: evaluate(p, output, args.model), files))
    (output / "summary.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2))
    print(json.dumps(reports, ensure_ascii=False, indent=2), flush=True)
    if not all(r["completed"] for r in reports):
        raise SystemExit(2)
    if not all(r["passed"] for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
