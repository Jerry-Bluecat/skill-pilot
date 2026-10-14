from .common import reads

FILE_GLOB = '*.jsonl'
COVERAGE_NOTE = 'Codex 含归档记录'


def session_name(path):
    return path.stem


def relevant(line, mentioned):
    return mentioned or any(token in line for token in (b'SKILL.md', b'"Skill"', b'"session_meta"'))


def parse(row, names, session):
    payload = row.get('payload', {})
    if row.get('type') == 'session_meta':
        session = payload.get('id', session)
    if payload.get('type') not in {'custom_tool_call', 'function_call', 'local_shell_call'}:
        return session, set()
    if payload['type'] == 'local_shell_call':
        return session, reads('local_shell_call', payload, names)
    return session, reads(payload.get('name'), payload.get('arguments', payload.get('input')), names)
