#!/usr/bin/env python3
import base64, json, os, pathlib, socket, subprocess, sys, tempfile, time, urllib.request
from datetime import datetime, timezone

BASE = pathlib.Path.home()/".config"/"kero-control"
STATE = BASE/"seen.json"
META = BASE/"poll-meta.json"
KEY = BASE/"result-ed25519.pem"
REPO = "keromotoboy-netizen/kero-cloud-slots-public"
JOBS_API = f"https://api.github.com/repos/{REPO}/contents/control/jobs.json?ref=main"
SELF_API = f"https://api.github.com/repos/{REPO}/contents/control/kids-poller.py?ref=main"
RESULT_URL = "https://kero-public-slot.onrender.com/control/result"
DEVICE = "kids"
CONTROL_VERSION = "2026.10.05.8"
PRETO = "100.101.3.28"
CINZA = "100.121.228.117"
PHONE = "100.87.82.13"
PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
SERVICE_ALLOW = {"sshd","Tailscale","KeroDeviceAgent","KeroWatchdog"}
MIN_FETCH_SECONDS = 30
SELF_UPDATE_SECONDS = 120

BASE.mkdir(parents=True, exist_ok=True)

def log(event, **kw):
    obj={"ts":datetime.now(timezone.utc).isoformat(),"event":event,**kw}
    print(json.dumps(obj,ensure_ascii=False,separators=(",",":")),flush=True)

def now():
    return datetime.now(timezone.utc)

def load_json(path, default):
    try:
        x=json.loads(path.read_text())
        return x
    except Exception:
        return default

def atomic_json(path,obj):
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,separators=(",",":")))
    os.replace(tmp,path)

def github_content(url):
    req=urllib.request.Request(url,headers={
      "User-Agent":"kero-kids-control/2",
      "Accept":"application/vnd.github+json",
      "Cache-Control":"no-cache"
    })
    with urllib.request.urlopen(req,timeout=12) as r:
        obj=json.loads(r.read())
    raw=base64.b64decode(obj["content"])
    return raw, obj.get("sha","")

def maybe_self_update(meta):
    t=time.time()
    if t-float(meta.get("self_checked",0)) < SELF_UPDATE_SECONDS:
        return meta
    raw,sha=github_content(SELF_API)
    meta["self_checked"]=t
    meta["self_sha"]=sha
    try:
        current=pathlib.Path(__file__).read_bytes()
        if raw != current:
            tmp=pathlib.Path(__file__).with_suffix(".new")
            tmp.write_bytes(raw); os.chmod(tmp,0o700); os.replace(tmp,__file__)
            log("self_updated",sha=sha)
            atomic_json(META,meta)
            os.execv(sys.executable,[sys.executable,__file__])
    finally:
        atomic_json(META,meta)
    return meta

def tcp(host,port,timeout=2):
    try:
        with socket.create_connection((host,port),timeout):
            return True
    except Exception:
        return False

def fetch_jobs(meta):
    t=time.time()
    if t-float(meta.get("jobs_checked",0)) < MIN_FETCH_SECONDS:
        return None,meta
    raw,sha=github_content(JOBS_API)
    obj=json.loads(raw)
    if obj.get("version") != 1 or not isinstance(obj.get("jobs"),list):
        raise ValueError("invalid_manifest")
    meta["jobs_checked"]=t
    meta["jobs_sha"]=sha
    atomic_json(META,meta)
    return obj["jobs"],meta

def ssh_preto(script, timeout=30):
    full="$OutputEncoding=[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"+script
    enc=base64.b64encode(full.encode("utf-16le")).decode()
    remote=PS+" -NoProfile -NonInteractive -EncodedCommand "+enc
    p=subprocess.run(["ssh","-o","BatchMode=yes","-o","ConnectTimeout=5","DELL@"+PRETO,remote],
                     capture_output=True,timeout=timeout)
    def dec(b):
        try: return b.decode("utf-8")
        except Exception:
            try: return b.decode("cp850")
            except Exception: return b.decode("cp1252",errors="replace")
    out={"exit":p.returncode,"stdout":dec(p.stdout)[-12000:],"stderr":dec(p.stderr)[-4000:]}
    if p.returncode != 0:
        raise RuntimeError("remote_exit_"+str(p.returncode)+": "+out["stderr"][-1200:])
    return out

