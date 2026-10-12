from tests import set_up_home
import contextlib
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from skill_pilot import cli, normalization, operations, store, updates
from skill_pilot.sources import github
from skill_pilot.sources.update_github import Reader
from skill_pilot.sync import visibility


class NormalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='skill-pilot-m5-normalize-');self.addCleanup(self.tmp.cleanup)
        set_up_home(self, Path(self.tmp.name)/'home');self.repo=Path(self.tmp.name).resolve()/'repo';self.repo.mkdir()
        self.skill(self.home/'.codex/skills/original','original')
        store.apply(store.preview(self.home)['plan_id'],self.home)
        self.root=self.repo/'skills/alpha';self.skill(self.root,'alpha','See examples/person/SKILL.md and SKILL.md.')
        self.skill(self.root/'examples/person','person-perspective','See ../../SKILL.md and SKILL.md.')
        (self.root/'examples/README.md').write_text('See person/SKILL.md')
        github.git(self.repo,'init','-q');self.commit()

    def skill(self,path,name,body='content'):
        path.mkdir(parents=True,exist_ok=True);(path/'SKILL.md').write_text(f'---\nname: {name}\ndescription: hello\n---\n{body}\n')

    def commit(self):
        github.git(self.repo,'add','.');github.git(self.repo,'-c','user.name=Test','-c','user.email=t@local','-c','commit.gpgsign=false','commit','-qm','fixture')

    def test_normalization_is_idempotent_and_updates_relative_references(self):
        before=store.physical_state(self.root);processed=normalization.apply(self.root)
        self.assertEqual(len(processed['renamed']),1)
        self.assertEqual(processed['references'],['SKILL.md','examples/README.md','examples/person/SKILL.example.md'])
        self.assertIn('examples/person/SKILL.example.md',(self.root/'SKILL.md').read_text())
        self.assertIn('person/SKILL.example.md',(self.root/'examples/README.md').read_text())
        text=(self.root/'examples/person/SKILL.example.md').read_text()
        self.assertIn('../../SKILL.md',text);self.assertIn('and SKILL.example.md',text)
        self.assertEqual(normalization.tree(self.root),store.git_tree(self.root))
        self.assertEqual(normalization.apply(self.root),{'renamed':[],'references':[]})
        self.assertNotEqual(before,store.physical_state(self.root))

    def test_collision_preserves_existing_files(self):
        (self.root/'examples/person/SKILL.example.md').write_text('keep')
        before=store.physical_state(self.root)
        with self.assertRaisesRegex(ValueError,'已经有'):normalization.apply(self.root)
        self.assertEqual(before,store.physical_state(self.root))

    def test_install_normalizes_store_base_and_conflicts_without_mutating_source(self):
        review=github.inspect(self.repo.as_uri());self.addCleanup(shutil.rmtree,review['temporary'],True)
        point=store.physical_state(self.root)
        result=operations.install(review,['alpha'],['codex'],home=self.home)
        root=self.home/'.skill-pilot/store/alpha'
        self.assertFalse((root/'examples/person/SKILL.md').exists());self.assertTrue((root/'examples/person/SKILL.example.md').exists())
        self.assertEqual(normalization.tree(root),store.git_tree(self.home/'.skill-pilot/bases/alpha'))
        self.assertTrue(result['normalization']['alpha']['renamed']);self.assertEqual(point,store.physical_state(self.root))
        self.assertTrue(operations.conflicts(review['skills'],operations.load(self.home)[1],self.home)[0]['same_content'])

    def test_first_migration_and_absorption_normalize(self):
        other=Path(self.tmp.name).resolve()/'other'
        shutil.copytree(self.root,other/'.codex/skills/alpha')
        result=store.apply(store.preview(other)['plan_id'],other)
        self.assertTrue(result['normalization']['alpha']['renamed'])
        self.assertEqual(visibility(other)['codex']['available'],['alpha'])
        shutil.copytree(self.root,self.home/'.codex/skills/alpha')
        with patch.object(github,'verify_source',return_value={'source':'自制'}):
            result=operations.absorb(all_skills=True,home=self.home)
        self.assertTrue(result['normalization']['alpha']['renamed'])
        self.assertFalse((self.home/'.skill-pilot/store/alpha/examples/person/SKILL.md').exists())

    def test_standard_processing_not_local_edits_and_update_succeeds(self):
        review=github.inspect(self.repo.as_uri());self.addCleanup(shutil.rmtree,review['temporary'],True)
        operations.install(review,['alpha'],['codex'],home=self.home)
        # An untrusted normalized baseline is compared only with the current upstream.
        (self.root/'SKILL.md').write_text((self.root/'SKILL.md').read_text()+'new upstream\n');self.commit()
        review=updates.check(self.home);self.addCleanup(shutil.rmtree,review['temporary'],True)
        self.assertFalse(review['errors'],review['errors']);row=next(r for r in review['skills'] if r['name']=='alpha')
        self.assertIsNone(row['local_modified']);self.assertTrue(row['has_update'])
        self.assertNotEqual(row['normalized_tree_sha'],row['tree_sha'])
        result=updates.apply(review,['alpha'],confirmed=True)
        self.assertTrue(result['normalization']['alpha']['renamed'])
        self.assertFalse((self.home/'.skill-pilot/store/alpha/examples/person/SKILL.md').exists())
        self.assertIn('new upstream',(self.home/'.skill-pilot/store/alpha/SKILL.md').read_text())
        self.assertFalse(next(s for s in operations.table(self.home)['skills'] if s['name']=='alpha')['local_modified'])
        with patch.object(Reader,'latest',return_value=(row['commit'],row['tree_sha'])), \
                patch.object(Reader,'current',side_effect=AssertionError('download forbidden')), \
                patch.object(Reader,'inspect',side_effect=AssertionError('history forbidden')):
            latest=updates.check(self.home);self.addCleanup(shutil.rmtree,latest['temporary'],True)
        self.assertFalse(latest['errors'],latest['errors'])
        self.assertEqual(next(r for r in latest['skills'] if r['name']=='alpha')['status'],'已是最新')

    def test_mention_in_text_does_not_create_dependency(self):
        (self.root/'SKILL.md').write_text((self.root/'SKILL.md').read_text()+'Read original optionally.\n');self.commit()
        review=github.inspect(self.repo.as_uri());self.addCleanup(shutil.rmtree,review['temporary'],True)
        result=operations.install(review,['alpha'],['claude'],home=self.home)
        self.assertFalse(result.get('needs_confirmation'))
        result=operations.apply_assign([{'skill':'alpha','agent':'dsh','enabled':True}],home=self.home)
        self.assertFalse(result.get('needs_confirmation'))
        self.assertIn('alpha',visibility(self.home)['dsh']['available'])
        self.assertNotIn('original',visibility(self.home)['claude']['available'])

    def test_set_source_requires_yes_recalibrates_and_undo_is_exact(self):
        before=operations.revision(self.home,operations.load(self.home)[2])
        with self.assertRaisesRegex(ValueError,'--yes'):operations.set_source('original','owner/repo','.',home=self.home)
        with self.assertRaisesRegex(ValueError,'来源记录'):operations.set_source('original','owner/repo','../outside',True,self.home)
        base=self.home/'.skill-pilot/bases/original'
        row={'_base_path':str(base),'base_commit':'historical','base_tree_sha':store.git_tree(base),'similarity':1,'local_modified':False}
        # Return a separate calibrated copy; the real Reader's history matching is covered above.
        copy=Path(self.tmp.name)/'calibrated';shutil.copytree(base,copy);row['_base_path']=str(copy)
        with patch.object(Reader,'inspect',return_value=row):
            result=operations.set_source('original','owner/repo','skills/original',True,self.home)
        self.assertEqual(operations.load(self.home)[1]['skills']['original']['source']['source_path'],'skills/original')
        operations.undo(result['id'],home=self.home)
        self.assertEqual(before,operations.revision(self.home,operations.load(self.home)[2]))


