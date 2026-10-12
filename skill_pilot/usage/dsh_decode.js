const fs = require('node:fs'), z = require('node:zlib');
const bytes = fs.readFileSync(process.argv[2]);
const aliases = JSON.parse(process.argv[4] || '{}');
const mentionPatterns = Object.entries(aliases).map(([name,skill])=>[new RegExp('(^|[^A-Za-z0-9_.-])'+name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')+'(?=$|[^A-Za-z0-9_.-])'),skill]);
let offset = Number(process.argv[3]), pending = '', rows = [], hints = [], first = null, last = null, incomplete = false;
while (offset < bytes.length) {
  let part;
  try { part = z.zstdDecompressSync(bytes.subarray(offset), {info:true}); }
  catch { incomplete = true; break; }
  if (!part.engine.bytesWritten) throw new Error('No decoding progress');
  offset += part.engine.bytesWritten;
  pending += part.buffer.toString('utf8');
  let end;
  while ((end = pending.indexOf('\n')) >= 0) {
    const line = pending.slice(0, end); pending = pending.slice(end + 1);
    if (!line) continue;
    const r = JSON.parse(line), time = r.time ?? r.createdAt;
    if (typeof time === 'number') {first = first === null ? time : Math.min(first,time);last = last === null ? time : Math.max(last,time);}
    if (r.type === 'session' || (r.type === 'tool/call' && ['skill','read','read_file','bash','shell','terminal'].includes(r.data?.name))) rows.push(r);
    if (line.includes('SKILL.md')) hints.push({time, paths:line.match(/(?:~|\/)[^\s"'`<>]*?\/SKILL\.md/g) || []});
    const mentioned = mentionPatterns.filter(([pattern])=>pattern.test(line)).map(([,name])=>name);
    if (mentioned.length) hints.push({time, paths:[], names:mentioned});
  }
}
if (pending.trim()) throw new Error('Incomplete JSONL frame');
process.stdout.write(JSON.stringify({offset, rows, hints, first, last, incomplete}));