def action_kids_version(params):
    return {"device":DEVICE,"control_version":CONTROL_VERSION,"python":sys.version.split()[0]}

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

def action_kids_read_control_source(params):
    name=str(params.get("name",""))
    allowed={
      "s24-tail-task.py": pathlib.Path("/home/victor/kero-mobile/s24-tail-task.py"),
      "s24-task.py": pathlib.Path("/home/victor/kero-mobile/s24-task.py"),
      "remote-status.py": pathlib.Path("/home/victor/kero-mobile/remote-status.py"),
      "background-watch.sh": pathlib.Path("/home/victor/kero-mobile/background-watch.sh"),
    }
    p=allowed.get(name)
    if not p:
        raise ValueError("source_not_allowlisted")
    data=p.read_text(encoding="utf-8",errors="replace")
    if len(data)>30000:
        raise ValueError("source_too_large")
    return {"name":name,"content":data}

def ssh_s24(command, timeout=20):
    p=subprocess.run(
      ["ssh","-p","8022","-o","BatchMode=yes","-o","ConnectTimeout=5","u0_a435@"+PHONE,command],
      capture_output=True,timeout=timeout,text=True
    )
    out={"exit":p.returncode,"stdout":p.stdout[-4000:],"stderr":p.stderr[-2000:]}
    if p.returncode != 0:
        raise RuntimeError("s24_remote_exit_"+str(p.returncode)+": "+out["stderr"][-1000:])
    return out

def action_s24_open_url(params):
    url=str(params.get("url","")).strip()
    allowed={
      "https://github.com/settings/billing",
      "https://github.com/settings/billing/budgets"
    }
    if url not in allowed:
        raise ValueError("url_not_allowlisted")
    q=base64.b64encode(url.encode()).decode()
    cmd="u=$(printf '%s' '"+q+"' | base64 -d); termux-open-url \"$u\""
    return ssh_s24(cmd,timeout=15)

def action_s24_ssh_rescue_status(params):
    logp=pathlib.Path.home()/"kero-mobile"/"s24-ssh-rescue.log"
    lines=[]
    try: lines=logp.read_text(errors="replace").splitlines()[-12:]
    except Exception: pass
    return {"ssh":tcp(PHONE,8022),"agent":tcp(PHONE,8770),"recent":lines}

def action_s24_ssh_rescue(params):
    script=pathlib.Path.home()/"kero-mobile"/"s24-ssh-rescue.sh"
    if not script.exists(): raise FileNotFoundError("rescue_script_missing")
    p=subprocess.run([str(script)],capture_output=True,text=True,timeout=25)
    logp=pathlib.Path.home()/"kero-mobile"/"s24-ssh-rescue.log"
    lines=[]
    try: lines=logp.read_text(errors="replace").splitlines()[-8:]
    except Exception: pass
    return {"exit":p.returncode,"ssh":tcp(PHONE,8022),"agent":tcp(PHONE,8770),"stdout":p.stdout[-1500:],"stderr":p.stderr[-1500:],"recent":lines}

def action_cinza_connectivity(params):
    ports=[22,445,3389,5985,5986]
    return {"host":CINZA,"ports":{str(p):tcp(CINZA,p,1.5) for p in ports}}

def action_preto_s24_adb_status(params):
    s=r"""$adb=(Get-Command adb -ErrorAction SilentlyContinue).Source
if(!$adb){[pscustomobject]@{adb=$false}|ConvertTo-Json -Compress;exit 0}
$dev=& $adb devices -l 2>&1
$mdns=& $adb mdns services 2>&1
[pscustomobject]@{adb=$true;path=$adb;devices=@($dev);mdns=@($mdns)}|ConvertTo-Json -Compress -Depth 5"""
    return ssh_preto(s)

