import http from 'node:http';
import crypto from 'node:crypto';

const port = Number(process.env.PORT || 10000);
const MAX_BODY = 1_000_000;
const MAX_TEXT = 200_000;
const MAX_RESULT = 64_000;
const KIDS_PUBLIC_KEY = `-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEANb0DV7OTQnZnHS4DwC+YjjujOFf46kg9aTx8P8SpU2o=
-----END PUBLIC KEY-----`;
const controlResults = new Map();

const json=(res,code,obj)=>{
  const body=JSON.stringify(obj);
  res.writeHead(code,{
    'content-type':'application/json',
    'access-control-allow-origin':'*',
    'access-control-allow-methods':'GET,POST,OPTIONS',
    'access-control-allow-headers':'content-type,x-kero-worker-token,x-kero-device,x-kero-signature',
    'cache-control':'no-store'
  });
  res.end(body);
};

function secureEq(a,b){
  const aa=Buffer.from(String(a||'')), bb=Buffer.from(String(b||''));
  return aa.length===bb.length && aa.length>0 && crypto.timingSafeEqual(aa,bb);
}
async function readRaw(req,limit=MAX_BODY){
  let size=0, chunks=[];
  for await (const chunk of req){
    size += chunk.length;
    if(size>limit) throw new Error('payload_too_large');
    chunks.push(chunk);
  }
  return Buffer.concat(chunks);
}
async function readJson(req){
  return JSON.parse((await readRaw(req)).toString('utf8')||'{}');
}
function text(v){
  const s=v==null?'':String(v);
  if(s.length>MAX_TEXT) throw new Error('payload_too_large');
  return s;
}
function sha256buf(buf){return crypto.createHash('sha256').update(buf).digest('hex')}
function verifyKids(raw,signature){
  try{
    const sig=Buffer.from(String(signature||''),'base64');
    return sig.length>0 && crypto.verify(null,raw,KIDS_PUBLIC_KEY,sig);
  }catch{return false}
}
function pruneResults(){
  const cutoff=Date.now()-6*60*60*1000;
  for(const [k,v] of controlResults){
    if(v.receivedAt<cutoff) controlResults.delete(k);
  }
  while(controlResults.size>200) controlResults.delete(controlResults.keys().next().value);
}

const tasks={
  health:()=>({ok:true,worker:'render-free-public',node:process.version,arch:process.arch}),
  sha256:p=>{const s=text(p?.text);return{sha256:sha256buf(Buffer.from(s)),bytes:Buffer.byteLength(s)}},
  'text-stats':p=>{
    const s=text(p?.text), words=s.trim()?s.trim().split(/\s+/):[];
    return {chars:s.length,bytes:Buffer.byteLength(s),words:words.length,lines:s? s.split(/\r?\n/).length:0,unique_words:new Set(words.map(x=>x.toLocaleLowerCase())).size};
  },
  'json-summary':p=>{
    const d=p?.data, raw=JSON.stringify(d);
    if(Buffer.byteLength(raw)>MAX_BODY) throw new Error('payload_too_large');
    const out={type:Array.isArray(d)?'array':d===null?'null':typeof d,bytes:Buffer.byteLength(raw)};
    if(Array.isArray(d)) out.items=d.length;
    else if(d&&typeof d==='object'){out.keys=Object.keys(d).sort().slice(0,200);out.key_count=Object.keys(d).length}
    return out;
  },
  'json-normalize':p=>{
    const sort=x=>Array.isArray(x)?x.map(sort):(x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,sort(x[k])])):x);
    const raw=JSON.stringify(sort(p?.data));
    if(Buffer.byteLength(raw)>MAX_RESULT) throw new Error('result_too_large');
    return {json:raw,sha256:sha256buf(Buffer.from(raw))};
  },
  manifest:p=>{
    const items=p?.items;
    if(!Array.isArray(items)||items.length>500) throw new Error('invalid_items');
    return {count:items.length,items:items.map((it,i)=>{
      if(!it||typeof it!=='object') throw new Error('invalid_item_'+i);
      const content=text(it.content), path=text(it.path).slice(0,500);
      return {path,bytes:Buffer.byteLength(content),sha256:sha256buf(Buffer.from(content))};
    })};
  }
};

