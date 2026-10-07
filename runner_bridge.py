#!/usr/bin/env python3
import json, os, sys, time, urllib.request, urllib.error

BRAIN_URL=os.environ.get("BRAIN_WORKER_URL","").strip()
AUD="kero-brain-worker"
CAPS=["runner-probe","health","sha256","text-stats","json-summary","json-normalize","manifest","lint","unit-test","build-safe"]

def req_json(url, method="GET", headers=None, data=None, timeout=25):
    body=None if data is None else json.dumps(data,separators=(",",":")).encode()
    r=urllib.request.Request(url,data=body,method=method,headers=headers or {})
    with urllib.request.urlopen(r,timeout=timeout) as x:
        return json.loads(x.read().decode() or "{}")

def oidc():
    base=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL","")
    tok=os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN","")
    if not base or not tok: raise RuntimeError("oidc_environment_missing")
    sep="&" if "?" in base else "?"
    out=req_json(base+sep+"audience="+AUD,headers={"Authorization":"Bearer "+tok})
    v=out.get("value")
    if not v: raise RuntimeError("oidc_token_missing")
    return v

def post_brain(payload):
    if not BRAIN_URL: raise RuntimeError("brain_worker_url_missing")
    payload=dict(payload)
    variant=(os.environ.get("KERO_RUNNER_VARIANT") or "").strip()
    if variant:
        payload["runner_variant"]=variant
    return req_json(BRAIN_URL,"POST",{
        "Authorization":"Bearer "+oidc(),
        "Content-Type":"application/json",
        "User-Agent":"kero-public-runner-bridge/1.0"
    },payload)

def write_output(k,v):
    p=os.environ.get("GITHUB_OUTPUT")
    if p:
        with open(p,"a",encoding="utf-8") as f: f.write(f"{k}={v}\n")

def claim():
    r=post_brain({"action":"claim","capabilities":CAPS})
    if not r.get("ok"): raise RuntimeError(str(r.get("error") or "claim_failed"))
    with open("claim.json","w",encoding="utf-8") as f: json.dump(r,f,separators=(",",":"))
    job=r.get("job")
    write_output("claimed",str(bool(job)).lower())
    if job:
        print(json.dumps({"claimed":True,"id":job.get("id"),"task":job.get("task"),"classification":job.get("classification")}))
    else:
        print(json.dumps({"claimed":False,"reason":r.get("reason") or "empty_queue"}))

def complete():
    with open("claim.json",encoding="utf-8") as f: claim=json.load(f)
    try:
        with open("result.json",encoding="utf-8") as f: result=json.load(f)
    except Exception:
        result={"ok":False,"error":"worker_result_missing"}
    jid=claim.get("job",{}).get("id")
    if not jid: raise RuntimeError("claim_job_id_missing")
    payload={"action":"complete","id":jid}
    if result.get("ok"):
        payload["result"]={"task":result.get("task"),"result":result.get("result"),"_execution":{"runner_variant":os.environ.get("KERO_RUNNER_VARIANT"),"runner_os":os.environ.get("RUNNER_OS"),"runner_arch":os.environ.get("RUNNER_ARCH")}}
    else:
        payload["error"]=str(result.get("error") or "worker_failed")[:500]
    r=post_brain(payload)
    if not r.get("ok"): raise RuntimeError(str(r.get("error") or "complete_failed"))
    with open("complete-response.json","w",encoding="utf-8") as f: json.dump(r,f,separators=(",",":"))
    print(json.dumps({"completed":True,"id":jid,"status":r.get("job",{}).get("status")}))

def site_smoke():
    urls=["https://keromotoboy.com.br","https://keromotoboy.com.br/rotas/","https://keromotoboy.com.br/calculadora/"]
    bad=0
    for u in urls:
        ok=False
        for a in range(1,4):
            try:
                rq=urllib.request.Request(u,headers={"User-Agent":"kero-public-smoke/1.0"})
                with urllib.request.urlopen(rq,timeout=20) as r:
                    status=r.status
                print(json.dumps({"url":u,"status":status,"attempt":a}))
                ok=200 <= status < 400
            except Exception as e:
                print(json.dumps({"url":u,"status":0,"attempt":a,"error":type(e).__name__}))
            if ok: break
            time.sleep(1)
        if not ok: bad+=1
    raise SystemExit(2 if bad else 0)

def benchmark():
    slot=os.environ.get("KERO_SLOT","")
    t=time.perf_counter(); x=0
    for i in range(50_000_000): x=(x+i)%1_000_000_007
    print(json.dumps({"slot":slot,"ms":round((time.perf_counter()-t)*1000),"x":x,"platform":sys.platform,"arch":os.environ.get("PROCESSOR_ARCHITECTURE") or os.uname().machine if hasattr(os,"uname") else "unknown"}))

if __name__=="__main__":
    cmd=sys.argv[1] if len(sys.argv)>1 else ""
    {"claim":claim,"complete":complete,"site-smoke":site_smoke,"benchmark":benchmark}.get(cmd,lambda: (_ for _ in ()).throw(RuntimeError("unsupported_command")))()