def action_preto_s24_ssh_rescue(params):
    s=r"""$ErrorActionPreference='Stop'
$adb=(Get-Command adb -ErrorAction SilentlyContinue).Source
if(!$adb){throw 'adb_missing'}
$rows=@(& $adb devices -l 2>&1)
$line=$rows|Where-Object{$_ -match 'model:SM_S921B' -and $_ -match '\sdevice\s'}|Select-Object -First 1
if(!$line){[pscustomobject]@{attempted=$false;reason='s24_not_paired_or_offline'}|ConvertTo-Json -Compress;exit 0}
$serial=($line -split '\s+')[0]
$power=@(& $adb -s $serial shell dumpsys power 2>&1)
$active=($power -match 'mWakefulness=Awake') -or ($power -match 'mInteractive=true')
if($active){[pscustomobject]@{attempted=$false;reason='user_active';serial=$serial}|ConvertTo-Json -Compress;exit 0}
& $adb -s $serial shell am start -n com.termux/.app.TermuxActivity | Out-Null
Start-Sleep -Seconds 1
& $adb -s $serial shell input text sshd | Out-Null
& $adb -s $serial shell input keyevent 66 | Out-Null
Start-Sleep -Seconds 2
[pscustomobject]@{attempted=$true;serial=$serial}|ConvertTo-Json -Compress"""
    return ssh_preto(s,timeout=35)

def action_preto_status(params):
    s=r"""$os=Get-CimInstance Win32_OperatingSystem;$cs=Get-CimInstance Win32_ComputerSystem;$d=Get-PSDrive C;[pscustomobject]@{host=$env:COMPUTERNAME;user=$env:USERNAME;uptime_s=[int]((Get-Date)-$os.LastBootUpTime).TotalSeconds;ram_total_gb=[math]::Round($cs.TotalPhysicalMemory/1GB,1);ram_free_gb=[math]::Round($os.FreePhysicalMemory*1KB/1GB,1);c_free_gb=[math]::Round($d.Free/1GB,1);sshd=(Get-Service sshd -ErrorAction SilentlyContinue).Status.ToString();tailscale=(Get-Service Tailscale -ErrorAction SilentlyContinue).Status.ToString()}|ConvertTo-Json -Compress"""
    return ssh_preto(s)

def action_preto_admin_status(params):
    s=r"""$isAdmin=([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator);[pscustomobject]@{host=$env:COMPUTERNAME;user=$env:USERNAME;is_admin=$isAdmin;identity=[Security.Principal.WindowsIdentity]::GetCurrent().Name}|ConvertTo-Json -Compress"""
    return ssh_preto(s)

def action_preto_baseline_status(params):
    s=r"""$p='C:\ProgramData\Kero';$task=Get-ScheduledTask -TaskName 'KeroWatchdog' -ErrorAction SilentlyContinue;[pscustomobject]@{root=(Test-Path $p);watchdog_file=(Test-Path ($p+'\scripts\watchdog.ps1'));watchdog_task=($null-ne$task);sshd=(Get-Service sshd -ErrorAction SilentlyContinue).Status.ToString();sshd_start=(Get-Service sshd -ErrorAction SilentlyContinue).StartType.ToString();tailscale=(Get-Service Tailscale -ErrorAction SilentlyContinue).Status.ToString();tailscale_start=(Get-Service Tailscale -ErrorAction SilentlyContinue).StartType.ToString()}|ConvertTo-Json -Compress"""
    return ssh_preto(s)

