"""All browser mutations use this disposable, synthetic home and local upstream."""
import json
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from skill_pilot import operations, store
from skill_pilot.sources import github
from skill_pilot.web.server import Dashboard
from skill_pilot.scan import scan

with tempfile.TemporaryDirectory(prefix='skill-pilot-m7-browser-') as temporary:
    home = Path(temporary).resolve()
    def skill(path, name, body):
        path.mkdir(parents=True)
        (path/'SKILL.md').write_text(f'---\nname: {name}\ndescription: 示例技能\n---\n{body}\n')
    for name in ['grill-me', 'grilling', 'other']:
        skill(home/'.codex/skills'/name, name, '参考 grilling' if name=='grill-me' else '正文')
    (home/'.agents').mkdir()
    (home/'.agents/.skill-lock.json').write_text(json.dumps({'skills':{n:{'sourceUrl':'自制'} for n in ['grill-me','grilling','other','sample']}}))
    store.apply(store.preview(home)['plan_id'], home)
    repository = home/'repository'
    skill(repository/'sample', 'sample', '原来的说明')
    github.git(repository,'init','-q')
    def commit():
        github.git(repository,'add','.')
        github.git(repository,'-c','user.name=Fixture','-c','user.email=fixture@local','-c','commit.gpgsign=false','commit','-qm','fixture')
    commit()
    review = github.inspect(repository.as_uri())
    operations.install(review,['sample'],['codex'],home=home)
    shutil.rmtree(review['temporary'])
    local = home/'.skill-pilot/store/sample/SKILL.md'
    local.write_text(local.read_text()+'我修改的说明\n')
    upstream = repository/'sample/SKILL.md'
    upstream.write_text(upstream.read_text().replace('原来的说明','上游新版说明'))
    scripts = repository/'sample/scripts'
    scripts.mkdir()
    (scripts/'task.sh').write_text('#!/bin/sh\ncurl https://example.test\nrm -rf temporary\n')
    (scripts/'task.sh').chmod(0o755)
    commit()
    operations.bootstrap(home)
    with patch('skill_pilot.research.ask',side_effect=AssertionError('默认流程不能调用 AI')):
        server=Dashboard(scan(home))
        Path(PROJECT/'work/m7-ui-runtime.json').write_text(json.dumps({'url':server.url,'home':str(home)}))
        print('模拟看板已就绪',flush=True)
        try: server.serve_forever(poll_interval=.1)
        except KeyboardInterrupt: pass
        finally: server.server_close()
