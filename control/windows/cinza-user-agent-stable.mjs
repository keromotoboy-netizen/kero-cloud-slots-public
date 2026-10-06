import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import net from 'node:net';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileP=promisify(execFile);
const HOME=os.homedir();
const BASE=path.join(process.env.LOCALAPPDATA||path.join(HOME,'AppData','Local'),'KeroControl');
const STATE=path.join(BASE,'seen.json');
const PRIV=path.join(BASE,'cinza-ed25519-private.pem');
const PUB=path.join(BASE,'cinza-ed25519-public.pem');
const LOG=path.join(BASE,'agent.log');
const SELF=path.join(BASE,'cinza-user-agent.mjs');
const SUPABASE='https://noqdjfuqaqlicugbqihv.supabase.co';
const APIKEY='sb_publishable_sM9x9lsULWy3TAm37NxWUQ_9oNXEoGr';
const RESULT='https://kero-public-slot.onrender.com/control/result';
const DEVICE='cinza';
const VERSION='2026.10.06.3.4.1';
const POLL_MS=60_000;
const PS='C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe';
const REPO='keromotoboy-netizen/kero-cloud-slots-public';
let restartRequested=false;
const SINGLETON_PORT=18771;
const singleton=net.createServer();
await new Promise((resolve,reject)=>{
  singleton.once('error',e=>{
    if(e?.code==='EADDRINUSE') process.exit(0);
    else reject(e);
  });
  singleton.listen(SINGLETON_PORT,'127.0.0.1',resolve);
});