def action_preto_baseline_install(params):
    script=r"""$ErrorActionPreference='Stop'
$root='C:\ProgramData\Kero'
@('agent','state','logs','locks','backup','scripts')|ForEach-Object{New-Item -ItemType Directory -Force -Path (Join-Path $root $_)|Out-Null}
$watch=@'
$ErrorActionPreference='SilentlyContinue'
$log='C:\ProgramData\Kero\logs\watchdog.log'
foreach($n in @('sshd','Tailscale')){
  $s=Get-Service -Name $n -ErrorAction SilentlyContinue
  if($s){
    if($s.StartType -ne 'Automatic'){Set-Service -Name $n -StartupType Automatic}
    if($s.Status -ne 'Running'){Start-Service -Name $n}
  }
}
$agentTask=Get-ScheduledTask -TaskName 'KeroDeviceAgent' -ErrorAction SilentlyContinue
if($agentTask -and $agentTask.State -ne 'Running'){
  Start-ScheduledTask -TaskName 'KeroDeviceAgent' -ErrorAction SilentlyContinue
}
Add-Content -Path $log -Value ((Get-Date).ToString('o')+' ok')
'@
Set-Content -Path (Join-Path $root 'scripts\watchdog.ps1') -Value $watch -Encoding UTF8
Set-Service sshd -StartupType Automatic
Set-Service Tailscale -StartupType Automatic
$taskCmd='powershell.exe -NoProfile -NonInteractive -File "C:\ProgramData\Kero\scripts\watchdog.ps1"'
& schtasks.exe /Create /TN 'KeroWatchdog' /SC MINUTE /MO 5 /TR $taskCmd /RU SYSTEM /RL HIGHEST /F | Out-Null
& schtasks.exe /Run /TN 'KeroWatchdog' | Out-Null
[pscustomobject]@{installed=$true;task='KeroWatchdog';root=$root}|ConvertTo-Json -Compress"""
    return ssh_preto(script,timeout=45)

def action_preto_agent_status(params):
    s=r"""$root='C:\ProgramData\Kero';$task=Get-ScheduledTask -TaskName 'KeroDeviceAgent' -ErrorAction SilentlyContinue;$proc=Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -like '*Kero\\agent\\agent.ps1*'}|Select-Object -First 1 ProcessId,CommandLine;[pscustomobject]@{agent_file=(Test-Path ($root+'\\agent\\agent.ps1'));task_exists=($null-ne$task);task_state=if($task){$task.State.ToString()}else{'Missing'};process_pid=if($proc){$proc.ProcessId}else{$null};inbox=(Test-Path ($root+'\\queue\\inbox'));outbox=(Test-Path ($root+'\\queue\\outbox'))}|ConvertTo-Json -Compress"""
    return ssh_preto(s)

def action_preto_agent_install(params):
    s=r"""$ErrorActionPreference='Stop'
$root='C:\ProgramData\Kero'
$agentDir=Join-Path $root 'agent'
@($agentDir,(Join-Path $root 'queue\inbox'),(Join-Path $root 'queue\processing'),(Join-Path $root 'queue\outbox'),(Join-Path $root 'queue\done'),(Join-Path $root 'queue\failed'),(Join-Path $root 'logs'))|ForEach-Object{New-Item -ItemType Directory -Force -Path $_|Out-Null}
$url='https://raw.githubusercontent.com/keromotoboy-netizen/kero-cloud-slots-public/main/control/windows/kero-agent.ps1'
$tmp=Join-Path $agentDir 'agent.ps1.tmp'
$dst=Join-Path $agentDir 'agent.ps1'
Invoke-WebRequest -UseBasicParsing -Uri $url -OutFile $tmp
$got=(Get-FileHash -Algorithm SHA256 -Path $tmp).Hash.ToLower()
$want='872de5946b6bc6e6acfa30baf8c36d85f1606c85a14675964617ca64548c9e17'
if($got -ne $want){Remove-Item -Force $tmp;throw 'agent_hash_mismatch'}
Move-Item -Force $tmp $dst
$act=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -NonInteractive -File "C:\ProgramData\Kero\agent\agent.ps1"'
$tr=New-ScheduledTaskTrigger -AtStartup
$settings=New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit (New-TimeSpan -Days 3650) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'KeroDeviceAgent' -Action $act -Trigger $tr -Settings $settings -User 'SYSTEM' -RunLevel Highest -Force|Out-Null
Start-ScheduledTask -TaskName 'KeroDeviceAgent'
Start-Sleep -Seconds 3
$task=Get-ScheduledTask -TaskName 'KeroDeviceAgent' -ErrorAction Stop
$info=Get-ScheduledTaskInfo -TaskName 'KeroDeviceAgent' -ErrorAction SilentlyContinue
[pscustomobject]@{installed=$true;sha256=$got;task_state=$task.State.ToString();last_result=if($info){$info.LastTaskResult}else{$null}}|ConvertTo-Json -Compress"""
    return ssh_preto(s,timeout=45)

