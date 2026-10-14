"""Extract invocation identities only; never retain conversation text."""
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from .. import profiles


def timestamp(value):
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value, timezone.utc).isoformat()
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00')).astimezone(timezone.utc).isoformat()
    except (ValueError, TypeError, OverflowError):
        return None


class Names:
    def __init__(self, home, registry, preview=None):
        self.aliases = {n: n for n in registry['skills']}
        self.entries = {}
        for name, skill in registry['skills'].items():
            for entry in skill.get('entries', []) + skill.get('withdrawn_entries', []):
                self.entries[entry] = name
                self.aliases[Path(entry).name] = name
        for skill in (preview or {}).get('skills', []):
            if skill['name'] in registry['skills']:
                for entry in skill.get('entries', []):
                    self.entries[entry] = skill['name']
                    self.aliases[Path(entry).name] = skill['name']
        self.home = str(home)
        self.roots = {r + '/': any(p['nested'] for p in profiles.all_profiles(home) if r in p['skill_roots'])
                      for r in {r for p in profiles.all_profiles(home) for r in p['skill_roots']}}
        self.roots['.skill-pilot/store/'] = False
        self.readonly = profiles.readonly_roots(home)
        self.path_pattern = re.compile('(?:' + '|'.join(re.escape(r) for r in self.roots) +
                                       r')[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*/SKILL\.md|Developer/vendor/stop-that-shit-local/skills/stss/SKILL\.md')
        self.evidence_aliases = {}
        self.evidence_pattern = None

    def evidence(self, missing):
        self.evidence_aliases = {a:n for a,n in self.aliases.items() if n in missing}
        if self.evidence_aliases:
            self.evidence_pattern = re.compile(rb'(?<![A-Za-z0-9_.-])(' + b'|'.join(re.escape(a.encode()) for a in self.evidence_aliases) + rb')(?![A-Za-z0-9_.-])')

    def mentions(self, line):
        return {self.evidence_aliases[a.decode()] for a in self.evidence_pattern.findall(line)} if self.evidence_pattern else set()

    def name(self, value):
        return self.aliases.get(str(value).strip().removeprefix('/'))

    def path(self, value):
        value = str(value).replace('\\', '').rstrip('.,;)')
        if not value.endswith('/SKILL.md'):
            return None
        directory = value[:-len('/SKILL.md')]
        for root, nested in self.roots.items():
            if root in directory:
                tail = directory.split(root, 1)[1]
                entry = root + tail
                if any(Path(entry).is_relative_to(r) for r in self.readonly):
                    return None
                if entry in self.entries:
                    return self.entries[entry]
                if '/' not in tail or nested:
                    return self.name(Path(tail).name)
        if directory.endswith('Developer/vendor/stop-that-shit-local/skills/stss'):
            return self.name('stss')
        return None

    def paths(self, text):
        return {name for p in self.path_pattern.findall(str(text)) if (name := self.path(p))}


def arguments(value):
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value or {}


def shell_reads(command, names):
    """Only read commands, excluding task descriptions and edit/write payloads."""
    if isinstance(command, list):
        command = command[-1] if len(command) >= 3 and command[1] in {'-c','-lc'} else ' '.join(map(str, command))
    command = str(command)
    # A cat heredoc writes its body; example read commands inside it never run.
    command = re.sub(r'(?:^|\n)\s*cat[^\n]*<<-?\s*[\"\x27]?([A-Za-z0-9_]+)[\"\x27]?[^\n]*\n.*?\n\1(?:\n|$)', '\n', command, flags=re.S)
    found = set()
    for part in re.split(r'\s*(?:&&|;|\n)\s*', command):
        match = re.match(r'^\s*(cat|head|tail|sed|rg|grep|less|more|bat)\s', part)
        if match and not (match[1] == 'sed' and re.search(r'\s-i\b',part)):
            found |= names.paths(part.split('>',1)[0])
    # Python snippets that directly read a manifest also occur in older logs.
    for match in re.finditer(r'(?:Path\([\"\x27]([^\"\x27]+/SKILL\.md)[\"\x27]\)\.(?:read_text|read_bytes)\(|open\([\"\x27]([^\"\x27]+/SKILL\.md)[\"\x27]\s*(?:\)|,\s*[\"\x27]r[b+t]*[\"\x27]))', command):
        found |= names.paths(next(v for v in match.groups() if v))
    return found


def reads(tool, value, names):
    tool = str(tool).split('__')[-1].lower()
    args = arguments(value)
    if tool in {'read', 'read_file', 'view_file', 'read_text_file'} and isinstance(args, dict):
        return names.paths(args.get('file_path', args.get('path', args.get('AbsolutePath', ''))))
    if tool in {'exec_command', 'bash', 'shell', 'local_shell_call', 'run_command', 'terminal'} and isinstance(args, dict):
        action = args.get('action', args)
        return shell_reads(action.get('cmd', action.get('command', '')), names) if isinstance(action, dict) else set()
    if tool in {'exec', 'functions.exec'} and isinstance(args, str):
        found = set()
        # Extract only executable shell arguments, never titles or agent messages.
        for match in re.finditer(r'(?:[\"\x27]?(?:cmd|command)[\"\x27]?)\s*:\s*("(?:\\.|[^"\\])*"|\x27(?:\\.|[^\x27\\])*\x27)', args):
            literal = match[1]
            try:
                command = json.loads(literal) if literal[0] == '"' else literal[1:-1]
            except ValueError:
                command = literal[1:-1]
            found |= shell_reads(command, names)
        return found
    return set()
