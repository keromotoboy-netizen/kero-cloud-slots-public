import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';

const execFileP=promisify(execFile);
const HOME=os.homedir();
const BASE=path.join(process.env.LOCALAPPDATA||path.join(HOME,'AppData','Local'),'KeroControl');
const STATE=path.join(BASE,'seen.json');
const PRIV=path.join(BASE,'cinza-ed25519-private.pem');
const PUB=path.join(BASE,'cinza-ed25519-public.pem');
const LOG=path.join(BASE,'agent.log');
const SUPABASE='https://noqdjfuqaqlicugbqihv.supabase.co';
const APIKEY='sb_publishable_sM9x9lsULWy3TAm37NxWUQ_9oNXEoGr';
const RESULT='https://kero-public-slot.onrender.com/control/result';
const DEVICE='cinza';
const VERSION='2026.10.05.1';
const POLL_MS=60_000;
const PS='C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe';

fs.mkdirSync(BASE,{recursive:true});
function log(event,detail={}) {
  const row=JSON.stringify({ts:new Date().toISOString(),event,detail});
  fs.appendFileSync(LOG,row+'\n');
}
function loadSeen(){
  try{return JSON.parse(fs.readFileSync(STATE,'utf8'))||{};}catch{return {};}
}
function saveSeen(x){
  const t=STATE+'.tmp';
  fs.writeFileSync(t,JSON.stringify(x));
  fs.renameSync(t,STATE);
}
function ensureKeys(){
  if(fs.existsSync(PRIV)&&fs.existsSync(PUB)) return;
  const {privateKey,publicKey}=crypto.generateKeyPairSync('ed25519');
  fs.writeFileSync(PRIV,privateKey.export({type:'pkcs8',format:'pem'}),{mode:0o600});
  fs.writeFileSync(PUB,publicKey.export({type:'spki',format:'pem'}));
}
ensureKeys();

async function ps(script,timeout=20_000){
  const enc=Buffer.from("$ProgressPreference='SilentlyContinue';$OutputEncoding=[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new();"+script,'utf16le').toString('base64');
  const {stdout='',stderr=''}=await execFileP(PS,['-NoProfile','-NonInteractive','-EncodedCommand',enc],{timeout,windowsHide:true,maxBuffer:512*1024});
  return {stdout:String(stdout).slice(-12000),stderr:String(stderr).slice(-3000)};
}
async function actionVersion(){
  return {device:DEVICE,version:VERSION,node:process.version,user:process.env.USERNAME||'',host:os.hostname()};
}
async function actionStatus(){
  const r=await ps("$os=Get-CimInstance Win32_OperatingSystem;$cs=Get-CimInstance Win32_ComputerSystem;$d=Get-PSDrive C;[pscustomobject]@{host=$env:COMPUTERNAME;user=$env:USERNAME;uptime_s=[int]((Get-Date)-$os.LastBootUpTime).TotalSeconds;ram_total_gb=[math]::Round($cs.TotalPhysicalMemory/1GB,1);ram_free_gb=[math]::Round($os.FreePhysicalMemory*1KB/1GB,1);c_free_gb=[math]::Round($d.Free/1GB,1);tailscale=(Get-Service Tailscale -ErrorAction SilentlyContinue).Status.ToString();sshd=if(Get-Service sshd -ErrorAction SilentlyContinue){(Get-Service sshd).Status.ToString()}else{'Missing'}}|ConvertTo-Json -Compress");
  return r;
}
async function actionDisk(){
  return await ps("Get-PSDrive -PSProvider FileSystem|Select Name,@{n='UsedGB';e={[math]::Round($_.Used/1GB,1)}},@{n='FreeGB';e={[math]::Round($_.Free/1GB,1)}}|ConvertTo-Json -Compress");
}
async function actionProcessTop(){
  return await ps("Get-Process|Sort-Object WorkingSet64 -Descending|Select-Object -First 15 Name,Id,@{n='RAM_MB';e={[math]::Round($_.WorkingSet64/1MB,1)}},CPU|ConvertTo-Json -Compress");
}
async function actionTailscale(){
  const exe='C:\\Program Files\\Tailscale\\tailscale.exe';
  return await ps("& '"+exe+"' status --json | ConvertFrom-Json | Select-Object Self,@{n='PeerCount';e={$_.Peer.PSObject.Properties.Count}} | ConvertTo-Json -Compress -Depth 5");
}
async function actionUserPaths(){
  return {
    home:HOME,
    desktop:path.join(HOME,'Desktop'),
    downloads:path.join(HOME,'Downloads'),
    documents:path.join(HOME,'Documents'),
    localappdata:process.env.LOCALAPPDATA||''
  };
}
const ACTIONS={
  'cinza.version':{risk:1,fn:actionVersion},
  'cinza.status':{risk:1,fn:actionStatus},
  'cinza.disk':{risk:1,fn:actionDisk},
  'cinza.process.top':{risk:1,fn:actionProcessTop},
  'cinza.tailscale.status':{risk:1,fn:actionTailscale},
  'cinza.user.paths':{risk:1,fn:actionUserPaths},
};

