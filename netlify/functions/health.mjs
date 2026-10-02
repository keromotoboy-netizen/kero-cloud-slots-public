export default async () => {
  return new Response(JSON.stringify({ok:true,service:'kero-netlify-slot',time:new Date().toISOString()}), {
    headers: {'content-type':'application/json'}
  });
};
