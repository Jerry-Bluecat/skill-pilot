"""Incremental, durable, session-deduplicated usage ledger."""
import hashlib
import importlib
import json
import re
import sqlite3
import tempfile
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .common import Names, timestamp
from .. import operations, profiles
from ..store import PROJECT, guard, write_allowed

def reader(profile):
    return importlib.import_module(__name__ + '.' + profile['usage']['reader']) if profile['usage'] else None


class Ledger:
    def __init__(self, path):
        self.db = sqlite3.connect(path, timeout=.1)
        try:
            self.db.execute('PRAGMA journal_mode=WAL')
            self.db.executescript('''
                CREATE TABLE IF NOT EXISTS calls(agent TEXT, session TEXT, skill TEXT, first_used TEXT, last_used TEXT,
                    PRIMARY KEY(agent,session,skill));
                CREATE TABLE IF NOT EXISTS appearances(skill TEXT PRIMARY KEY, first_seen TEXT);
                CREATE TABLE IF NOT EXISTS scans(path TEXT PRIMARY KEY, agent TEXT, inode TEXT, size INTEGER,
                    mtime INTEGER, offset INTEGER, prefix TEXT, anchor TEXT, session TEXT, first_seen TEXT, last_seen TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY, value TEXT);
            ''')
        except sqlite3.Error:
            self.db.close()
            raise
        self.db.row_factory = sqlite3.Row

    def close(self):
        self.db.close()

    def appearance(self, name, date):
        if date:
            self.db.execute('INSERT INTO appearances VALUES(?,?) ON CONFLICT(skill) DO UPDATE SET first_seen=min(first_seen,excluded.first_seen)', (name,date))

    def call(self, agent, session, name, date):
        if date:
            self.db.execute('INSERT INTO calls VALUES(?,?,?,?,?) ON CONFLICT(agent,session,skill) DO UPDATE SET first_used=min(first_used,excluded.first_used), last_used=max(last_used,excluded.last_used)', (agent,session,name,date,date))
            self.appearance(name,date)

    @staticmethod
    def sample(path, offset):
        with path.open('rb') as f:
            prefix = hashlib.sha256(f.read(512)).hexdigest()
            f.seek(max(0,offset-512))
            anchor = hashlib.sha256(f.read(min(offset,512))).hexdigest()
        return prefix, anchor

    def scan(self, path, agent, names):
        parser = reader(profiles.by_id(names.home)[agent])
        info = path.stat()
        inode = str((info.st_dev,info.st_ino))
        saved = self.db.execute('SELECT * FROM scans WHERE path=?', (str(path),)).fetchone()
        if saved and saved['inode'] == inode and saved['size'] == info.st_size and saved['mtime'] == info.st_mtime_ns and not saved['error']:
            return 0, None
        offset = saved['offset'] if saved else 0
        if saved and saved['error']:
            offset = 0
        prefix, anchor = self.sample(path, offset)
        if saved and (saved['inode'] != inode or info.st_size < offset or saved['anchor'] != anchor or
                      (saved['size'] >= 512 and saved['prefix'] != prefix)):
            offset = 0
        session = saved['session'] if saved and offset else parser.session_name(path)
        first, last = (saved['first_seen'], saved['last_seen']) if saved and offset else (None,None)
        error, processed = None, 0
        def observe(date):
            nonlocal first, last
            if date:
                first = min(first,date) if first else date
                last = max(last,date) if last else date
        try:
            if hasattr(parser, 'decode'):
                decoded = parser.decode(path,offset,names.evidence_aliases)
                observe(timestamp(decoded['first'])); observe(timestamp(decoded['last']))
                for hint in decoded['hints']:
                    for name in names.paths(' '.join(hint['paths'])):
                        self.appearance(name,timestamp(hint['time']))
                    for name in hint.get('names',[]):
                        self.appearance(name,timestamp(hint['time']))
                for row in decoded['rows']:
                    session, found = parser.parse(row,names,session)
                    for name in found:
                        self.call(agent,session,name,timestamp(row.get('time')))
                processed = decoded['offset']-offset
                offset = decoded['offset']
                if decoded['incomplete']:
                    error = '有压缩片段尚未完整写入，暂不据此清理。'
            else:
                with path.open('rb') as f:
                    f.seek(offset)
                    while line := f.readline():
                        if not line.endswith(b'\n'):
                            error = '有记录尚未完整写入，暂不据此清理。'
                            break
                        offset += len(line); processed += len(line)
                        match = re.search(rb'"timestamp"\s*:\s*"([^"\\]+)"',line[:500])
                        date = timestamp(match[1].decode()) if match else None
                        observe(date)
                        mentioned = names.mentions(line)
                        if not parser.relevant(line, mentioned):
                            continue
                        row = json.loads(line)
                        session, found = parser.parse(row,names,session)
                        date = timestamp(row.get('timestamp')) or date
                        observe(date)
                        for name in mentioned:
                            self.appearance(name,date)
                        for name in found:
                            self.call(agent,session,name,date)
                        if b'SKILL.md' in line:
                            for name in names.paths(line.decode('utf-8').replace('\\"','"')):
                                self.appearance(name,date)
        except (ValueError, OSError, UnicodeError, KeyError, TypeError) as problem:
            error = '记录未完整读出（'+type(problem).__name__+'），暂不据此清理。'
        prefix, anchor = self.sample(path,offset)
        self.db.execute('INSERT OR REPLACE INTO scans VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                        (str(path),agent,inode,info.st_size,info.st_mtime_ns,offset,prefix,anchor,session,first,last,error))
        return processed, error


def mapping(home, registry):
    path = PROJECT / 'work/real-migration-preview.json'
    preview = json.loads(path.read_text()) if path.exists() else None
    return Names(home,registry,preview)


def recorded(database):
    """Read the existing ledger for assignment rows without starting another scan."""
    database = Path(database)
    try:
        with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True,timeout=.05)) as db:
            db.execute('BEGIN')
            if db.execute('SELECT value FROM settings WHERE name="complete"').fetchone() != ('1',):
                return None
            result = {}
            for name, agent, date in db.execute('SELECT skill,agent,max(last_used) FROM calls GROUP BY skill,agent'):
                result.setdefault(name,{})[agent] = date[:10]
            return result
    except (sqlite3.Error, OSError):
        return None


