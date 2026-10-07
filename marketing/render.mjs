import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import sharp from 'sharp';

const root = process.cwd();
const briefsDir = path.join(root, 'marketing', 'briefs');
const outDir = path.join(root, 'marketing', 'generated');
fs.mkdirSync(briefsDir, { recursive: true });
fs.mkdirSync(outDir, { recursive: true });

const esc = (s='') => String(s)
  .replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')
  .replaceAll('"','&quot;').replaceAll("'","&apos;");

function wrapText(text, maxChars=28) {
  const words = String(text || '').trim().split(/\s+/).filter(Boolean);
  const lines = [];
  let line = '';
  for (const w of words) {
    const next = line ? line + ' ' + w : w;
    if (next.length > maxChars && line) { lines.push(line); line = w; }
    else line = next;
  }
  if (line) lines.push(line);
  return lines.slice(0, 8);
}

function tspans(lines, x, y, size, lineHeight, weight=700, fill='#ffffff') {
  return lines.map((l,i) =>
    `<text x="${x}" y="${y + i*lineHeight}" font-family="Arial,Helvetica,sans-serif" font-size="${size}" font-weight="${weight}" fill="${fill}">${esc(l)}</text>`
  ).join('');
}

function dimensions(format) {
  if (format === 'feed45') return [1080,1350];
  if (format === 'square') return [1080,1080];
  return [1080,1920];
}