def action_preto_agent_policy(params):
    s=r"""$path='C:\ProgramData\Kero\agent\agent.ps1';[pscustomobject]@{policies=@(Get-ExecutionPolicy -List|ForEach-Object{[pscustomobject]@{scope=$_.Scope.ToString();policy=$_.ExecutionPolicy.ToString()}});zone_identifier=(Test-Path ($path+':Zone.Identifier'));file_exists=(Test-Path $path)}|ConvertTo-Json -Compress -Depth 6"""
    return ssh_preto(s)

def action_preto_agent_syntax(params):
    s=r"""$path='C:\ProgramData\Kero\agent\agent.ps1';$tokens=$null;$errors=$null;[System.Management.Automation.Language.Parser]::ParseFile($path,[ref]$tokens,[ref]$errors)|Out-Null;[pscustomobject]@{exists=(Test-Path $path);error_count=@($errors).Count;errors=@($errors|ForEach-Object{[pscustomobject]@{message=$_.Message;line=$_.Extent.StartLineNumber;column=$_.Extent.StartColumnNumber;text=$_.Extent.Text}})}|ConvertTo-Json -Compress -Depth 6"""
    return ssh_preto(s)

def action_preto_agent_diagnostics(params):
    s=r"""$root='C:\ProgramData\Kero';$task=Get-ScheduledTask -TaskName 'KeroDeviceAgent' -ErrorAction SilentlyContinue;$info=Get-ScheduledTaskInfo -TaskName 'KeroDeviceAgent' -ErrorAction SilentlyContinue;$act=if($task){$task.Actions|Select-Object Execute,Arguments}else{$null};$log=if(Test-Path ($root+'\logs\agent.log')){@(Get-Content ($root+'\logs\agent.log') -Tail 20)}else{@()};$proc=Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -like '*Kero\\agent\\agent.ps1*'}|Select-Object -First 1 ProcessId,CommandLine;[pscustomobject]@{task_state=if($task){$task.State.ToString()}else{'Missing'};last_run=if($info){$info.LastRunTime}else{$null};last_result=if($info){$info.LastTaskResult}else{$null};action=$act;process=$proc;log=$log}|ConvertTo-Json -Compress -Depth 6"""
    return ssh_preto(s)

def action_preto_agent_selftest(params):
    jid="agent-selftest-"+str(int(time.time()))+"-"+os.urandom(3).hex()
    s=f"""$ErrorActionPreference='Stop';$root='C:\\ProgramData\\Kero';$id='{jid}';$job=[ordered]@{{id=$id;action='status';risk=1;params=@{{}};expires_at=(Get-Date).ToUniversalTime().AddMinutes(2).ToString('o')}}|ConvertTo-Json -Compress;$in=Join-Path $root ('queue\\inbox\\'+$id+'.json');$out=Join-Path $root ('queue\\outbox\\'+$id+'.json');Set-Content -Encoding UTF8 -Path $in -Value $job;$limit=(Get-Date).AddSeconds(20);while((Get-Date)-lt$limit){{if(Test-Path $out){{Get-Content -Raw $out;exit 0}};Start-Sleep -Milliseconds 500}};throw 'agent_selftest_timeout'"""
    return ssh_preto(s,timeout=30)

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


