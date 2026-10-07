import ast, hashlib, json, os, sys
from collections import Counter

MAX_TEXT = 200_000
MAX_JSON = 1_000_000
MAX_RESULT = 64_000
WORKER_VERSION = "2.1.0"
MAX_BUILD_FILES = 100
MAX_BUILD_BYTES = 500_000

def clamp_text(value):
    s = "" if value is None else str(value)
    if len(s) > MAX_TEXT:
        raise ValueError("payload_too_large")
    return s

def task_health(payload):
    return {"ok": True, "worker": "github-public", "worker_version": WORKER_VERSION, "python": sys.version.split()[0], "tasks": sorted(TASKS) if "TASKS" in globals() else []}

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


def task_lint(payload):
    kind = str(payload.get("kind") or "").strip().lower()
    text = clamp_text(payload.get("text", ""))
    if kind == "json":
        json.loads(text)
    elif kind == "python":
        ast.parse(text)
    else:
        raise ValueError("unsupported_lint_kind")
    return {"kind": kind, "valid": True, "bytes": len(text.encode("utf-8"))}

def task_unit_test(payload):
    suite = str(payload.get("suite") or "worker-selftest")
    if suite != "worker-selftest":
        raise ValueError("unsupported_test_suite")
    checks = []
    h = task_sha256({"text": "abc"})
    checks.append(h.get("sha256") == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    n = task_json_normalize({"data": {"b": 2, "a": 1}})
    checks.append(n.get("json") == '{"a":1,"b":2}')
    s = task_text_stats({"text": "a b\nc"})
    checks.append(s.get("words") == 3 and s.get("lines") == 2)
    if not all(checks):
        raise ValueError("worker_selftest_failed")
    return {"suite": suite, "passed": len(checks), "failed": 0}

def task_build_safe(payload):
    items = payload.get("files")
    if not isinstance(items, list) or not items or len(items) > MAX_BUILD_FILES:
        raise ValueError("invalid_files")
    total = 0
    manifest = []
    allowed_ext = {".txt", ".md", ".json", ".py", ".js", ".ts", ".css", ".html", ".yml", ".yaml"}
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError(f"invalid_file_{i}")
        path = clamp_text(item.get("path", "")).replace("\\", "/")
        content = clamp_text(item.get("content", ""))
        if not path or path.startswith("/") or ".." in path.split("/"):
            raise ValueError(f"unsafe_path_{i}")
        dot = path.rfind(".")
        ext = path[dot:].lower() if dot >= 0 else ""
        if ext not in allowed_ext:
            raise ValueError(f"unsupported_extension_{i}")
        b = content.encode("utf-8")
        total += len(b)
        if total > MAX_BUILD_BYTES:
            raise ValueError("build_input_too_large")
        if ext == ".json":
            json.loads(content)
        elif ext == ".py":
            ast.parse(content)
        manifest.append({
            "path": path[:500],
            "bytes": len(b),
            "sha256": hashlib.sha256(b).hexdigest(),
        })
    canonical = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {
        "build_type": "validated-manifest",
        "files": manifest,
        "count": len(manifest),
        "bytes": total,
        "build_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    }

TASKS = {
    "health": task_health,
    "sha256": task_sha256,
    "text-stats": task_text_stats,
    "json-summary": task_json_summary,
    "json-normalize": task_json_normalize,
    "manifest": task_manifest,
    "lint": task_lint,
    "unit-test": task_unit_test,
    "build-safe": task_build_safe,
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
