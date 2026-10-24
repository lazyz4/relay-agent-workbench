import json
import os
import unittest
from unittest.mock import Mock, patch
import providers


class ProviderTests(unittest.TestCase):
    def test_first_run_defaults_to_deepseek_but_not_ready(self):
        with patch.dict(os.environ,{},clear=True):
            self.assertEqual(providers.active()['provider'],'deepseek')
            self.assertFalse(providers.ready())

    def test_ollama_requires_no_key_and_is_local(self):
        config=providers.normalize({'provider':'ollama','model':'installed-tool-model'})
        self.assertEqual(config['key'],'')
        self.assertEqual(config['base_url'],'http://127.0.0.1:11434/v1')
        with self.assertRaises(ValueError):
            providers.normalize({'provider':'ollama','model':'x','base_url':'https://remote.example'})

    def test_secret_reuse_only_same_provider_and_address(self):
        current=providers.normalize({'key':'private-test-key','model':'x'})
        same=providers.normalize({'model':'y'},current)
        self.assertEqual(same['key'],'private-test-key')
        with self.assertRaises(ValueError):
            providers.normalize({'provider':'compatible','base_url':'https://gateway.example/v1','model':'y'},current)
        with self.assertRaises(ValueError):
            providers.normalize({'model':'y','base_url':'https://different.example'},current)

    def test_custom_protocol_url_validation(self):
        for url in ('http://remote.example/v1','https://user:password@example.com','https://example.com?api_key=secret'):
            with self.assertRaises(ValueError):
                providers.normalize({'provider':'compatible','base_url':url,'key':'test','model':'x'})

    def test_chat_completions_tool_roundtrip(self):
        config=providers.normalize({'provider':'compatible','base_url':'https://gateway.example/v1','key':'test-key','model':'tool-model'})
        messages=[{'role':'user','content':'查任务'},{'role':'assistant','content':[{'type':'tool_use','id':'c1','name':'list_tasks','input':{}}]},{'role':'user','content':[{'type':'tool_result','tool_use_id':'c1','content':'[]'}]}]
        request=Mock(return_value={'choices':[{'message':{'content':None,'tool_calls':[{'id':'c2','function':{'name':'create_document','arguments':'{"title":"草稿"}'}}]},'finish_reason':'tool_calls'}]})
        tools=[{'name':'list_tasks','description':'query','input_schema':{'type':'object','properties':{}}}]
        result=providers.call(request,config,messages,tools,'system')
        args=request.call_args.args
        self.assertEqual(args[0],'https://gateway.example/v1/chat/completions')
        self.assertEqual(args[2]['messages'][-1],{'role':'tool','tool_call_id':'c1','content':'[]'})
        self.assertEqual(result['content'][0]['input'],{'title':'草稿'})
        self.assertEqual(args[3]['Authorization'],'Bearer test-key')

    def test_invalid_tool_arguments_are_rejected(self):
        request=Mock(return_value={'choices':[{'message':{'tool_calls':[{'id':'c1','function':{'name':'x','arguments':'not json'}}]}}]})
        config=providers.normalize({'key':'test','model':'x'})
        with self.assertRaisesRegex(ValueError,'JSON'):
            providers.call(request,config,[],[],'system')

    def test_messages_protocol_preserves_tools(self):
        config=providers.normalize({'provider':'anthropic','key':'test','model':'user-model-id','base_url':'https://api.anthropic.com/v1'})
        request=Mock(return_value={'content':[{'type':'text','text':'hello'}]})
        tools=[{'name':'x','description':'test','input_schema':{'type':'object','properties':{}}}]
        providers.call(request,config,[],tools,'system')
        self.assertEqual(request.call_args.args[0],'https://api.anthropic.com/v1/messages')
        self.assertEqual(request.call_args.args[2]['tools'],tools)

    def test_public_configuration_never_includes_key(self):
        with patch.dict(os.environ,{},clear=True):
            providers.install(providers.normalize({'key':'private-test-key','model':'x'}))
            public=providers.public()
            self.assertNotIn('key',public)
            self.assertNotIn('private-test-key',json.dumps(public))

    def test_models_are_loaded_from_provider(self):
        config=providers.normalize({'provider':'ollama','model':'local'})
        request=Mock(return_value={'data':[{'id':'model-b'},{'id':'model-a'},{'id':'model-a'}]})
        self.assertEqual(providers.list_models(request,config),['model-a','model-b'])
        self.assertEqual(request.call_args.args[0],'http://127.0.0.1:11434/v1/models')


if __name__=='__main__':
    unittest.main()
