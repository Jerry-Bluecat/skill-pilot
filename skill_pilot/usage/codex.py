from .common import reads


def parse(row, names, session):
    payload = row.get('payload', {})
    if row.get('type') == 'session_meta':
        session = payload.get('id', session)
    if payload.get('type') not in {'custom_tool_call', 'function_call', 'local_shell_call'}:
        return session, set()
    if payload['type'] == 'local_shell_call':
        return session, reads('local_shell_call', payload, names)
    return session, reads(payload.get('name'), payload.get('arguments', payload.get('input')), names)