async function fetchJobs(){
  const u=new URL(SUPABASE+'/rest/v1/kero_control_jobs_public');
  u.searchParams.set('select','id,target,action,params,risk,expires_at,created_at');
  u.searchParams.set('target','in.(cinza,any)');
  u.searchParams.set('order','created_at.asc');
  u.searchParams.set('limit','100');
  const r=await fetch(u,{headers:{apikey:APIKEY,Accept:'application/json','Cache-Control':'no-cache','User-Agent':'kero-cinza-control/1'}});
  if(!r.ok) throw new Error('queue_http_'+r.status);
  const x=await r.json();
  if(!Array.isArray(x)) throw new Error('queue_invalid');
  return x;
}
async function postResult(obj){
  const body=Buffer.from(JSON.stringify(obj));
  const privateKey=crypto.createPrivateKey(fs.readFileSync(PRIV));
  const sig=crypto.sign(null,body,privateKey).toString('base64');
  const r=await fetch(RESULT,{method:'POST',headers:{'content-type':'application/json','x-kero-device':DEVICE,'x-kero-signature':sig},body});
  if(!r.ok) throw new Error('result_http_'+r.status+':'+(await r.text()).slice(0,200));
}
async function cycle(){
  let seen=loadSeen();
  const cutoff=Date.now()-7*86400_000;
  seen=Object.fromEntries(Object.entries(seen).filter(([,v])=>Number(v)>cutoff));
  for(const job of await fetchJobs()){
    const id=String(job.id||'');
    if(!id||seen[id]) continue;
    const spec=ACTIONS[String(job.action||'')];
    if(!spec){continue;}
    const risk=Number(job.risk);
    if(risk!==spec.risk||risk>=3) continue;
    if(Date.parse(job.expires_at)<=Date.now()){seen[id]=Date.now();saveSeen(seen);continue;}
    const started=Date.now();
    let out;
    try{
      const result=await spec.fn(job.params||{});
      out={job_id:id,device:DEVICE,action:job.action,ok:true,duration_ms:Date.now()-started,result,ts:new Date().toISOString()};
    }catch(e){
      out={job_id:id,device:DEVICE,action:job.action,ok:false,duration_ms:Date.now()-started,error:(e?.name||'Error')+':'+String(e?.message||e).slice(0,500),ts:new Date().toISOString()};
    }
    try{
      await postResult(out);
      seen[id]=Date.now();saveSeen(seen);
      log('job_result_sent',{id,action:job.action,ok:out.ok});
    }catch(e){
      log('result_error',{id,error:String(e?.message||e)});
    }
  }
}
let busy=false;
async function tick(){
  if(busy) return;
  busy=true;
  try{await cycle();}catch(e){log('cycle_error',{error:String(e?.message||e)});}
  finally{busy=false;}
}
log('agent_start',{version:VERSION,pid:process.pid});
console.log(fs.readFileSync(PUB,'utf8').trim());
await tick();
setInterval(tick,POLL_MS);