class MergeCliTests(unittest.TestCase):
    def test_review_errors_preserve_preview_and_merge_id_implies_merge(self):
        with tempfile.TemporaryDirectory(prefix='skill-pilot-m5-cli-home-') as temporary:
            home=Path(temporary).resolve()
            directory=Path(tempfile.mkdtemp(prefix='skill-pilot-updates-'))
            self.addCleanup(shutil.rmtree,directory,True)
            review={'home':str(home),'temporary':str(directory),'id':directory.name}
            (directory/'review.json').write_text(json.dumps(review));(directory/'merged').write_text('keep preview')
            env={'SKILL_PILOT_HOME':str(home)}
            args=['skill-pilot','update','alpha','--yes','--review',directory.name,'--json']
            with patch.dict('os.environ',env),patch.object(sys,'argv',args),patch.object(updates,'apply',side_effect=ValueError('bad arguments')),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaises(SystemExit):cli.main()
            self.assertTrue((directory/'review.json').exists());self.assertEqual((directory/'merged').read_text(),'keep preview')
            with patch.dict('os.environ',env),patch.object(sys,'argv',args+['--merge-id','alpha=valid']),patch.object(updates,'apply',return_value={'message':'done'}) as apply,contextlib.redirect_stdout(io.StringIO()):
                cli.main()
            self.assertEqual(apply.call_args.args[2],{'alpha':'merge'})
            self.assertFalse(directory.exists())


if __name__=='__main__':unittest.main()
