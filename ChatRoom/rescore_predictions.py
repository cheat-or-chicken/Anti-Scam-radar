"""Rescore archived predictions without regenerating any risk analysis or predictions."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from ChatRoom.detector import ROOT, load_local_env
from ChatRoom.prediction_matcher import PredictionMatcher, final_status


def main():
    load_local_env()
    source = ROOT / "reports/expanded-v1"
    output = ROOT / "reports/prediction-semantic-v2"
    output.mkdir(parents=True, exist_ok=True)
    jobs = []
    for path in sorted(source.glob("run*/*.results.json")):
        data = json.loads(path.read_text())
        # Resolve the archived input by the final response ID.
        for trace_path in (path.parent / "traces").glob("*.jsonl"):
            last = json.loads(trace_path.read_text().splitlines()[-1])
            if last["result"].get("response_id") == data["results"][-1].get("response_id"):
                messages = last["input"]["messages"]
                break
        else:
            raise ValueError(f"No original input trace for {path.name}")
        for pred in data["results"][-1]["predictions"]:
            jobs.append((path, data["summary"], pred, messages))

    def score(job):
        path, summary, pred, messages = job
        matcher = PredictionMatcher(summary["model"])
        verdict = matcher.check(pred, messages)
        record = dict(
            source=str(path.relative_to(ROOT)),
            source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            case=summary["file"],
            repeat=summary["repeat"],
            prediction=pred,
            old_status=pred["status"],
            new_status=final_status(verdict, pred, len(messages)),
            verdict=verdict,
            original_context=messages[: pred["created_turn"]],
            observation_window=messages[pred["created_turn"] : pred["expires_turn"]],
        )
        target = output / (
            path.parent.name + "_" + path.name.replace(".results.json", "") + "_" + pred["id"] + ".json"
        )
        target.write_text(json.dumps(record, ensure_ascii=False, indent=2))
        print(summary["file"], pred["id"], record["new_status"], verdict["reason"], flush=True)
        return record

    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(score, jobs))
    (output / "summary.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
