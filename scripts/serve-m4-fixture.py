"""Isolated browser acceptance; Codex endpoints use explicit test substitutes."""
import json
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_updates import UpdateTests
from skill_pilot import research
from skill_pilot.scan import scan
from skill_pilot.web.server import Dashboard

fixture = UpdateTests(methodName='test_old_version_is_unmodified_and_check_is_read_only')
fixture.setUp(); fixture.modified()
before = fixture.fingerprint()
server = Dashboard(scan(fixture.home))
Path('work/m4-ui-runtime.json').write_text(json.dumps({'home':str(fixture.home),'url':server.url}))
print('模拟看板已启动', flush=True)
try:
    with patch.object(research,'merge',side_effect=fixture.mock_merge), \
            patch.object(research,'explain',return_value='新版加入了上游的文字调整。你的本机修改会单独保留。脚本也有变化，请先核对。'):
        server.serve_forever(poll_interval=.1)
except KeyboardInterrupt:
    pass
finally:
    server.server_close()
    Path('work/m4-ui-final-state.json').write_text(json.dumps({'undo_exact':before==fixture.fingerprint()}))
    import shutil
    for review in server.update_reviews.values(): shutil.rmtree(review['temporary'],ignore_errors=True)
    fixture.doCleanups()