function svgFor(b) {
  const [w,h] = dimensions(b.format === 'reel' ? 'story' : b.format);
  const pad = Math.round(w * 0.07);
  const yellow = '#A9822A', black = '#080808', white = '#F4F1E8', gray = '#D8D2C4';

  if (b.kind === 'review') {
    const quote = wrapText(b.quote, b.format==='square'?24:30);
    const detail = wrapText(b.detail || 'Experiência real de cliente Kero.', b.format==='square'?34:42);
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
      <rect width="100%" height="100%" fill="${black}"/>
      <polygon points="0,${Math.round(h*.62)} ${w},${Math.round(h*.48)} ${w},${h} 0,${h}" fill="${yellow}"/>
      <text x="${pad}" y="${pad+40}" font-family="Arial,Helvetica,sans-serif" font-size="42" font-weight="900" fill="${white}">KERO <tspan fill="${yellow}">MOTOBOY</tspan></text>
      <text x="${pad}" y="${Math.round(h*.25)}" font-family="Arial,Helvetica,sans-serif" font-size="54" font-weight="900" fill="${yellow}">★★★★★</text>
      ${tspans(quote,pad,Math.round(h*.34),b.format==='square'?44:62,b.format==='square'?54:74,900,white)}
      <text x="${pad}" y="${Math.round(h*.62)}" font-family="Arial,Helvetica,sans-serif" font-size="34" font-weight="800" fill="${black}">${esc(b.reviewer || 'Cliente Kero')}</text>
      ${tspans(detail,pad,Math.round(h*.68),28,38,700,black)}
      <rect x="${pad}" y="${h-pad-90}" rx="18" ry="18" width="${Math.min(w-pad*2,720)}" height="72" fill="${black}"/>
      <text x="${pad+24}" y="${h-pad-43}" font-family="Arial,Helvetica,sans-serif" font-size="28" font-weight="900" fill="${white}">${esc(b.cta || 'Fale com a Kero no WhatsApp')}</text>
    </svg>`;
  }

  if (b.kind === 'faq') {
    const q = wrapText(b.question, b.format==='square'?24:28);
    const a = wrapText(b.answer, b.format==='square'?34:40);
    const p = wrapText(b.proof || 'Acompanhamento humano do início ao fim.', 42);
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
      <rect width="100%" height="100%" fill="${yellow}"/>
      <text x="${pad}" y="${pad+40}" font-family="Arial,Helvetica,sans-serif" font-size="42" font-weight="900" fill="${black}">KERO MOTOBOY</text>
      <rect x="${pad}" y="${Math.round(h*.18)}" rx="28" ry="28" width="360" height="62" fill="${black}"/>
      <text x="${pad+22}" y="${Math.round(h*.18)+42}" font-family="Arial,Helvetica,sans-serif" font-size="24" font-weight="900" fill="${white}">${esc(b.kicker || 'PERGUNTA RÁPIDA')}</text>
      ${tspans(q,pad,Math.round(h*.32),b.format==='square'?48:68,b.format==='square'?58:78,900,black)}
      ${tspans(a,pad,Math.round(h*.55),b.format==='square'?28:36,b.format==='square'?38:48,700,black)}
      ${tspans(p,pad,Math.round(h*.76),26,36,800,black)}
      <text x="${pad}" y="${h-pad-30}" font-family="Arial,Helvetica,sans-serif" font-size="28" font-weight="900" fill="${black}">${esc(b.cta || 'Chame a Kero e peça seu orçamento.')}</text>
    </svg>`;
  }

  if (b.kind === 'photo') {
    const headline = wrapText(b.headline, b.format==='square'?22:26);
    const subhead = wrapText(b.subhead || '', b.format==='square'?34:40);
    const proof = wrapText(b.proof || '', 42);
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
      <defs>
        <linearGradient id="fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#080808" stop-opacity="0.18"/>
          <stop offset="55%" stop-color="#080808" stop-opacity="0.45"/>
          <stop offset="100%" stop-color="#080808" stop-opacity="0.94"/>
        </linearGradient>
      </defs>
      <rect width="100%" height="100%" fill="url(#fade)"/>
      <rect x="${pad}" y="${pad}" width="${w-pad*2}" height="5" fill="#A9822A"/>
      <text x="${pad}" y="${pad+60}" font-family="Arial,Helvetica,sans-serif" font-size="36" font-weight="900" fill="#F4F1E8">KERO <tspan fill="#A9822A">MOTOBOY</tspan></text>
      <text x="${pad}" y="${Math.round(h*.56)}" font-family="Arial,Helvetica,sans-serif" font-size="27" font-weight="900" fill="#A9822A">${esc(b.eyebrow || '')}</text>
      ${tspans(headline,pad,Math.round(h*.64),b.format==='square'?48:68,b.format==='square'?58:78,900,white)}
      ${tspans(subhead,pad,Math.round(h*.79),b.format==='square'?26:32,b.format==='square'?36:42,700,white)}
      ${tspans(proof,pad,Math.round(h*.90),24,34,800,'#C7A344')}
    </svg>`;
  }

  const headline = wrapText(b.headline, b.format==='square'?22:26);
  const subhead = wrapText(b.subhead, b.format==='square'?34:40);
  const proof = wrapText(b.proof || 'São Paulo • Grande SP • Interior • Litoral', 42);
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}">
    <rect width="100%" height="100%" fill="${black}"/>
    <polygon points="${Math.round(w*.63)},0 ${w},0 ${w},${h} ${Math.round(w*.82)},${h}" fill="${yellow}"/>
    <text x="${pad}" y="${pad+40}" font-family="Arial,Helvetica,sans-serif" font-size="42" font-weight="900" fill="${white}">KERO MOTOBOY</text>
    <text x="${pad}" y="${Math.round(h*.27)}" font-family="Arial,Helvetica,sans-serif" font-size="28" font-weight="900" fill="${yellow}">${esc(b.eyebrow || 'ENTREGA URGENTE')}</text>
    ${tspans(headline,pad,Math.round(h*.36),b.format==='square'?48:72,b.format==='square'?58:82,900,white)}
    ${tspans(subhead,pad,Math.round(h*.62),b.format==='square'?28:36,b.format==='square'?38:48,700,gray)}
    ${tspans(proof,pad,Math.round(h*.78),26,36,800,white)}
    <rect x="${pad}" y="${h-pad-100}" rx="18" ry="18" width="600" height="78" fill="${yellow}"/>
    <text x="${pad+26}" y="${h-pad-49}" font-family="Arial,Helvetica,sans-serif" font-size="30" font-weight="900" fill="${black}">${esc(b.cta || 'Solicite seu orçamento')}</text>
  </svg>`;
}

const files = fs.readdirSync(briefsDir).filter(f => f.endsWith('.json')).sort();
const manifest = [];
for (const file of files) {
  const parsed = JSON.parse(fs.readFileSync(path.join(briefsDir,file),'utf8'));
  const briefs = Array.isArray(parsed) ? parsed : [parsed];
  for (const b of briefs) {
  if (b.privacy !== 'PUBLIC_SAFE') continue;
  if (!/^[a-zA-Z0-9._-]+$/.test(b.id || '')) throw new Error('invalid brief id: '+b.id);
  if (!['review','faq','urgencia','photo'].includes(b.kind)) throw new Error('invalid kind: '+b.kind);
  if (!['story','feed45','square','reel'].includes(b.format)) throw new Error('invalid format: '+b.format);

  const svg = svgFor(b);
  const jpgPath = path.join(outDir, b.id + '.jpg');
  let base;
  if (b.kind === 'photo' && b.photo_url) {
    const res = await fetch(b.photo_url);
    if (!res.ok) throw new Error('photo fetch failed '+res.status+' '+b.id);
    const buf = Buffer.from(await res.arrayBuffer());
    const [w,h] = dimensions(b.format === 'reel' ? 'story' : b.format);
    base = sharp(buf).resize(w,h,{fit:'cover',position:'centre'});
  } else {
    const [w,h] = dimensions(b.format === 'reel' ? 'story' : b.format);
    base = sharp({create:{width:w,height:h,channels:3,background:'#080808'}});
  }
  await base.composite([{input:Buffer.from(svg),top:0,left:0}]).jpeg({quality:92}).toFile(jpgPath);

  const item = {
    id:b.id, kind:b.kind, format:b.format,
    jpg:`https://raw.githubusercontent.com/${process.env.GITHUB_REPOSITORY || 'keromotoboy-netizen/kero-cloud-slots-public'}/main/marketing/generated/${b.id}.jpg`
  };

  if (b.format === 'reel') {
    const mp4Path = path.join(outDir, b.id + '.mp4');
    if (!fs.existsSync(mp4Path)) {
      try {
        execFileSync('ffmpeg',[
          '-y','-loop','1','-i',jpgPath,
          '-t',String(b.duration_seconds || 8),
          '-vf','scale=1080:1920,format=yuv420p,fade=t=in:st=0:d=0.35,fade=t=out:st=7.2:d=0.5',
          '-r','30','-c:v','libx264','-pix_fmt','yuv420p','-movflags','+faststart',mp4Path
        ],{stdio:'inherit'});
      } catch (e) {
        console.warn('ffmpeg unavailable; preserving existing reel asset only:', b.id);
      }
    }
    if (fs.existsSync(mp4Path)) {
      item.mp4=`https://raw.githubusercontent.com/${process.env.GITHUB_REPOSITORY || 'keromotoboy-netizen/kero-cloud-slots-public'}/main/marketing/generated/${b.id}.mp4`;
    }
  }
  manifest.push(item);
  }
}
fs.writeFileSync(path.join(outDir,'manifest.json'), JSON.stringify({generated_at:new Date().toISOString(),items:manifest},null,2)+'\n');
console.log(JSON.stringify(manifest,null,2));
