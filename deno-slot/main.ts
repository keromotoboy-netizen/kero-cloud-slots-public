Deno.serve(async (req) => {
  const u = new URL(req.url);
  if (u.pathname === "/health") return Response.json({ ok: true, service: "kero-deno-slot", time: new Date().toISOString() });
  if (u.pathname === "/site-smoke") {
    const urls = ["https://keromotoboy.com.br","https://keromotoboy.com.br/rotas/","https://keromotoboy.com.br/calculadora/"];
    const results = await Promise.all(urls.map(async (url) => {
      const t = Date.now();
      try { const r = await fetch(url, { redirect: "follow" }); return { url, ok:r.ok, status:r.status, ms:Date.now()-t }; }
      catch(e) { return { url, ok:false, status:0, ms:Date.now()-t, error:String(e) }; }
    }));
    return Response.json({ ok: results.every(x=>x.ok), results }, { status: results.every(x=>x.ok) ? 200 : 502 });
  }
  return new Response("Kero Deno Cloud Slot");
});
