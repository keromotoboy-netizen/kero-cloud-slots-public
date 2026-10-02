import http from 'node:http';

const PORT = Number(process.env.PORT || 8080);
const urls = [
  'https://keromotoboy.com.br',
  'https://keromotoboy.com.br/rotas/',
  'https://keromotoboy.com.br/calculadora/'
];

async function smoke() {
  const results = await Promise.all(urls.map(async (url) => {
    const t = Date.now();
    try {
      const r = await fetch(url, { redirect: 'follow', signal: AbortSignal.timeout(20000) });
      return { url, ok: r.ok, status: r.status, ms: Date.now() - t };
    } catch (e) {
      return { url, ok: false, status: 0, ms: Date.now() - t, error: String(e.message || e) };
    }
  }));
  return { ok: results.every(x => x.ok), results };
}

http.createServer(async (req,res) => {
  if (req.url === '/health') {
    res.writeHead(200, {'content-type':'application/json'});
    return res.end(JSON.stringify({ ok:true, service:'kero-universal-cloud-slot', time:new Date().toISOString() }));
  }
  if (req.url === '/site-smoke') {
    const out = await smoke();
    res.writeHead(out.ok ? 200 : 502, {'content-type':'application/json'});
    return res.end(JSON.stringify(out));
  }
  if (req.url === '/benchmark') {
    const t=Date.now(); let x=0; for(let i=0;i<5e7;i++) x=(x+i)%1000000007;
    res.writeHead(200, {'content-type':'application/json'});
    return res.end(JSON.stringify({ok:true,ms:Date.now()-t,x,arch:process.arch,platform:process.platform}));
  }
  res.writeHead(200, {'content-type':'text/plain'});
  res.end('Kero universal cloud slot');
}).listen(PORT,'0.0.0.0');