fs.mkdirSync(BASE,{recursive:true});
function log(event,detail={}) {
  fs.appendFileSync(LOG,JSON.stringify({ts:new Date().toISOString(),event,detail})+'\n');
}
function loadSeen(){try{return JSON.parse(fs.readFileSync(STATE,'utf8'))||{};}catch{return {};}}
function saveSeen(x){const t=STATE+'.tmp';fs.writeFileSync(t,JSON.stringify(x));fs.renameSync(t,STATE);}
function ensureKeys(){
  if(fs.existsSync(PRIV)&&fs.existsSync(PUB)) return;
  const {privateKey,publicKey}=crypto.generateKeyPairSync('ed25519');
  fs.writeFileSync(PRIV,privateKey.export({type:'pkcs8',format:'pem'}),{mode:0o600});
  fs.writeFileSync(PUB,publicKey.export({type:'spki',format:'pem'}));
}
ensureKeys();
async function ps(script,timeout=20_000){
  const prefix="$ProgressPreference='SilentlyContinue';$OutputEncoding=[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();";
  const enc=Buffer.from(prefix+script,'utf16le').toString('base64');
  const {stdout='',stderr=''}=await execFileP(PS,['-NoProfile','-NonInteractive','-EncodedCommand',enc],{timeout,windowsHide:true,maxBuffer:512*1024});
  return {stdout:String(stdout).slice(-12000),stderr:String(stderr).slice(-3000)};
}
function roots(){
  return {
    desktop:path.join(HOME,'Desktop'),
    downloads:path.join(HOME,'Downloads'),
    documents:path.join(HOME,'Documents')
  };
}
function safeUserPath(rootName,rel=''){
  const r=roots()[String(rootName||'')];
  if(!r) throw new Error('root_not_allowlisted');
  const base=path.resolve(r);
  const full=path.resolve(base,String(rel||''));
  if(full!==base&&!full.startsWith(base+path.sep)) throw new Error('path_escape');
  return full;
}
async function actionVersion(){return {device:DEVICE,version:VERSION,node:process.version,user:process.env.USERNAME||'',host:os.hostname()};}
async function actionStatus(){
  return await ps("$os=Get-CimInstance Win32_OperatingSystem;$cs=Get-CimInstance Win32_ComputerSystem;$d=Get-PSDrive C;[pscustomobject]@{host=$env:COMPUTERNAME;user=$env:USERNAME;uptime_s=[int]((Get-Date)-$os.LastBootUpTime).TotalSeconds;ram_total_gb=[math]::Round($cs.TotalPhysicalMemory/1GB,1);ram_free_gb=[math]::Round($os.FreePhysicalMemory*1KB/1GB,1);c_free_gb=[math]::Round($d.Free/1GB,1);tailscale=(Get-Service Tailscale -ErrorAction SilentlyContinue).Status.ToString();sshd=if(Get-Service sshd -ErrorAction SilentlyContinue){(Get-Service sshd).Status.ToString()}else{'Missing'}}|ConvertTo-Json -Compress");
}
async function actionDisk(){return await ps("Get-PSDrive -PSProvider FileSystem|Select Name,@{n='UsedGB';e={[math]::Round($_.Used/1GB,1)}},@{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}}|ConvertTo-Json -Compress");}
async function actionProcessTop(){return await ps("Get-Process|Sort-Object WorkingSet64 -Descending|Select-Object -First 15 Name,Id,@{n='RAM_MB';e={[math]::Round($_.WorkingSet64/1MB,1)}},CPU|ConvertTo-Json -Compress");}
async function actionProcessStop(p){
  const name=String(p?.name||'').toLowerCase();
  const allowed=new Set(['chrome','msedge','notepad']);
  if(!allowed.has(name)) throw new Error('process_not_allowlisted');
  return await ps("Get-Process -Name '"+name+"' -ErrorAction SilentlyContinue|Stop-Process -Force -ErrorAction Stop;[pscustomobject]@{stopped='"+name+"'}|ConvertTo-Json -Compress");
}
async function actionTailscale(){
  return await ps("& 'C:\\Program Files\\Tailscale\\tailscale.exe' status --json | ConvertFrom-Json | Select-Object Self,@{n='PeerCount';e={$_.Peer.PSObject.Properties.Count}} | ConvertTo-Json -Compress -Depth 5");
}
async function actionUserPaths(){return {...roots(),home:HOME,localappdata:process.env.LOCALAPPDATA||''};}
async function actionFileList(p){
  const full=safeUserPath(p?.root,p?.path||'');
  const items=fs.readdirSync(full,{withFileTypes:true}).slice(0,200).map(x=>({name:x.name,type:x.isDirectory()?'dir':x.isFile()?'file':'other'}));
  return {root:p?.root,path:p?.path||'',items};
}
async function actionFileHash(p){
  const full=safeUserPath(p?.root,p?.path||'');
  const st=fs.statSync(full); if(!st.isFile()) throw new Error('not_file'); if(st.size>1024*1024*1024) throw new Error('file_too_large');
  const h=crypto.createHash('sha256'); const fd=fs.openSync(full,'r'); const buf=Buffer.alloc(1024*1024); let pos=0,n=0;
  try{while((n=fs.readSync(fd,buf,0,buf.length,pos))>0){h.update(buf.subarray(0,n));pos+=n;}}finally{fs.closeSync(fd);}
  return {root:p?.root,path:p?.path,size:st.size,sha256:h.digest('hex')};
}
async function actionFileMove(p){
  const src=safeUserPath(p?.src_root,p?.src_path||'');
  const dst=safeUserPath(p?.dst_root,p?.dst_path||'');
  if(!fs.existsSync(src)) throw new Error('source_missing');
  if(fs.existsSync(dst)) throw new Error('destination_exists');
  fs.mkdirSync(path.dirname(dst),{recursive:true}); fs.renameSync(src,dst);
  return {moved:true,src_root:p?.src_root,src_path:p?.src_path,dst_root:p?.dst_root,dst_path:p?.dst_path};
}

