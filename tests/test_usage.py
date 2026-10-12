from tests import set_up_home
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from skill_pilot import store, usage
from skill_pilot.usage import claude, codex, dsh
from skill_pilot.usage.common import Names, reads


class ParserTests(unittest.TestCase):
    def setUp(self):
        self.names = Names('/fake', {'skills': {'huashu-nuwa': {'entries':['.codex/skills/nuwa-skill']},
            'alpha': {'entries':['.agents/skills/alpha']}, 'stss': {'entries':['.codex/skills/community/stss']}}})

    def test_aliases_old_new_and_vendor_paths(self):
        for path in ['/fake/.codex/skills/nuwa-skill/SKILL.md','~/.skill-pilot/store/huashu-nuwa/SKILL.md',
                     '~/.gemini/config/skills/nuwa-skill/SKILL.md']:
            self.assertEqual(self.names.path(path),'huashu-nuwa')
        self.assertEqual(self.names.path('/fake/.codex/skills/community/stss/SKILL.md'),'stss')
        self.assertEqual(self.names.path('/fake/Developer/vendor/stop-that-shit-local/skills/stss/SKILL.md'),'stss')
        self.assertIsNone(self.names.path('/project/alpha/SKILL.md'))
        self.assertIsNone(self.names.path('/fake/.skill-pilot/store/alpha/examples/x/SKILL.md'))
        self.assertIsNone(self.names.name('plugin:alpha'))

    def test_claude_skill_read_slash_and_no_write_or_prompt(self):
        for block in [{'type':'tool_use','name':'Skill','input':{'skill':'alpha'}},
                      {'type':'tool_use','name':'Read','input':{'file_path':'~/.agents/skills/alpha/SKILL.md'}},
                      {'type':'tool_use','name':'Bash','input':{'command':'cat ~/.agents/skills/alpha/SKILL.md'}}]:
            self.assertEqual(claude.parse({'type':'assistant','message':{'content':[block]}},self.names,'s')[1],{'alpha'})
        for text in ['/alpha answer','<command-name>/alpha</command-name>']:
            self.assertEqual(claude.parse({'type':'user','message':{'content':text}},self.names,'s')[1],{'alpha'})
        for row in [{'type':'system','message':{'content':'alpha ~/.agents/skills/alpha/SKILL.md'}},
                    {'type':'assistant','message':{'content':[{'type':'tool_use','name':'Write','input':{'file_path':'~/.agents/skills/alpha/SKILL.md'}}]}}]:
            self.assertFalse(claude.parse(row,self.names,'s')[1])

    def test_codex_tools_only_and_exec_read_arguments(self):
        path='~/.agents/skills/alpha/SKILL.md'
        cases=[('function_call','exec_command',json.dumps({'cmd':'cat '+path})),
               ('custom_tool_call','exec','text(await tools.exec_command({cmd: "cat '+path+'", title:"ignored"}));'),
               ('function_call','Read',json.dumps({'file_path':path}))]
        for kind,name,args in cases:
            self.assertEqual(codex.parse({'payload':{'type':kind,'name':name,'input':args}},self.names,'s')[1],{'alpha'})
        self.assertEqual(codex.parse({'payload':{'type':'local_shell_call','action':{'command':['bash','-lc','sed -n 1,30p '+path]}}},self.names,'s')[1],{'alpha'})
        for name,args in [('apply_patch','*** Add File: '+path),('exec_command',json.dumps({'cmd':'echo x > '+path})),
                          ('exec','await tools.spawn_agent({message:"cat '+path+'"})')]:
            self.assertFalse(codex.parse({'payload':{'type':'function_call','name':name,'arguments':args}},self.names,'s')[1])
        self.assertFalse(codex.parse({'payload':{'type':'message','content':path}},self.names,'s')[1])

    def test_reads_do_not_count_shell_edit_or_message(self):
        for command in ['sed -i x ~/.agents/skills/alpha/SKILL.md','cat example > ~/.agents/skills/alpha/SKILL.md',
                        'echo "cat ~/.agents/skills/alpha/SKILL.md"', "open('~/.agents/skills/alpha/SKILL.md', 'w')",
                        "cat > example <<'END'\ncat ~/.agents/skills/alpha/SKILL.md\nEND\n"]:
            self.assertFalse(reads('Bash',{'command':command},self.names))
        self.assertEqual(reads('Bash',{'command':'cat ~/.agents/skills/alpha/SKILL.md > /tmp/copy'},self.names),{'alpha'})
        self.assertEqual(reads('Bash',{'command':'rg -i example ~/.agents/skills/alpha/SKILL.md'},self.names),{'alpha'})

    def test_dsh_tool_type_and_named_skill(self):
        row={'type':'tool/call','data':{'name':'skill','arguments':'{"name":"alpha"}'}}
        self.assertEqual(dsh.parse(row,self.names,'s')[1],{'alpha'})
        row['type']='request/context';self.assertFalse(dsh.parse(row,self.names,'s')[1])
        row={'type':'tool/call','data':{'name':'write','arguments':'{"path":"~/.agents/skills/alpha/SKILL.md"}'}}
        self.assertFalse(dsh.parse(row,self.names,'s')[1])


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix='skill-pilot-m5-usage-');self.addCleanup(self.tmp.cleanup)
        set_up_home(self, Path(self.tmp.name))
        path=self.home/'.codex/skills/alpha';path.mkdir(parents=True)
        (path/'SKILL.md').write_text('---\nname: alpha\ndescription: hello\n---\nexample\n')
        store.apply(store.preview(self.home)['plan_id'],self.home)
        self.path=self.home/'.codex/sessions/session.jsonl';self.path.parent.mkdir(parents=True)
        self.date='2026-10-10T10:00:00Z'
        self.now=datetime(2026,10,11,tzinfo=timezone.utc)

    def row(self,tool='exec_command',cmd='cat ~/.agents/skills/alpha/SKILL.md'):
        return {'timestamp':self.date,'payload':{'type':'function_call','name':tool,'arguments':json.dumps({'cmd':cmd})}}

    def save(self,rows,path=None,mode='w'):
        with (path or self.path).open(mode) as f:
            for row in rows:f.write(json.dumps(row)+'\n')

    def report(self):return usage.report(self.home,now=self.now)

    def test_once_per_session_increment_archive_and_deleted_history(self):
        header={'type':'session_meta','timestamp':self.date,'payload':{'id':'original'}}
        self.save([header,self.row(),self.row()])
        archive=self.home/'.codex/archived_sessions/copy.jsonl';archive.parent.mkdir()
        self.save([header,self.row()],archive)
        first=self.report();self.assertEqual(first['skills'][0]['sessions_30d'],{'codex':1})
        self.assertGreater(first['scanned_bytes'],0)
        self.assertEqual(self.report()['scanned_bytes'],0)
        self.save([self.row()],mode='a');self.assertEqual(self.report()['skills'][0]['sessions_30d'],{'codex':1})
        self.path.unlink();archive.unlink()
        self.assertEqual(self.report()['skills'][0]['sessions_30d'],{'codex':1})

    def test_system_list_is_installation_evidence_not_usage(self):
        self.save([{'timestamp':self.date,'payload':{'type':'message','content':'alpha ~/.agents/skills/alpha/SKILL.md'}}])
        row=self.report()['skills'][0]
        self.assertFalse(row['last_used']);self.assertTrue(row['first_seen'])

    def test_first_name_mention_is_evidence_when_original_install_time_missing(self):
        import shutil
        shutil.rmtree(self.home/'.skill-pilot/backups')
        self.save([{'timestamp':self.date,'payload':{'type':'message','content':'alpha was installed'}}])
        row=self.report()['skills'][0]
        self.assertFalse(row['last_used']);self.assertEqual(row['first_seen'],'2026-10-10T10:00:00+00:00')

    def test_claude_same_session_sidechain_and_slash_dedup(self):
        folder=self.home/'.claude/projects/p';folder.mkdir(parents=True)
        a={'type':'user','timestamp':self.date,'sessionId':'c','message':{'content':'/alpha'}}
        self.save([a],folder/'c.jsonl');self.save([a],folder/'sub.jsonl')
        self.assertEqual(self.report()['skills'][0]['sessions_30d'],{'claude':1})

    def test_claude_coverage_timestamp_after_long_payload(self):
        path=self.home/'.claude/projects/p/c.jsonl';path.parent.mkdir(parents=True)
        row={'type':'assistant','sessionId':'c','message':{'content':[{'type':'tool_use','name':'Skill',
             'input':{'skill':'alpha','args':'synthetic '*100}}]},'timestamp':self.date}
        self.save([row],path)
        result=self.report();self.assertEqual(result['coverage']['claude']['earliest'],'2026-10-10T10:00:00+00:00')

    def test_partial_line_then_append_and_truncation(self):
        text=json.dumps(self.row())
        self.path.write_text(text[:20])
        self.assertFalse(self.report()['coverage']['codex']['available'])
        with self.path.open('a') as f:f.write(text[20:]+'\n')
        self.assertTrue(self.report()['coverage']['codex']['available'])
        self.path.write_text(json.dumps({'timestamp':self.date})+'\n')
        self.assertEqual(self.report()['skills'][0]['sessions_30d'],{'codex':1})

    def test_malformed_file_stays_unavailable_on_repeated_scan(self):
        self.path.write_text('{"timestamp":"2026-10-10T10:00:00Z","SKILL.md":bad}\n')
        for _ in range(2):
            self.assertFalse(self.report()['coverage']['codex']['available'])

    def test_dsh_multiframe_v3_v4_dedup_and_increment(self):
        folder=self.home/'.dsh/sessions/p/session-d';folder.mkdir(parents=True)
        header={'type':'session','id':'d','createdAt':1791630000000}
        call={'type':'tool/call','seq':3,'time':1791630000100,'data':{'name':'skill','arguments':'{"name":"alpha"}'}}
        def frames(rows):
            code="const z=require('node:zlib');process.stdout.write(Buffer.concat(JSON.parse(process.argv[1]).map(x=>z.zstdCompressSync(Buffer.from(JSON.stringify(x)+'\\n')))));"
            return subprocess.run(['node','-e',code,json.dumps(rows)],capture_output=True,check=True).stdout
        v3=folder/'session.v3.jsonl.zstd';v4=folder/'session.v4.jsonl.zstd'
        v3.write_bytes(frames([header,call,call]));v4.write_bytes(frames([header,call]))
        result=self.report();self.assertTrue(result['coverage']['dsh']['available'])
        self.assertEqual(result['skills'][0]['sessions_30d'],{'dsh':1})
        self.assertEqual(self.report()['scanned_bytes'],0)
        with v4.open('ab') as f:f.write(frames([call]))
        self.assertEqual(self.report()['skills'][0]['sessions_30d'],{'dsh':1})
        v4.write_bytes(v4.read_bytes()+b'bad')
        self.assertFalse(self.report()['coverage']['dsh']['available'])


if __name__=='__main__':unittest.main()
