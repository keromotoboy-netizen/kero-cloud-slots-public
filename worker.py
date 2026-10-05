import hashlib, json, os, sys
from collections import Counter

MAX_TEXT = 200_000
MAX_JSON = 1_000_000
MAX_RESULT = 64_000

def clamp_text(value):
    s = "" if value is None else str(value)
    if len(s) > MAX_TEXT:
        raise ValueError("payload_too_large")
    return s

def task_health(payload):
    return {"ok": True, "worker": "github-public", "python": sys.version.split()[0]}

def task_sha256(payload):
    text = clamp_text(payload.get("text", ""))
    return {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(), "bytes": len(text.encode("utf-8"))}

def task_text_stats(payload):
    text = clamp_text(payload.get("text", ""))
    words = text.split()
    lines = text.splitlines()
    return {
        "chars": len(text),
        "bytes": len(text.encode("utf-8")),
        "words": len(words),
        "lines": len(lines),
        "unique_words": len({w.casefold() for w in words}),
    }

def task_json_summary(payload):
    data = payload.get("data")
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode("utf-8")) > MAX_JSON:
        raise ValueError("payload_too_large")
    out = {"type": type(data).__name__, "bytes": len(raw.encode("utf-8"))}
    if isinstance(data, dict):
        out["keys"] = sorted(map(str, data.keys()))[:200]
        out["key_count"] = len(data)
    elif isinstance(data, list):
        out["items"] = len(data)
        out["item_types"] = dict(Counter(type(x).__name__ for x in data))
    return out

def task_json_normalize(payload):
    data = payload.get("data")
    raw = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(raw.encode("utf-8")) > MAX_RESULT:
        raise ValueError("result_too_large")
    return {"json": raw, "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest()}

def task_manifest(payload):
    items = payload.get("items")
    if not isinstance(items, list) or len(items) > 500:
        raise ValueError("invalid_items")
    normalized=[]
    for i,item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"invalid_item_{i}")
        path=clamp_text(item.get("path",""))[:500]
        content=clamp_text(item.get("content",""))
        normalized.append({
            "path": path,
            "bytes": len(content.encode("utf-8")),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        })
    return {"items": normalized, "count": len(normalized)}

TASKS = {
    "health": task_health,
    "sha256": task_sha256,
    "text-stats": task_text_stats,
    "json-summary": task_json_summary,
    "json-normalize": task_json_normalize,
    "manifest": task_manifest,
}

def main():
    claim_path=os.environ.get("KERO_CLAIM_FILE","claim.json")
    result_path=os.environ.get("KERO_RESULT_FILE","result.json")
    with open(claim_path,"r",encoding="utf-8") as f:
        claim=json.load(f)
    job=claim.get("job") or {}
    task=str(job.get("task") or "")
    payload=job.get("payload") or {}
    if task not in TASKS:
        raise ValueError("task_not_allowlisted")
    result=TASKS[task](payload)
    encoded=json.dumps(result,ensure_ascii=False,separators=(",",":"))
    if len(encoded.encode("utf-8")) > MAX_RESULT:
        raise ValueError("result_too_large")
    with open(result_path,"w",encoding="utf-8") as f:
        json.dump({"ok":True,"task":task,"result":result},f,ensure_ascii=False,separators=(",",":"))
    print(json.dumps({"ok":True,"task":task,"result_bytes":len(encoded.encode("utf-8"))},separators=(",",":")))

if __name__=="__main__":
    try:
        main()
    except Exception as e:
        result_path=os.environ.get("KERO_RESULT_FILE","result.json")
        with open(result_path,"w",encoding="utf-8") as f:
            json.dump({"ok":False,"error":str(e)[:500]},f,separators=(",",":"))
        print(json.dumps({"ok":False,"error":str(e)[:500]},separators=(",",":")))
        sys.exit(1)