async function actionAdminInventory(){
  const script="$ErrorActionPreference='SilentlyContinue';"+
  "$id=[Security.Principal.WindowsIdentity]::GetCurrent();"+
  "$p=New-Object Security.Principal.WindowsPrincipal($id);"+
  "$isAdmin=$p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator);"+
  "$admins=@();try{$admins=@(Get-LocalGroupMember -Group 'Administrators'|Select-Object Name,ObjectClass,PrincipalSource)}catch{};"+
  "$tasks=@();try{$tasks=@(Get-ScheduledTask|Where-Object{$_.TaskName -match 'Kero|RDC|Remote|SSH|Tailscale'}|Select-Object TaskName,TaskPath,State)}catch{};"+
  "$svcs=@(Get-Service|Where-Object{$_.Name -match 'sshd|ssh|tailscale|kero|remote' -or $_.DisplayName -match 'SSH|Tailscale|Kero|Remote'}|Select-Object Name,DisplayName,Status,StartType);"+
  "$uac=(Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System' -Name EnableLUA -ErrorAction SilentlyContinue).EnableLUA;"+
  "[pscustomobject]@{identity=$id.Name;current_token_admin=$isAdmin;uac_enabled=($uac -eq 1);openssh_server_file=(Test-Path 'C:\\Windows\\System32\\OpenSSH\\sshd.exe');sshd_service=if(Get-Service sshd -ErrorAction SilentlyContinue){(Get-Service sshd).Status.ToString()}else{'Missing'};administrators=$admins;related_tasks=$tasks;related_services=$svcs}|ConvertTo-Json -Compress -Depth 7";
  return await ps(script,30_000);
}
async function actionPersistenceStatus(){
  const script="$ErrorActionPreference='SilentlyContinue';"+
  "$base=Join-Path $env:LOCALAPPDATA 'KeroControl';"+
  "$tasks=@(Get-ScheduledTask|Where-Object{$_.TaskName -match 'Kero|Cinza'}|Select-Object TaskName,TaskPath,State,Actions,Triggers);"+
  "$run1=(Get-ItemProperty 'HKCU:\\Software\\Microsoft\\Windows\\CurrentVersion\\Run' -ErrorAction SilentlyContinue).PSObject.Properties|Where-Object{$_.Name -match 'Kero|Cinza'}|Select-Object Name,Value;"+
  "$procs=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -match 'cinza-user-agent|KeroControl'}|Select-Object ProcessId,Name,CommandLine;"+
  "[pscustomobject]@{base=$base;agent_file=(Test-Path (Join-Path $base 'cinza-user-agent.mjs'));tasks=$tasks;run_entries=@($run1);processes=@($procs)}|ConvertTo-Json -Compress -Depth 8";
  return await ps(script,30_000);
}


async function actionPrivilegedTaskStatus(){
  const script="$ErrorActionPreference='SilentlyContinue';"+
  "$n='Kero Admin Worker Privileged';"+
  "$t=Get-ScheduledTask -TaskName $n -ErrorAction SilentlyContinue;"+
  "$i=Get-ScheduledTaskInfo -TaskName $n -ErrorAction SilentlyContinue;"+
  "if(!$t){[pscustomobject]@{exists=$false}|ConvertTo-Json -Compress;exit};"+
  "$acts=@($t.Actions|ForEach-Object{[pscustomobject]@{execute=$_.Execute;arguments=$_.Arguments;working_directory=$_.WorkingDirectory}});"+
  "$pr=[pscustomobject]@{user_id=$t.Principal.UserId;logon_type=$t.Principal.LogonType.ToString();run_level=$t.Principal.RunLevel.ToString()};"+
  "$files=@();foreach($a in $t.Actions){if($a.Execute -and (Test-Path $a.Execute)){$files+=[pscustomobject]@{path=$a.Execute;sha256=(Get-FileHash -Algorithm SHA256 $a.Execute -ErrorAction SilentlyContinue).Hash}}};"+
  "[pscustomobject]@{exists=$true;state=$t.State.ToString();last_run=$i.LastRunTime;last_result=$i.LastTaskResult;next_run=$i.NextRunTime;principal=$pr;actions=$acts;existing_action_files=$files}|ConvertTo-Json -Compress -Depth 6";
  return await ps(script,30_000);
}
async function actionPrivilegedFilesStatus(){
  const script="$ErrorActionPreference='SilentlyContinue';"+
  "$base='C:\\Users\\ailla\\KeroCoordenacao\\admin-kero';"+
  "$paths=@("+
    "(Join-Path $base 'Start-AdminKero-Privileged.ps1'),"+
    "(Join-Path $base 'Install-AdminKero-Privileged.ps1'),"+
    "(Join-Path $base 'admin-worker.mjs'),"+
    "(Join-Path $base 'provider-gateway.mjs')"+
  ");"+
  "$files=@($paths|ForEach-Object{if(Test-Path $_){$i=Get-Item $_;[pscustomobject]@{path=$i.FullName;exists=$true;size=$i.Length;sha256=(Get-FileHash -Algorithm SHA256 $_).Hash.ToLower()}}else{[pscustomobject]@{path=$_;exists=$false;size=0;sha256=$null}}});"+
  "[pscustomobject]@{base=$base;files=$files}|ConvertTo-Json -Compress -Depth 5";
  return await ps(script,20_000);
}
async function actionPrivilegedTaskRun(){
  const script="$ErrorActionPreference='Stop';"+
  "$n='Kero Admin Worker Privileged';"+
  "$t=Get-ScheduledTask -TaskName $n -ErrorAction Stop;"+
  "Start-ScheduledTask -TaskName $n -ErrorAction Stop;Start-Sleep -Seconds 5;"+
  "$t2=Get-ScheduledTask -TaskName $n -ErrorAction Stop;$i=Get-ScheduledTaskInfo -TaskName $n -ErrorAction SilentlyContinue;"+
  "$p=@(Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -match 'admin-worker\\.mjs'}|Select-Object ProcessId,ParentProcessId,CommandLine);"+
  "[pscustomobject]@{started=$true;state=$t2.State.ToString();last_result=if($i){$i.LastTaskResult}else{$null};processes=$p}|ConvertTo-Json -Compress -Depth 5";
  return await ps(script,20_000);
}

