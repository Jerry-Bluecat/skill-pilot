"""Node 24 decodes concatenated frames; byte offsets stop at complete frames."""
import json
import subprocess
from pathlib import Path

from .common import arguments, reads


def decode(path, offset=0, evidence=None):
    decoder = Path(__file__).with_name('dsh_decode.js')
    process = subprocess.run(['node', str(decoder), str(path), str(offset), json.dumps(evidence or {})], capture_output=True, text=True, timeout=60)
    if process.returncode:
        raise ValueError('DSH 记录解码失败，不能据此清理。')
    return json.loads(process.stdout)


def parse(row, names, session):
    if row.get('type') == 'session':
        return row.get('id', session), set()
    if row.get('type') != 'tool/call':
        return session, set()
    data = row.get('data', {})
    args = arguments(data.get('arguments'))
    if data.get('name') == 'skill' and isinstance(args, dict):
        name = names.name(args.get('name', args.get('skill', '')))
        return session, {name} if name else set()
    return session, reads(data.get('name'), args, names)
