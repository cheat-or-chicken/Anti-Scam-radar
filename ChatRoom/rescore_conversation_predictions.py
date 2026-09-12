"""Only rescore existing predictions; never call the risk detector."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from ChatRoom.conversation_prediction_review import ConversationReviewer
from ChatRoom.detector import ROOT, load_local_env


def main():
    load_local_env()
    source = ROOT / "reports/expanded-v1"
    output = ROOT / "reports/prediction-whole-conversation-v2"
    output.mkdir(parents=True, exist_ok=True)
    traces = {}
    for p in source.glob("run*/traces/*.jsonl"):
        last = json.loads(p.read_text().splitlines()[-1])
        traces[last["result"]["response_id"]] = last["input"]["messages"]

    def score(path):
        d = json.loads(path.read_text())
        predictions = d["results"][-1]["predictions"]
        messages = traces[d["results"][-1]["response_id"]]
        result = ConversationReviewer(d["summary"]["model"]).check(predictions, messages)
        record = dict(
            case=d["summary"]["file"],
            repeat=d["summary"]["repeat"],
            source=str(path.relative_to(ROOT)),
            source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            predictions=predictions,
            messages=messages,
            review=result,
        )
        (output / (path.parent.name + "_" + path.name)).write_text(
            json.dumps(record, ensure_ascii=False, indent=2)
        )
        print(
            record["repeat"],
            record["case"],
            result["status"],
            result.get("matched"),
            result.get("missed"),
            result.get("uncertain"),
            flush=True,
        )
        return record

    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(score, sorted(source.glob("run*/*.results.json"))))
    (output / "summary.json").write_text(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
