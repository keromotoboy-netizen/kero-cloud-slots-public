import http from 'node:http';

const port = Number(process.env.PORT || 10000);
const json=(res,code,obj)=>{
  res.writeHead(code,{
    'content-type':'application/json',
    'access-control-allow-origin':'*',
    'cache-control':'no-store'
  });
  res.end(JSON.stringify(obj));
};
const server = http.createServer(async (req,res)=>{
  if(req.method==='OPTIONS'){
    res.writeHead(204,{'access-control-allow-origin':'*','access-control-allow-methods':'GET,OPTIONS'});
    return res.end();
  }
  if(req.url === '/health'){
    return json(res,200,{ok:true,service:'kero-render-slot',time:new Date().toISOString()});
  }
  if(req.url === '/site-smoke'){
    const urls=['https://keromotoboy.com.br','https://keromotoboy.com.br/rotas/','https://keromotoboy.com.br/calculadora/'];
    const results=await Promise.all(urls.map(async u=>{
      const t=Date.now();
      try{const r=await fetch(u,{redirect:'follow',signal:AbortSignal.timeout(20000)});return{url:u,ok:r.ok,status:r.status,ms:Date.now()-t}}
      catch(e){return{url:u,ok:false,status:0,ms:Date.now()-t,error:String(e.message||e)}}
    }));
    return json(res,results.every(x=>x.ok)?200:502,{ok:results.every(x=>x.ok),results});
  }
  if(req.url === '/benchmark'){
    const t=Date.now(); let x=0;
    for(let i=0;i<5e7;i++) x=(x+i)%1000000007;
    return json(res,200,{ok:true,ms:Date.now()-t,x,arch:process.arch,platform:process.platform});
  }
  res.writeHead(200,{'content-type':'text/plain','access-control-allow-origin':'*'});res.end('Kero public cloud slot');
});
server.listen(port,'0.0.0.0');
