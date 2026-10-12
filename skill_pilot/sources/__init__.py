"""Read-only source discovery. Never import code from downloaded skills."""
"""Normalize inherited installation records without changing the registry."""
import re
from pathlib import PurePosixPath


def normalize(source):
    source = source if isinstance(source, dict) else {'source': source}
    record = source.get('record', source)
    text = str(source.get('source', ''))
    if text in {'自制', '本机源码', '本机文档生成', '来源不明'}:
        return {'kind': 'skip', 'label': '自制，不检查更新'}
    if record.get('sourceType') == 'well-known':
        url = record.get('sourceUrl', '')
        if url.startswith('https://open.feishu.cn/lark-cli/skills/'):
            return {'kind': 'lark', 'label': '飞书官方', 'url': url,
                    'base_url': record.get('sourceBaseUrl', url.split('/.well-known/')[0])}
        return {'kind': 'skip', 'label': '自制，不检查更新'}
    repository = source.get('repository') or record.get('source', '')
    match = re.search(r'https://github.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)',
                      text + ' ' + str(record.get('sourceUrl', '')))
    if match:
        repository = match[1].removesuffix('.git')
    local = str(repository).startswith('file:///')
    if not local and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', str(repository)):
        return {'kind': 'skip', 'label': '自制，不检查更新'}
    folder = str(source.get('source_path', record.get('skillPath', '.')) or '.')
    path = PurePosixPath(folder)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('来源记录中的技能位置不正确。')
    if path.name == 'SKILL.md':
        path = path.parent
    return {'kind': 'github', 'repository': repository, 'path': str(path),
            'label': str(repository), 'url': repository if local else 'https://github.com/' + repository}