def report(home=None, database=None, now=None, progress=None):
    home, registry, agents = operations.load(home)
    catalog = profiles.by_id(home)
    parsers = {a: reader(catalog[a]) for a in agents}
    if database is None and not write_allowed(home):
        with tempfile.TemporaryDirectory(prefix='skill-pilot-usage-preview-') as temporary:
            return report(home,Path(temporary)/'usage.sqlite',now,progress)
    database = Path(database) if database else guard(home/'.skill-pilot/usage.sqlite',home)
    if not database.resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
        guard(database,home)
    database.parent.mkdir(parents=True,exist_ok=True)
    progress = progress if progress is not None else {}
    progress.update(running=True,done=0,total=0)
    ledger = Ledger(database)
    try:
        names = mapping(home,registry)
        from ..cleanup import installations
        known = installations(home,registry,[])
        names.evidence({n for n,row in known.items() if not row['date']})
        identity = hashlib.sha256(json.dumps([names.aliases,names.entries,names.evidence_aliases],sort_keys=True).encode()).hexdigest()
        previous = ledger.db.execute('SELECT value FROM settings WHERE name="mapping"').fetchone()
        if previous and previous['value'] != identity:
            ledger.db.execute('DELETE FROM scans')
        ledger.db.execute('INSERT OR REPLACE INTO settings VALUES("mapping",?)',(identity,))
        ledger.db.execute('INSERT OR REPLACE INTO settings VALUES("complete","0")'); ledger.db.commit()
        files = {a: sorted({p for r in (catalog[a]['usage'] or {}).get('roots', [])
                            for p in (home/r).rglob(parsers[a].FILE_GLOB)}) for a in agents}
        progress.update(running=True,done=0,total=sum(map(len,files.values())))
        coverage, bytes_read = {}, 0
        now = now or datetime.now(timezone.utc)
        cutoff = (now-timedelta(days=30)).isoformat()
        for agent in agents:
            if parsers[agent] is None:
                coverage[agent] = {'available':False,'message':catalog[agent]['usage_reason'],'files':0,'earliest':None,'latest':None,'errors':[]}
                continue
            paths = files[agent]
            errors = []
            for path in paths:
                count, error = ledger.scan(path,agent,names)
                bytes_read += count
                ledger.db.commit(); progress['done'] += 1
                if error:
                    errors.append({'file':str(path.relative_to(home)),'reason':error})
            current = [ledger.db.execute('SELECT first_seen,last_seen FROM scans WHERE path=?',(str(p),)).fetchone() for p in paths]
            earliest = min((r['first_seen'] for r in current if r and r['first_seen']),default=None)
            latest = max((r['last_seen'] for r in current if r and r['last_seen']),default=None)
            available = bool(paths) and not errors
            label = parsers[agent].COVERAGE_NOTE
            message = label+('，最早到 '+earliest[:10] if earliest else '，没有可读取的记录')
            if errors:
                message += '；有记录未读完整，统计不到'
            coverage[agent] = {'available':available,'message':message,'files':len(paths),'earliest':earliest,'latest':latest,'errors':errors}
        ledger.db.execute('INSERT OR REPLACE INTO settings VALUES("complete","1")'); ledger.db.commit()
        rows = []
        for name in sorted(registry['skills']):
            used = {r['agent']:r['last_used'] for r in ledger.db.execute('SELECT agent,max(last_used) AS last_used FROM calls WHERE skill=? GROUP BY agent',(name,))}
            last_agent = max(used,key=used.get) if used else None
            count = {r['agent']:r['n'] for r in ledger.db.execute('SELECT agent,count(*) AS n FROM calls WHERE skill=? AND last_used>=? GROUP BY agent',(name,cutoff))}
            first = ledger.db.execute('SELECT first_seen FROM appearances WHERE skill=?',(name,)).fetchone()
            rows.append({'name':name,'last_used':used,'last_agent':last_agent,'last_used_at':used.get(last_agent),
                         'sessions_30d':count,'first_seen':first['first_seen'] if first else None})
        return {'coverage':coverage,'skills':rows,'scanned_bytes':bytes_read,'checked_at':now.isoformat(),
                'ledger':str(database),'persistent':database.is_relative_to(home/'.skill-pilot')}
    finally:
        progress['running'] = False
        ledger.close()
