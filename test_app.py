import json
import os
import urllib.error
from pathlib import Path
import tempfile
import unittest
import sys
from unittest.mock import patch
import app


class WorkbenchTests(unittest.TestCase):
    def test_model_errors_are_actionable(self):
        with patch.object(app,'_model_call',side_effect=urllib.error.HTTPError('https://example.com',401,'bad',{},None)):
            with self.assertRaisesRegex(ValueError,'API Key'):
                app.model_call([])
        problem=OSError('blocked')
        problem.winerror=10013
        with patch.object(app,'_model_call',side_effect=urllib.error.URLError(problem)):
            with self.assertRaisesRegex(ValueError,'10013'):
                app.model_call([])

    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        app.DATA=Path(cls.tmp.name)
        app.initialize()
        cls.rd=app.serve(0,"rd")
        cls.docs=app.serve(0,"docs")
        cls.tools=app.catalog()
        for tool in cls.tools.values():
            port=cls.docs.server_port if 'document' in tool['name'] else cls.rd.server_port
            tool['base_url']=f'http://127.0.0.1:{port}'
        cls.mock=patch.object(app,'catalog',return_value=cls.tools)
        cls.mock.start()

    @classmethod
    def tearDownClass(cls):
        for server in [cls.rd,cls.docs]:
            server.shutdown()
            server.server_close()
        cls.mock.stop()
        cls.tmp.cleanup()

    def test_query_and_filter(self):
        self.assertEqual(len(app.invoke('list_tasks',{'project':'星河'})['result']),3)
        self.assertEqual(app.invoke('list_tasks',{'project':'不存在'})['result'],[])

    def test_model_configuration_does_not_return_key(self):
        server=app.serve(0,'ui')
        try:
            with patch.dict(os.environ,{},clear=True):
                result=app.request_json(f'http://127.0.0.1:{server.server_port}/api/model/configure','POST',{'key':'test-placeholder','model':'deepseek-flash'})
                self.assertTrue(result['configured'])
                self.assertNotIn('test-placeholder',json.dumps(result))
                status=app.request_json(f'http://127.0.0.1:{server.server_port}/api/status')
                self.assertTrue(status['model_ready'])
                self.assertNotIn('test-placeholder',json.dumps(status))
        finally:
            server.shutdown()
            server.server_close()

    def test_connection_query_only(self):
        self.assertTrue(app.test_connection('list_tasks',{})['connected'])
        with self.assertRaises(ValueError):
            app.test_connection('create_requirement',{})

    def test_configuration_save_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            config=Path(directory)/'connectors.json'
            with patch.object(app,'CONFIG',config):
                items=json.loads(json.dumps(list(self.tools.values())))
                self.assertTrue(app.save_connectors(items)['saved'])
                before=config.read_text(encoding='utf-8')
                for field,value in [('method','DELETE'),('base_url','http://example.com'),('parameters',[]),('path','//example.com')]:
                    broken=json.loads(json.dumps(items))
                    broken[0][field]=value
                    with self.assertRaises(ValueError):
                        app.save_connectors(broken)
                    self.assertEqual(config.read_text(encoding='utf-8'),before)

    def test_confirmation_uses_preview_snapshot(self):
        pending=app.invoke('create_document',{'title':'配置快照','body':'使用预览时的连接'})
        with patch.object(app,'catalog',return_value={}):
            self.assertTrue(app.decide(pending['pending_id'],True)['verified'])

    def test_write_preview_confirmation_and_duplicate(self):
        args={'project':'星河','title':'确认测试','description':'验证实际写入'}
        pending=app.invoke('create_requirement',args)
        with app.database() as db:
            self.assertEqual(db.execute("SELECT count(*) FROM records WHERE request_key=?",('requirements:'+pending['pending_id'],)).fetchone()[0],0)
        first=app.decide(pending['pending_id'],True)
        second=app.decide(pending['pending_id'],True)
        self.assertEqual(first,second)
        self.assertTrue(first['verified'])

    def test_cancel(self):
        pending=app.invoke('create_document',{'title':'取消','body':'不得创建'})
        self.assertTrue(app.decide(pending['pending_id'],False)['cancelled'])
        with self.assertRaises(ValueError):
            app.decide(pending['pending_id'],True)

    def test_validation(self):
        for args in [{},{'title':3},{'title':'x','body':'y','extra':'z'}]:
            with self.assertRaises(ValueError):
                app.invoke('create_document',args)

    def test_uncertain_write_not_retried(self):
        pending=app.invoke('create_document',{'title':'不确定','body':'模拟网络故障'})
        with patch.object(app,'execute',side_effect=TimeoutError) as call:
            for _ in range(2):
                with self.assertRaises(ValueError):
                    app.decide(pending['pending_id'],True)
            self.assertEqual(call.call_count,1)

    def test_cross_system_model_protocol_offline(self):
        # Scripted model responses validate orchestration, NOT model intelligence.
        responses=[{'content':[{'type':'tool_use','id':'c1','name':'list_tasks','input':{'project':'星河'}}]},
                   {'content':[{'type':'tool_use','id':'c2','name':'create_document','input':{'title':'周报','body':'TASK-2 需求评审已完成。'}}]},
                   {'content':[{'type':'text','text':'草稿已保存。'}]}]
        with patch.object(app,'model_call',side_effect=responses):
            first=app.chat('生成周报')
            self.assertIsNotNone(first['pending'])
            final=app.chat(None,first['chat_id'],True)
            self.assertIsNone(final['pending'])
        docs=app.invoke('list_documents',{})['result']
        self.assertTrue(any(d['title']=='周报' for d in docs))

    def test_parallel_tool_calls_are_executed_sequentially(self):
        response={'content':[{'type':'tool_use','id':'p1','name':'list_tasks','input':{}},{'type':'tool_use','id':'p2','name':'list_documents','input':{}}]}
        with patch.object(app,'model_call',side_effect=[response,{'content':[{'type':'text','text':'查询完成'}]}]):
            result=app.chat('查询任务和文档')
        self.assertEqual([t['tool'] for t in result['trace']],['list_tasks','list_documents'])

    def test_multiple_writes_require_separate_confirmation(self):
        response={'content':[{'type':'tool_use','id':'w1','name':'create_document','input':{'title':'第一条','body':'x'}},{'type':'tool_use','id':'w2','name':'create_document','input':{'title':'第二条','body':'y'}}]}
        with patch.object(app,'model_call',side_effect=[response,{'content':[{'type':'text','text':'已处理'}]}]):
            a=app.chat('创建两条')
            b=app.chat(None,a['chat_id'],True)
            self.assertEqual(b['pending']['args']['title'],'第二条')
            c=app.chat(None,a['chat_id'],False)
            self.assertIsNone(c['pending'])

    def test_model_failure_after_write_can_resume_without_duplicate(self):
        response={'content':[{'type':'tool_use','id':'r1','name':'create_document','input':{'title':'恢复测试','body':'只写一次'}}]}
        with patch.object(app,'model_call',side_effect=[response,ValueError('网络超时'),{'content':[{'type':'text','text':'已完成'}]}]):
            a=app.chat('保存恢复测试')
            b=app.chat(None,a['chat_id'],True)
            self.assertTrue(b['can_resume'])
            c=app.chat(None,a['chat_id'],resume=True)
            self.assertEqual(c['answer'],'已完成')
        with app.database('docs') as db:
            rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM records')]
        self.assertEqual(sum(r['title']=='恢复测试' for r in rows),1)

    def test_pending_is_restored_from_saved_chat(self):
        response={'content':[{'type':'tool_use','id':'z1','name':'create_document','input':{'title':'恢复预览','body':'待确认'}}]}
        with patch.object(app,'model_call',return_value=response):
            result=app.chat('生成草稿')
        self.assertEqual(app.chat_info(result['chat_id'])['pending'],result['pending'])

    def test_openapi_import_reports_unsupported(self):
        from integrations import import_openapi
        spec={'openapi':'3.0.3','paths':{'/tasks':{'get':{'operationId':'find_tasks','parameters':[{'in':'query','name':'project','schema':{'type':'string'}}]}},'/bad':{'delete':{}},'/numbers':{'get':{'parameters':[{'in':'query','name':'count','schema':{'type':'integer'}}]}}}}
        result=import_openapi(spec,'http://127.0.0.1:8876')
        self.assertEqual(result['tools'][0]['name'],'find_tasks')
        self.assertEqual(len(result['warnings']),2)

    def test_field_mapping_and_envelope(self):
        tool={'method':'POST','base_url':'https://example.com','path':'/docs','verify_path':'/docs/{id}','field_map':{'title':'subject'},'response_path':'data'}
        with patch.object(app,'request_json',side_effect=[{'data':{'id':'1','subject':'标题'}},{'data':{'id':'1','subject':'标题'}}]) as request:
            result=app.execute(tool,{'title':'标题'},'unique')
            self.assertTrue(result['verified'])
            self.assertEqual(request.call_args_list[0].args[2],{'subject':'标题'})

    def test_demo_data_stores_are_separate(self):
        with app.database('rd') as db:
            self.assertEqual(db.execute("SELECT count(*) FROM records WHERE kind='documents'").fetchone()[0],0)
        with app.database('docs') as db:
            self.assertEqual(db.execute("SELECT count(*) FROM records WHERE kind='tasks'").fetchone()[0],0)

    @unittest.skipUnless(os.name=='nt','Windows DPAPI only')
    def test_windows_encrypted_key_roundtrip(self):
        import vault
        if not vault.available():
            self.skipTest('当前受限 Windows 会话无法使用 DPAPI；正常 Windows 用户会话需另行验证')
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'key.dpapi'
            vault.save(path,{'key':'test-private-placeholder','model':'test-model'})
            self.assertNotIn(b'test-private-placeholder',path.read_bytes())
            self.assertEqual(vault.load(path)['key'],'test-private-placeholder')

    def test_engineering_acceptance_uses_actual_http(self):
        from evaluate import run
        result=run(app,'engineering')
        self.assertEqual(result['passed'],result['total'])
        self.assertFalse(result['model_used'])

    def test_acceptance_rejects_remote_business_targets(self):
        from evaluate import run
        remote=json.loads(json.dumps(self.tools))
        remote['create_document']['base_url']='https://real-business.example'
        with patch.object(app,'catalog',return_value=remote):
            with self.assertRaisesRegex(ValueError,'本地演示'):
                run(app,'engineering')


if __name__=='__main__':
    unittest.main()
