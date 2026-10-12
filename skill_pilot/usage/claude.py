from .common import reads


def parse(row, names, session):
    session = row.get('sessionId', session)
    message = row.get('message', {})
    content = message.get('content', [])
    found = set()
    if row.get('type') == 'assistant' and isinstance(content, list):
        for block in content:
            if not isinstance(block, dict) or block.get('type') != 'tool_use':
                continue
            args = block.get('input', {})
            if block.get('name') == 'Skill':
                if name := names.name(args.get('skill', '')):
                    found.add(name)
            else:
                found |= reads(block.get('name'), args, names)
    if row.get('type') == 'user':
        texts = [content] if isinstance(content, str) else [b.get('text', '') for b in content if isinstance(b, dict) and b.get('type') == 'text']
        import re
        for text in texts:
            command = re.match(r'^\s*/([A-Za-z0-9_.:-]+)(?:\s|$)', text)
            command = command or re.search(r'<command-name>/([A-Za-z0-9_.:-]+)</command-name>', text)
            if command and (name := names.name(command[1])):
                found.add(name)
    return session, found