async function actionAgentProcesses(){
  const script="$me='"+process.pid+"';"+
  "$x=@(Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -match 'cinza-user-agent.mjs'}|Select-Object ProcessId,ParentProcessId,CreationDate,CommandLine);"+
  "[pscustomobject]@{current_node_pid=[int]$me;agents=$x;count=$x.Count}|ConvertTo-Json -Compress -Depth 5";
  return await ps(script,20_000);
}


async function actionPrivilegedScriptRead(){
  const full=path.join(HOME,'KeroCoordenacao','admin-kero','Start-AdminKero-Privileged.ps1');
  if(!fs.existsSync(full)) return {exists:false,path:full};
  const st=fs.statSync(full);
  if(st.size>200_000) throw new Error('script_too_large');
  const content=fs.readFileSync(full,'utf8');
  return {exists:true,path:full,size:st.size,sha256:crypto.createHash('sha256').update(content).digest('hex'),content};
}
async function actionCleanupLegacyAgents(){
  const me=process.pid;
  const script="$me="+me+";"+
  "$xs=@(Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -match 'cinza-user-agent.mjs' -and $_.ProcessId -ne $me});"+
  "$k=@();foreach($x in $xs){try{Stop-Process -Id $x.ProcessId -Force -ErrorAction Stop;$k+=$x.ProcessId}catch{}};"+
  "[pscustomobject]@{current_pid=$me;killed=@($k);remaining=@(Get-CimInstance Win32_Process -Filter \"Name='node.exe'\" -ErrorAction SilentlyContinue|Where-Object{$_.CommandLine -match 'cinza-user-agent.mjs'}|Select-Object ProcessId,CommandLine)}|ConvertTo-Json -Compress -Depth 5";
  return await ps(script,20_000);
}