def action_preto_agent_debug(params):
    s=r"""$ErrorActionPreference='SilentlyContinue'
$root='C:\ProgramData\Kero'
$agent=Join-Path $root 'agent\agent.ps1'
$stdout=Join-Path $root 'logs\agent-debug.stdout.log'
$stderr=Join-Path $root 'logs\agent-debug.stderr.log'
Remove-Item $stdout,$stderr -Force -ErrorAction SilentlyContinue
$p=Start-Process -FilePath 'powershell.exe' -ArgumentList @('-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',$agent) -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru -WindowStyle Hidden
Start-Sleep -Seconds 4
$running=-not $p.HasExited
$code=if($p.HasExited){$p.ExitCode}else{$null}
if($running){Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue}
[pscustomobject]@{
  running_after_4s=$running
  exit_code=$code
  stdout=if(Test-Path $stdout){(Get-Content -Raw $stdout)}else{''}
  stderr=if(Test-Path $stderr){(Get-Content -Raw $stderr)}else{''}
  agent_log=if(Test-Path (Join-Path $root 'logs\agent.log')){@(Get-Content (Join-Path $root 'logs\agent.log') -Tail 10)}else{@()}
}|ConvertTo-Json -Compress -Depth 5"""
    return ssh_preto(s,timeout=20)

def action_preto_agent_repair(params):
    s=r"""$ErrorActionPreference='Stop'
$root='C:\ProgramData\Kero'
$agent='C:\ProgramData\Kero\agent\agent.ps1'
$wrap='C:\ProgramData\Kero\agent\launch.ps1'
$wrapper=@'
$ErrorActionPreference='Stop'
$log='C:\ProgramData\Kero\logs\agent-launch.log'
try {
  Add-Content -Path $log -Value ((Get-Date).ToString('o')+' launch')
  & 'C:\ProgramData\Kero\agent\agent.ps1'
} catch {
  Add-Content -Path $log -Value ((Get-Date).ToString('o')+' fatal '+$_.Exception.ToString())
  exit 1
}
'@
Set-Content -Path $wrap -Value $wrapper -Encoding UTF8
$act=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File "C:\ProgramData\Kero\agent\launch.ps1"'
$tr=New-ScheduledTaskTrigger -AtStartup
$settings=New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'KeroDeviceAgent' -Action $act -Trigger $tr -Settings $settings -User 'SYSTEM' -RunLevel Highest -Force|Out-Null
Start-ScheduledTask -TaskName 'KeroDeviceAgent'
Start-Sleep -Seconds 5
$task=Get-ScheduledTask -TaskName 'KeroDeviceAgent'
$info=Get-ScheduledTaskInfo -TaskName 'KeroDeviceAgent'
$proc=Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -like '*Kero\agent\launch.ps1*' -or $_.CommandLine -like '*Kero\agent\agent.ps1*'}|Select-Object -First 1 ProcessId,CommandLine
[pscustomobject]@{
 task_state=$task.State.ToString()
 last_result=$info.LastTaskResult
 process=$proc
 launch_log=if(Test-Path 'C:\ProgramData\Kero\logs\agent-launch.log'){@(Get-Content 'C:\ProgramData\Kero\logs\agent-launch.log' -Tail 10)}else{@()}
 agent_log=if(Test-Path 'C:\ProgramData\Kero\logs\agent.log'){@(Get-Content 'C:\ProgramData\Kero\logs\agent.log' -Tail 10)}else{@()}
}|ConvertTo-Json -Compress -Depth 6"""
    return ssh_preto(s,timeout=30)

