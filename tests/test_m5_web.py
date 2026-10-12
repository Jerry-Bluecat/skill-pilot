import json
import threading
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

from skill_pilot import operations
from skill_pilot.web.server import Dashboard
from tests import test_cleanup


class CleanupWebTests(unittest.TestCase):
    def setUp(self):
        self.fixture=test_cleanup.CleanupTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.server=Dashboard({'home':str(self.fixture.home)})
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join()

    def request(self,path,body=None):
        headers={'X-Skill-Pilot-Token':self.server.token,'Origin':self.server.origin}
        request=urllib.request.Request(self.server.origin+path,headers=headers,data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(request) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:return error.code,json.load(error)

    def test_readonly_views_and_confirmation_gate_then_cleanup_restore_and_undo(self):
        with patch('skill_pilot.cleanup.usage.report',return_value=self.fixture.data):
            before=self.fixture.fingerprint()
            status,view=self.request('/api/cleanup');self.assertEqual(status,200)
            self.assertEqual(before,self.fixture.fingerprint())
            body={'candidates':[s['name'] for s in view['candidates']],'revision':view['revision'],'keep':['candidate']}
            self.assertEqual(self.request('/api/cleanup/apply',body)[0],400)
            with patch('skill_pilot.web.server.preview_allowed',return_value=False):
                self.assertEqual(self.request('/api/cleanup/apply',body|{'confirmed':True})[0],403)
            status,result=self.request('/api/cleanup/apply',body|{'confirmed':True});self.assertEqual(status,200,result)
            self.assertEqual(result['withdrawn'],['dsh-only'])
            _,after=self.request('/api/cleanup');self.assertEqual(after['withdrawn'][0]['name'],'dsh-only')
            status,restored=self.request('/api/withdrawn/restore',{'skills':['dsh-only'],'revision':after['revision'],'confirmed':True})
            self.assertEqual(status,200,restored)
            for record in [restored,result]:
                status,undo=self.request('/api/undo',{'id':record['id'],'revision':operations.table(self.fixture.home)['revision'],'confirmed':True})
                self.assertEqual(status,200,undo)
            self.assertEqual(before,self.fixture.fingerprint())

    def test_usage_route_without_dependency_suggestions(self):
        with patch('skill_pilot.web.server.usage.report',return_value=self.fixture.data):
            status,result=self.request('/api/usage');self.assertEqual(status,200)
            self.assertFalse(result['coverage']['antigravity']['available'])
        from skill_pilot.web.server import STATIC
        html=(STATIC/'index.html').read_text();js=(STATIC/'app.js').read_text()
        self.assertNotIn('依赖建议',html)
        self.assertNotIn('data-dependency=',js)


if __name__=='__main__':unittest.main()
