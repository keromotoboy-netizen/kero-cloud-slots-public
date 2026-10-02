import http from 'node:http';

const port = Number(process.env.PORT || 10000);
const server = http.createServer(async (req,res)=>{
  if(req.url === '/health'){
    res.writeHead(200,{'content-type':'application/json'});
    return res.end(JSON.stringify({ok:true,service:'kero-render-slot',time:new Date().toISOString()}));
  }
  if(req.url === '/site-smoke'){
    const urls=['https://keromotoboy.com.br','https://keromotoboy.com.br/rotas/','https://keromotoboy.com.br/calculadora/'];
    const results=await Promise.all(urls.map(async u=>{
      const t=Date.now();
      try{const r=await fetch(u,{redirect:'follow',signal:AbortSignal.timeout(20000)});return{url:u,ok:r.ok,status:r.status,ms:Date.now()-t}}
      catch(e){return{url:u,ok:false,status:0,ms:Date.now()-t,error:String(e.message||e)}}
    }));
    res.writeHead(results.every(x=>x.ok)?200:502,{'content-type':'application/json'});
    return res.end(JSON.stringify({ok:results.every(x=>x.ok),results}));
  }
  res.writeHead(200,{'content-type':'text/plain'});res.end('Kero public cloud slot');
});
server.listen(port,'0.0.0.0');