ACTIONS = {
  "kids.version": (1, action_kids_version),
  "status.global": (1, action_status_global),
  "s24.health": (1, action_s24_health),
  "kids.read_control_source": (1, action_kids_read_control_source),
  "s24.open_url": (1, action_s24_open_url),
  "s24.ssh.rescue.status": (1, action_s24_ssh_rescue_status),
  "s24.ssh.rescue": (2, action_s24_ssh_rescue),
  "cinza.connectivity": (1, action_cinza_connectivity),
  "preto.status": (1, action_preto_status),
  "preto.s24.adb.status": (1, action_preto_s24_adb_status),
  "preto.s24.ssh.rescue": (2, action_preto_s24_ssh_rescue),
  "preto.admin.status": (1, action_preto_admin_status),
  "preto.baseline.status": (1, action_preto_baseline_status),
  "preto.baseline.install": (2, action_preto_baseline_install),
  "preto.agent.status": (1, action_preto_agent_status),
  "preto.agent.policy": (1, action_preto_agent_policy),
  "preto.agent.repair": (2, action_preto_agent_repair),
  "preto.agent.syntax": (1, action_preto_agent_syntax),
  "preto.agent.install": (2, action_preto_agent_install),
  "preto.agent.diagnostics": (1, action_preto_agent_diagnostics),
  "preto.agent.debug": (1, action_preto_agent_debug),
  "preto.agent.repair": (2, action_preto_agent_repair),
  "preto.agent.selftest": (1, action_preto_agent_selftest),
  "preto.disk": (1, action_preto_disk),
  "preto.process.top": (1, action_preto_process_top),
  "preto.service.status": (1, action_preto_service_status),
  "preto.service.restart": (2, action_preto_service_restart),
}

def canonical(obj):
    return json.dumps(obj,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()

def sign(body):
    with tempfile.TemporaryDirectory() as td:
        p=pathlib.Path(td); inp=p/"body"; sig=p/"sig"
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

def main():
    meta=load_json(META,{})
    try: meta=maybe_self_update(meta)
    except Exception as e: log("self_update_error",error=type(e).__name__+":"+str(e)[:250])
    try:
        jobs,meta=fetch_jobs(meta)
    except Exception as e:
        log("fetch_error",error=type(e).__name__+":"+str(e)[:250]); return 1
    if jobs is None: return 0
    seen=load_json(STATE,{})
    cutoff=time.time()-7*86400
    seen={k:v for k,v in seen.items() if float(v)>cutoff}
    for job in jobs:
        jid=str(job.get("id",""))
        if not jid or jid in seen: continue
        if job.get("target") not in ("kids","any"): continue
        action=str(job.get("action","")); spec=ACTIONS.get(action)
        if not spec: log("job_rejected",job_id=jid,reason="action_not_allowlisted"); continue
        declared=int(job.get("risk",99)); required,fn=spec
        if declared != required or declared >= 3:
            log("job_rejected",job_id=jid,reason="risk_mismatch"); continue
        try:
            if parse_expiry(job.get("expires_at")) <= now():
                seen[jid]=time.time(); atomic_json(STATE,seen); continue
        except Exception:
            log("job_rejected",job_id=jid,reason="bad_expiry"); continue
        started=time.time()
        try:
            result=fn(job.get("params") or {})
            out={"job_id":jid,"device":DEVICE,"action":action,"ok":True,"duration_ms":int((time.time()-started)*1000),
                 "result":result,"ts":datetime.now(timezone.utc).isoformat()}
        except Exception as e:
            out={"job_id":jid,"device":DEVICE,"action":action,"ok":False,"duration_ms":int((time.time()-started)*1000),
                 "error":type(e).__name__+":"+str(e)[:500],"ts":datetime.now(timezone.utc).isoformat()}
        try:
            code=post_result(out)
            seen[jid]=time.time(); atomic_json(STATE,seen)
            log("job_result_sent",job_id=jid,action=action,http=code,ok=out["ok"])
        except Exception as e:
            log("result_error",job_id=jid,error=type(e).__name__+":"+str(e)[:250])
    return 0

if __name__=="__main__":
    sys.exit(main())