async function actionPrivilegedWorkerRead(){
  const full=path.join(HOME,'KeroCoordenacao','admin-kero','admin-worker.mjs');
  if(!fs.existsSync(full)) return {exists:false,path:full};
  const st=fs.statSync(full);
  if(st.size>300_000) throw new Error('worker_too_large');
  const content=fs.readFileSync(full,'utf8');
  return {exists:true,path:full,size:st.size,sha256:crypto.createHash('sha256').update(content).digest('hex'),content};
}
async function actionAgentUpdate(p){
  const commit=String(p?.commit||'').toLowerCase();
  const expected=String(p?.sha256||'').toLowerCase();
  if(!/^[0-9a-f]{40}$/.test(commit)||!/^[0-9a-f]{64}$/.test(expected)) throw new Error('bad_update_descriptor');
  const url='https://raw.githubusercontent.com/'+REPO+'/'+commit+'/control/windows/cinza-user-agent-stable.mjs';
  const r=await fetch(url,{headers:{'User-Agent':'kero-cinza-updater/1','Cache-Control':'no-cache'}});
  if(!r.ok) throw new Error('update_http_'+r.status);
  const body=Buffer.from(await r.arrayBuffer());
  const got=crypto.createHash('sha256').update(body).digest('hex');
  if(got!==expected) throw new Error('update_hash_mismatch');
  const tmp=SELF+'.new.mjs';fs.writeFileSync(tmp,body);
  await execFileP(process.execPath,['--check',tmp],{timeout:15_000,windowsHide:true});
  if(fs.existsSync(SELF+'.bak')) fs.unlinkSync(SELF+'.bak');
  if(fs.existsSync(SELF)) fs.renameSync(SELF,SELF+'.bak');
  fs.renameSync(tmp,SELF);
  restartRequested=true;
  return {updated:true,commit,sha256:got};
}
const ACTIONS={
  'cinza.version':{risk:1,fn:actionVersion},
  'cinza.status':{risk:1,fn:actionStatus},
  'cinza.disk':{risk:1,fn:actionDisk},
  'cinza.process.top':{risk:1,fn:actionProcessTop},
  'cinza.process.stop':{risk:2,fn:actionProcessStop},
  'cinza.tailscale.status':{risk:1,fn:actionTailscale},
  'cinza.user.paths':{risk:1,fn:actionUserPaths},
  'cinza.admin.inventory':{risk:1,fn:actionAdminInventory},
  'cinza.persistence.status':{risk:1,fn:actionPersistenceStatus},
  'cinza.privileged.task.status':{risk:1,fn:actionPrivilegedTaskStatus},
  'cinza.privileged.files.status':{risk:1,fn:actionPrivilegedFilesStatus},
  'cinza.privileged.task.run':{risk:2,fn:actionPrivilegedTaskRun},
  'cinza.agent.processes':{risk:1,fn:actionAgentProcesses},
  'cinza.privileged.script.read':{risk:1,fn:actionPrivilegedScriptRead},
  'cinza.privileged.worker.read':{risk:1,fn:actionPrivilegedWorkerRead},
  'cinza.agent.cleanup_legacy':{risk:2,fn:actionCleanupLegacyAgents},
  'cinza.file.list':{risk:1,fn:actionFileList},
  'cinza.file.hash':{risk:1,fn:actionFileHash},
  'cinza.file.move':{risk:2,fn:actionFileMove},
  'cinza.agent.update':{risk:2,fn:actionAgentUpdate}
};
async function fetchJobs(){
  const u=new URL(SUPABASE+'/rest/v1/kero_control_jobs_public');
  u.searchParams.set('select','id,target,action,params,risk,expires_at,created_at');
  u.searchParams.set('target','in.(cinza,any)');u.searchParams.set('order','created_at.asc');u.searchParams.set('limit','100');
  const r=await fetch(u,{headers:{apikey:APIKEY,Accept:'application/json','Cache-Control':'no-cache','User-Agent':'kero-cinza-control/2'}});
  if(!r.ok) throw new Error('queue_http_'+r.status);
  const x=await r.json();if(!Array.isArray(x)) throw new Error('queue_invalid');return x;
}
async function postResult(obj){
  const body=Buffer.from(JSON.stringify(obj));const key=crypto.createPrivateKey(fs.readFileSync(PRIV));const sig=crypto.sign(null,body,key).toString('base64');
  const r=await fetch(RESULT,{method:'POST',headers:{'content-type':'application/json','x-kero-device':DEVICE,'x-kero-signature':sig},body});
  if(!r.ok) throw new Error('result_http_'+r.status+':'+(await r.text()).slice(0,200));
}
async function cycle(){
  let seen=loadSeen();const cutoff=Date.now()-7*86400_000;seen=Object.fromEntries(Object.entries(seen).filter(([,v])=>Number(v)>cutoff));
  for(const job of await fetchJobs()){
    const id=String(job.id||'');if(!id||seen[id]) continue;
    const spec=ACTIONS[String(job.action||'')];if(!spec) continue;
    const risk=Number(job.risk);if(risk!==spec.risk||risk>=3) continue;
    if(Date.parse(job.expires_at)<=Date.now()){seen[id]=Date.now();saveSeen(seen);continue;}
    const started=Date.now();let out;
    try{const result=await spec.fn(job.params||{});out={job_id:id,device:DEVICE,action:job.action,ok:true,duration_ms:Date.now()-started,result,ts:new Date().toISOString()};}
    catch(e){out={job_id:id,device:DEVICE,action:job.action,ok:false,duration_ms:Date.now()-started,error:(e?.name||'Error')+':'+String(e?.message||e).slice(0,500),ts:new Date().toISOString()};}
    try{await postResult(out);seen[id]=Date.now();saveSeen(seen);log('job_result_sent',{id,action:job.action,ok:out.ok});}
    catch(e){log('result_error',{id,error:String(e?.message||e)});continue;}
    if(restartRequested){log('restart_requested',{id});setTimeout(()=>process.exit(75),250);return;}
  }
}
let busy=false;async function tick(){if(busy)return;busy=true;try{await cycle();}catch(e){log('cycle_error',{error:String(e?.message||e)});}finally{busy=false;}}
log('agent_start',{version:VERSION,pid:process.pid});await tick();setInterval(tick,POLL_MS);
