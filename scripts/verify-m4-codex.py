"""Exactly one real explanation and one real merge, with a tiny fake home."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests.test_updates import UpdateTests
from skill_pilot import operations, updates

fixture = UpdateTests(methodName='test_old_version_is_unmodified_and_check_is_read_only')
fixture.setUp()
evidence = {'calls': {'explanation': 0, 'merge': 0}}
try:
    fixture.modified()
    before = fixture.fingerprint()
    review = fixture.check()
    evidence['calls']['explanation'] += 1
    evidence['explanation'] = updates.explain(review, 'sample')['explanation']
    evidence['explanation_readonly'] = fixture.fingerprint() == before
    evidence['calls']['merge'] += 1
    merged = updates.prepare_merge(review, 'sample')
    evidence['merge_preview'] = merged
    evidence['merge_readonly'] = fixture.fingerprint() == before
    result = updates.apply(review, ['sample'], {'sample': 'merge'}, True, {'sample': merged['merge_id']})
    text = (fixture.local() / 'SKILL.md').read_text()
    evidence['both_changes_preserved'] = 'my local edit' in text and 'new upstream' in text
    operations.undo(result['id'], home=fixture.home)
    evidence['undo_exact'] = fixture.fingerprint() == before
    evidence['passed'] = all(evidence[k] for k in ['explanation_readonly','merge_readonly','both_changes_preserved','undo_exact'])
except Exception as error:
    evidence.update(passed=False, error=str(error))
finally:
    Path('work/m4-codex-acceptance.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2))
    fixture.doCleanups()
print(json.dumps(evidence, ensure_ascii=False, indent=2))
raise SystemExit(0 if evidence['passed'] else 1)
