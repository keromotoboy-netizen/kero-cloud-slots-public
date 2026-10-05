#!/usr/bin/env python3
import base64, hashlib, json, os, pathlib, socket, subprocess, tempfile, time, urllib.request
from datetime import datetime, timezone

BASE = pathlib.Path.home()/".config"/"kero-control"
STATE = BASE/"seen.json"
KEY = BASE/"result-ed25519.pem"
JOBS_URL = "https://raw.githubusercontent.com/keromotoboy-netizen/kero-cloud-slots-public/main/control/jobs.json"
RESULT_URL = "https://kero-public-slot.onrender.com/control/result"
DEVICE = "kids"
PRETO = "100.101.3.28"
CINZA = "100.121.228.117"
PHONE = "100.87.82.13"
PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
SERVICE_ALLOW = {"sshd","Tailscale","KeroDeviceAgent","KeroWatchdog"}

BASE.mkdir(parents=True, exist_ok=True)

def now():
    return datetime.now(timezone.utc)

def load_seen():
    try:
        d=json.loads(STATE.read_text())
        return d if isinstance(d,dict) else {}
    except Exception:
        return {}

def save_seen(d):
    tmp=STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(d,separators=(",",":")))
    os.replace(tmp,STATE)

def tcp(host,port,timeout=2):
    try:
        with socket.create_connection((host,port),timeout):
            return True
    except Exception:
        return False

def fetch_jobs():
    req=urllib.request.Request(JOBS_URL+"?t="+str(int(time.time())),headers={"User-Agent":"kero-kids-control/1"})
    with urllib.request.urlopen(req,timeout=10) as r:
        obj=json.loads(r.read())
    if obj.get("version") != 1 or not isinstance(obj.get("jobs"),list):
        raise ValueError("invalid_manifest")
    return obj["jobs"]

def ssh_preto(script, timeout=30):
    cmd=["ssh","-o","BatchMode=yes","-o","ConnectTimeout=5","DELL@"+PRETO,
         PS+" -NoProfile -NonInteractive -Command "+script]
    p=subprocess.run(cmd,text=True,capture_output=True,timeout=timeout)
    return {"exit":p.returncode,"stdout":p.stdout[-12000:],"stderr":p.stderr[-4000:]}

def action_status_global(params):
    return {
      "kids":{"host":socket.gethostname(),"ts":int(time.time())},
      "preto":{"ssh":tcp(PRETO,22)},
      "cinza":{"ssh":tcp(CINZA,22)},
      "s24":{"ssh":tcp(PHONE,8022),"agent":tcp(PHONE,8770)}
    }

def action_s24_health(params):
    with urllib.request.urlopen("http://"+PHONE+":8770/health",timeout=5) as r:
        return json.loads(r.read())

def action_preto_status(params):
    s=r"""$os=Get-CimInstance Win32_OperatingSystem;$cs=Get-CimInstance Win32_ComputerSystem;$d=Get-PSDrive C;[pscustomobject]@{host=$env:COMPUTERNAME;user=$env:USERNAME;uptime_s=[int]((Get-Date)-$os.LastBootUpTime).TotalSeconds;ram_total_gb=[math]::Round($cs.TotalPhysicalMemory/1GB,1);ram_free_gb=[math]::Round($os.FreePhysicalMemory*1KB/1GB,1);c_free_gb=[math]::Round($d.Free/1GB,1);sshd=(Get-Service sshd -ErrorAction SilentlyContinue).Status.ToString();tailscale=(Get-Service Tailscale -ErrorAction SilentlyContinue).Status.ToString()}|ConvertTo-Json -Compress"""
    return ssh_preto(s)

def action_preto_disk(params):
    s=r"""Get-PSDrive -PSProvider FileSystem|Select Name,@{n='UsedGB';e={[math]::Round($_.Used/1GB,1)}},@{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}}|ConvertTo-Json -Compress"""
    return ssh_preto(s)

def action_preto_process_top(params):
    s=r"""Get-Process|Sort-Object WorkingSet64 -Descending|Select-Object -First 15 Name,Id,@{n='RAM_MB';e={[math]::Round($_.WorkingSet64/1MB,1)}},CPU|ConvertTo-Json -Compress"""
    return ssh_preto(s)

def action_preto_service_status(params):
    name=str(params.get("service",""))
    if name not in SERVICE_ALLOW: raise ValueError("service_not_allowlisted")
    s=f"Get-Service -Name '{name}' -ErrorAction Stop|Select Name,Status,StartType|ConvertTo-Json -Compress"
    return ssh_preto(s)

def action_preto_service_restart(params):
    name=str(params.get("service",""))
    if name not in SERVICE_ALLOW: raise ValueError("service_not_allowlisted")
    s=f"Restart-Service -Name '{name}' -ErrorAction Stop; Get-Service -Name '{name}'|Select Name,Status,StartType|ConvertTo-Json -Compress"
    return ssh_preto(s)

ACTIONS = {
  "status.global": (1, action_status_global),
  "s24.health": (1, action_s24_health),
  "preto.status": (1, action_preto_status),
  "preto.disk": (1, action_preto_disk),
  "preto.process.top": (1, action_preto_process_top),
  "preto.service.status": (1, action_preto_service_status),
  "preto.service.restart": (2, action_preto_service_restart),
}

def canonical(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()

def sign(body):
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td)
        inp=p/"body"; sig=p/"sig"
        inp.write_bytes(body)
        subprocess.run(["openssl","pkeyutl","-sign","-rawin","-inkey",str(KEY),"-in",str(inp),"-out",str(sig)],
                       check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=10)
        return base64.b64encode(sig.read_bytes()).decode()

def post_result(obj):
    body=canonical(obj)
    req=urllib.request.Request(RESULT_URL,data=body,method="POST",
      headers={"Content-Type":"application/json","X-Kero-Device":DEVICE,"X-Kero-Signature":sign(body)})
    with urllib.request.urlopen(req,timeout=12) as r:
        return r.status

def parse_expiry(s):
    return datetime.fromisoformat(str(s).replace("Z","+00:00"))

def run():
    seen=load_seen()
    cutoff=time.time()-7*86400
    seen={k:v for k,v in seen.items() if float(v)>cutoff}
    for job in fetch_jobs():
        jid=str(job.get("id",""))
        if not jid or jid in seen: continue
        if job.get("target") not in ("kids","any"): continue
        action=str(job.get("action",""))
        spec=ACTIONS.get(action)
        if not spec: continue
        declared=int(job.get("risk",99))
        required,fn=spec
        if declared != required or declared >= 3: continue
        try:
            if parse_expiry(job.get("expires_at")) <= now():
                seen[jid]=time.time(); continue
        except Exception:
            continue
        started=time.time()
        try:
            result=fn(job.get("params") or {})
            out={"job_id":jid,"device":DEVICE,"action":action,"ok":True,"duration_ms":int((time.time()-started)*1000),
                 "result":result,"ts":datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            out={"job_id":jid,"device":DEVICE,"action":action,"ok":False,"duration_ms":int((time.time()-started)*1000),
                 "error":type(e).__name__+":"+str(e)[:500],"ts":datetime.now(timezone.utc).isoformat()}
        try:
            post_result(out)
            seen[jid]=time.time()
            save_seen(seen)
        except Exception:
            pass

if __name__=="__main__":
    run()