const server=http.createServer(async(req,res)=>{
  try{
    if(req.method==='OPTIONS') return json(res,204,{});
    if(req.method==='GET' && req.url==='/health') return json(res,200,{ok:true,service:'kero-render-slot',time:new Date().toISOString()});
    if(req.method==='GET' && req.url==='/control/health') return json(res,200,{ok:true,service:'kero-control-result-relay',verification:'ed25519',stored:controlResults.size,time:new Date().toISOString()});
    if(req.method==='GET' && req.url?.startsWith('/control/result/')){
      pruneResults();
      const id=decodeURIComponent(req.url.slice('/control/result/'.length).split('?')[0]);
      const entry=controlResults.get(id);
      if(!entry) return json(res,404,{ok:false,error:'not_found'});
      const b=Buffer.from(JSON.stringify(entry.body));
      return json(res,200,{
        ok:true,job_id:id,device:entry.body?.device,action:entry.body?.action,
        job_ok:entry.body?.ok,ts:entry.body?.ts,duration_ms:entry.body?.duration_ms,
        result_sha256:sha256buf(b),received_at:new Date(entry.receivedAt).toISOString()
      });
    }
    if(req.method==='POST' && req.url==='/control/result'){
      const raw=await readRaw(req,128_000);
      if(req.headers['x-kero-device']!=='kids') return json(res,403,{ok:false,error:'unknown_device'});
      if(!verifyKids(raw,req.headers['x-kero-signature'])) return json(res,401,{ok:false,error:'bad_signature'});
      const body=JSON.parse(raw.toString('utf8')||'{}');
      const jid=String(body?.job_id||'');
      if(!/^[A-Za-z0-9._:-]{8,128}$/.test(jid)) return json(res,400,{ok:false,error:'bad_job_id'});
      if(body?.device!=='kids') return json(res,400,{ok:false,error:'device_mismatch'});
      controlResults.set(jid,{body,receivedAt:Date.now()});
      pruneResults();
      console.log('KERO_CONTROL_RESULT '+JSON.stringify(body));
      return json(res,202,{ok:true,accepted:true,job_id:jid});
    }
    if(req.method==='GET' && req.url==='/site-smoke'){
      const urls=['https://keromotoboy.com.br','https://keromotoboy.com.br/rotas/','https://keromotoboy.com.br/calculadora/'];
      const results=await Promise.all(urls.map(async u=>{
        const t=Date.now();
        try{const r=await fetch(u,{redirect:'follow',signal:AbortSignal.timeout(20000)});return{url:u,ok:r.ok,status:r.status,ms:Date.now()-t}}
        catch(e){return{url:u,ok:false,status:0,ms:Date.now()-t,error:String(e.message||e)}}
      }));
      return json(res,results.every(x=>x.ok)?200:502,{ok:results.every(x=>x.ok),results});
    }
    if(req.method==='GET' && req.url==='/benchmark'){
      const t=Date.now(); let x=0;
      for(let i=0;i<5e7;i++) x=(x+i)%1000000007;
      return json(res,200,{ok:true,ms:Date.now()-t,x,arch:process.arch,platform:process.platform});
    }
    if(req.method==='POST' && req.url==='/execute'){
      if(!secureEq(req.headers['x-kero-worker-token'],process.env.KERO_WORKER_TOKEN)) return json(res,401,{ok:false,error:'unauthorized'});
      const body=await readJson(req), task=String(body?.task||''), fn=tasks[task];
      if(!fn) return json(res,400,{ok:false,error:'task_not_allowlisted'});
      const result=await fn(body?.payload||{});
      if(Buffer.byteLength(JSON.stringify(result))>MAX_RESULT) throw new Error('result_too_large');
      return json(res,200,{ok:true,task,result});
    }
    return json(res,404,{ok:false,error:'not_found'});
  }catch(e){
    return json(res,400,{ok:false,error:String(e?.message||e).slice(0,500)});
  }
});
server.listen(port,'0.0.0.0');
