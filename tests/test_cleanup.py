from tests import set_up_home
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from skill_pilot import cleanup, operations, store
from skill_pilot.scan import content_digest
from skill_pilot.sync import visibility


class CleanupTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='skill-pilot-m5-cleanup-');self.addCleanup(self.tmp.cleanup)
        set_up_home(self, Path(self.tmp.name))
        self.now=datetime.now(timezone.utc)
        self.names=['candidate','kept','young','unknown','no-date','recent','parent','dep','deep','unassigned','dsh-only']
        for name in self.names:
            p=self.home/'.codex/skills'/name;p.mkdir(parents=True)
            (p/'SKILL.md').write_text(f'---\nname: {name}\ndescription: hello\n---\ncontent\n')
        (self.home/'.codex/config.toml').write_text('# preserve\n[skills]\nconfig=[{name="plugin:own",enabled=false}]\n')
        store.apply(store.preview(self.home)['plan_id'],self.home)
        operations.apply_assign([{'skill':'unassigned','agent':'codex','enabled':False},
            {'skill':'unknown','agent':'antigravity','enabled':True},
            {'skill':'dsh-only','agent':'codex','enabled':False},
            {'skill':'dsh-only','agent':'dsh','enabled':True}],confirmed=True,home=self.home)
        _,reg,_=operations.load(self.home)
        reg['skills']['parent']['requires']=['dep'];reg['skills']['dep']['requires']=['deep']
        reg['skills']['deep']['requires']=['dep']  # cycles terminate
        old=(self.now-timedelta(days=100)).isoformat()
        for name in self.names:
            reg['skills'][name]['installed_at']=old
        reg['skills']['kept']['kept_at']=(self.now-timedelta(days=5)).isoformat()
        p=self.home/'.skill-pilot/registry.json';p.write_text(json.dumps(reg))
        lock={n:{'installedAt':old} for n in self.names if n!='no-date'}
        lock['young']['installedAt']=(self.now-timedelta(days=59)).isoformat()
        path=self.home/'.agents/.skill-lock.json';path.parent.mkdir(exist_ok=True);path.write_text(json.dumps({'skills':lock}))
        operations._commit(self.home,reg,self.names,[],'fixture metadata')
        self.data={'coverage':{a:{'available':a!='antigravity','message':'test'} for a in ['codex','claude','dsh','antigravity']},
                   'skills':[{'name':n,'last_used':{},'last_used_at':None,'last_agent':None,'first_seen':None} for n in self.names]}
        for s in self.data['skills']:
            if s['name'] in {'recent','parent'}:
                s.update(last_used={'claude':self.now.isoformat()},last_agent='claude',last_used_at=self.now.isoformat())

    def preview(self):
        return cleanup.preview(self.home,now=self.now,usage_data=self.data)

    def fingerprint(self):
        paths=['.codex/skills','.agents/skills','.claude/skills','.gemini/config/skills','.codex/config.toml',
               '.skill-pilot/registry.json','.skill-pilot/bases','.agents/.skill-lock.json']
        return {p:store.physical_state(self.home/p) for p in paths}|{'store':content_digest(self.home/'.skill-pilot/store')}

    def test_all_candidate_conditions_transitive_protection_and_missing_evidence(self):
        view=self.preview()
        self.assertEqual({s['name'] for s in view['candidates']},{'candidate','dsh-only'})
        reasons={r['name']:r['reasons'] for r in view['excluded']}
        self.assertIn('尚未分配',reasons['unassigned'])
        self.assertIn('分配给了统计不到的助手',reasons['unknown'])
        self.assertIn('入库未满 60 天或时间缺证据',reasons['young'])
        self.assertIn('入库未满 60 天或时间缺证据',reasons['no-date'])
        self.assertIn('60 天内用过',reasons['recent'])
        self.assertIn('60 天内选择过留下',reasons['kept'])
        self.assertIn('近期使用技能的依赖',reasons['dep']);self.assertIn('近期使用技能的依赖',reasons['deep'])
        self.assertEqual(view['savings']['codex'],5);self.assertEqual(view['savings']['dsh'],5)

    def test_leave_resets_timer_then_reappears_after_60_days(self):
        with patch.object(cleanup.usage,'report',return_value=self.data):
            result=cleanup.apply(['candidate','dsh-only'],True,self.home)
        self.assertEqual(result['withdrawn'],[])
        after=self.preview();self.assertEqual(after['candidates'],[])
        # Advance beyond the new keep dates without making other exclusions eligible.
        _,reg,_=operations.load(self.home)
        future=max(datetime.fromisoformat(reg['skills'][n]['kept_at']) for n in ['candidate','dsh-only'])+timedelta(days=60,seconds=1)
        view=cleanup.preview(self.home,now=future,usage_data=self.data)
        self.assertTrue({'candidate','dsh-only'}<={s['name'] for s in view['candidates']})

    def test_cleanup_withdrawn_restore_and_both_undos_are_exact(self):
        before=self.fingerprint();config=(self.home/'.codex/config.toml').read_bytes()
        with patch.object(cleanup.usage,'report',return_value=self.data):
            result=cleanup.apply(['candidate'],True,self.home)
        self.assertEqual(result['withdrawn'],['dsh-only'])
        self.assertTrue((self.home/'.skill-pilot/store/dsh-only/SKILL.md').exists())
        self.assertFalse((self.home/'.agents/skills/dsh-only').exists())
        self.assertNotIn(b'{ name = "dsh-only", enabled = false }',(self.home/'.codex/config.toml').read_bytes())
        view=self.preview();self.assertEqual([s['name'] for s in view['withdrawn']],['dsh-only'])
        withdrawn=self.fingerprint()
        restored=cleanup.restore(['dsh-only'],self.home)
        self.assertIn('dsh-only',visibility(self.home)['dsh']['available'])
        self.assertNotIn('dsh-only',visibility(self.home)['codex']['available'])
        self.assertEqual((self.home/'.codex/config.toml').read_bytes(),config)
        operations.undo(restored['id'],home=self.home);self.assertEqual(self.fingerprint(),withdrawn)
        operations.undo(result['id'],home=self.home);self.assertEqual(self.fingerprint(),before)

    def test_cleanup_confirmation_stale_list_revision_and_rollback(self):
        before=self.fingerprint()
        with self.assertRaisesRegex(ValueError,'明确同意'):cleanup.apply(home=self.home)
        with patch.object(cleanup.usage,'report',return_value=self.data):
            with self.assertRaisesRegex(ValueError,'名单已经变了'):cleanup.apply([],True,self.home,candidate_names=['candidate'])
            with self.assertRaisesRegex(ValueError,'目录内容已经变了'):cleanup.apply([],True,self.home,expected='stale')
            with self.assertRaisesRegex(ValueError,'不在本次'):cleanup.apply(['young'],True,self.home)
            with patch.object(cleanup,'reconcile_assignments',side_effect=ValueError('injected')):
                with self.assertRaisesRegex(ValueError,'injected'):cleanup.apply([],True,self.home)
        self.assertEqual(before,self.fingerprint())

    def test_backup_and_log_evidence_and_60_day_boundary(self):
        _,reg,_=operations.load(self.home)
        # No-date can get a reliable archive time independently of rebuilt registry times.
        path=self.home/'.skill-pilot/backups'
        import tarfile
        for p in path.glob('*/manifest.json'):
            d=json.loads(p.read_text())
            if '.skill-pilot/registry.json' not in d['existing']:
                archive=p.parent/'files.tar'
                with tarfile.open(archive) as a:members=a.getmembers()
                self.assertTrue(any(m.name.endswith('no-date/SKILL.md') for m in members))
        # Archive times are recent in this fixture, so no-date stays protected.
        item=next(s for s in self.preview()['excluded'] if s['name']=='no-date')
        self.assertIn('迁移备份',item['installation_evidence'])
        cutoff=(self.now-timedelta(days=60)).isoformat()
        lock=self.home/'.agents/.skill-lock.json';data=json.loads(lock.read_text());data['skills']['candidate']['installedAt']=cutoff;lock.write_text(json.dumps(data))
        self.assertIn('candidate',{r['name'] for r in self.preview()['candidates']})
        usage_row=next(s for s in self.data['skills'] if s['name']=='candidate');usage_row['last_used']={'codex':cutoff}
        self.assertNotIn('candidate',{r['name'] for r in self.preview()['candidates']})
        # With no migration archive or lock evidence, absence of dates means freshly installed.
        import shutil
        shutil.rmtree(self.home/'.skill-pilot/backups')
        self.assertIsNone(next(r for r in self.preview()['excluded'] if r['name']=='no-date')['installed_at'])
        next(s for s in self.data['skills'] if s['name']=='no-date')['first_seen']='2026-01-01T00:00:00+00:00'
        self.assertIn('no-date',{r['name'] for r in self.preview()['candidates']})


if __name__=='__main__':unittest.main()
