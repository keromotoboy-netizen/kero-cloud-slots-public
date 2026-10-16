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
    """Check public availability and protected-route AUTH GATES only.

    A 401 on an internal route is expected and MUST NOT be reported as an
    application failure. This does not test authenticated functionality.
    """
    endpoints=[
        ("https://keromotoboy.com.br", 200, "PUBLIC_SITE", False),
        ("https://keromotoboy.com.br/rotas/", 401, "ROTAS_AUTH_GATE", True),
        ("https://keromotoboy.com.br/calculadora/", 401, "CALCULADORA_AUTH_GATE", True),
    ]
    bad=0
    for url,expected,label,auth_gate in endpoints:
        ok=False
        for attempt in range(1,4):
            status=0
            error=None
            try:
                request=urllib.request.Request(url,headers={"User-Agent":"kero-public-smoke/1.1"})
                with urllib.request.urlopen(request,timeout=20) as response:
                    status=int(response.status)
            except urllib.error.HTTPError as exc:
                status=int(exc.code)
                error="HTTPError"
            except Exception as exc:
                error=type(exc).__name__

            ok=(status==expected)
            print(json.dumps({
                "check":label,"url":url,"status":status,"expected_status":expected,
                "attempt":attempt,"ok":ok,"auth_guard":auth_gate,
                "authenticated_functionality_tested":False,"error":error
            },separators=(",",":")))

            # A definitive 4xx (except timeout/throttle) is not transient.
            if ok or (400<=status<500 and status not in (408,429)):
                break
            if attempt<3:
                time.sleep(1)
        if not ok:
            bad+=1
    raise SystemExit(2 if bad else 0)

def benchmark():
    slot=os.environ.get("KERO_SLOT","")
    t=time.perf_counter(); x=0
    for i in range(50_000_000): x=(x+i)%1_000_000_007
    print(json.dumps({"slot":slot,"ms":round((time.perf_counter()-t)*1000),"x":x,"platform":sys.platform,"arch":os.environ.get("PROCESSOR_ARCHITECTURE") or os.uname().machine if hasattr(os,"uname") else "unknown"}))

if __name__=="__main__":
    cmd=sys.argv[1] if len(sys.argv)>1 else ""
    {"claim":claim,"complete":complete,"site-smoke":site_smoke,"benchmark":benchmark}.get(cmd,lambda: (_ for _ in ()).throw(RuntimeError("unsupported_command")))()
