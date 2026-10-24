"""Provider presets and wire adapters; no credential is returned to the browser."""
import json
import os
import urllib.parse

PRESETS = {
    'deepseek': {'label':'DeepSeek','protocol':'openai','base_url':'https://api.deepseek.com','models':['deepseek-flash','deepseek-v4-pro'],'key_required':True},
    'anthropic': {'label':'Anthropic / Claude','protocol':'anthropic','base_url':'https://api.anthropic.com','models':[],'key_required':True},
    'compatible': {'label':'其他兼容 API / 企业网关','protocol':'openai','base_url':'','models':[],'key_required':True},
    'ollama': {'label':'Ollama（本地）','protocol':'openai','base_url':'http://127.0.0.1:11434/v1','models':[],'key_required':False},
}


def active():
    legacy = 'RELAY_MODEL_PROVIDER' not in os.environ
    if legacy and not any(os.getenv(k) for k in ('ANTHROPIC_API_KEY','ANTHROPIC_BASE_URL','MODEL_ID')):
        return {'provider':'deepseek','protocol':'openai','base_url':PRESETS['deepseek']['base_url'],'model':PRESETS['deepseek']['models'][0],'key':''}
    base=os.getenv('ANTHROPIC_BASE_URL','https://api.anthropic.com').rstrip('/')
    provider=os.getenv('RELAY_MODEL_PROVIDER', 'deepseek' if urllib.parse.urlparse(base).hostname=='api.deepseek.com' else 'anthropic')
    return {'provider':provider,'protocol':os.getenv('RELAY_MODEL_PROTOCOL','anthropic' if legacy else PRESETS.get(provider,PRESETS['compatible'])['protocol']), 'base_url':base,'model':os.getenv('MODEL_ID',''),'key':os.getenv('ANTHROPIC_API_KEY','')}


def public():
    c=active()
    c.pop('key')
    c['configured']=ready()
    return c


def ready():
    c=active()
    return bool(c['model'] and c['base_url'] and (c['key'] or c['provider']=='ollama'))


def normalize(body, current=None):
    provider=body.get('provider','deepseek')
    if provider not in PRESETS:
        raise ValueError('请选择有效的模型供应商')
    preset=PRESETS[provider]
    protocol=body.get('protocol',preset['protocol'])
    base=body.get('base_url',preset['base_url'])
    model=body.get('model','')
    key=body.get('key','')
    if not all(isinstance(x,str) for x in (base,model,key)) or protocol not in ('openai','anthropic'):
        raise ValueError('模型配置格式不正确')
    base=base.strip().rstrip('/')
    model=model.strip()
    key=key.strip()
    url=urllib.parse.urlparse(base)
    if not url.hostname or url.username or url.password or url.query or url.fragment or url.scheme not in ('http','https') or (url.scheme=='http' and url.hostname not in ('localhost','127.0.0.1')):
        raise ValueError('服务地址必须为 HTTPS 或本机 HTTP，不能包含密钥和查询参数')
    if len(base)>1500 or len(model)>200 or not model or len(key)>2000 or any(c in key for c in ('\r','\n')):
        raise ValueError('请检查模型名称或 API Key 格式')
    if provider=='ollama' and url.hostname not in ('localhost','127.0.0.1'):
        raise ValueError('Ollama 预设仅用于本机；远端服务请使用兼容 API 选项并配置授权')
    if not key and current and current['provider']==provider and current['base_url']==base:
        key=current['key']
    if preset['key_required'] and not key:
        raise ValueError('请填写该服务的 API Key')
    return {'provider':provider,'protocol':protocol,'base_url':base,'model':model,'key':key}


def install(config):
    os.environ['RELAY_MODEL_PROVIDER']=config['provider']
    os.environ['RELAY_MODEL_PROTOCOL']=config['protocol']
    os.environ['ANTHROPIC_BASE_URL']=config['base_url']
    os.environ['MODEL_ID']=config['model']
    os.environ['ANTHROPIC_API_KEY']=config['key']


def endpoint(config, suffix):
    base=config['base_url'].rstrip('/')
    if config['protocol']=='anthropic' and not base.endswith('/v1'):
        base+='/v1'
    return base+'/'+suffix


def headers(config):
    if config['protocol']=='anthropic':
        return {'x-api-key':config['key'],'anthropic-version':'2023-06-01'}
    return {'Authorization':'Bearer '+config['key']} if config['key'] else {}


def chat_messages(messages, system):
    out=[{'role':'system','content':system}]
    for message in messages:
        content=message['content']
        if isinstance(content,str):
            out.append({'role':message['role'],'content':content})
            continue
        text='\n'.join(b['text'] for b in content if b.get('type')=='text')
        if message['role']=='assistant':
            entry={'role':'assistant','content':text or None}
            calls=[{'id':b['id'],'type':'function','function':{'name':b['name'],'arguments':json.dumps(b['input'],ensure_ascii=False)}} for b in content if b.get('type')=='tool_use']
            if calls:
                entry['tool_calls']=calls
            out.append(entry)
        else:
            if text:
                out.append({'role':'user','content':text})
            for b in content:
                if b.get('type')=='tool_result':
                    out.append({'role':'tool','tool_call_id':b['tool_use_id'],'content':b['content']})
    return out


def call(request, config, messages, tools, system):
    if not config['model'] or (not config['key'] and config['provider']!='ollama'):
        raise ValueError('尚未配置模型，请在配置模型中填写服务与授权信息')
    if config['protocol']=='anthropic':
        payload={'model':config['model'],'max_tokens':2000,'tools':tools,'messages':messages,'system':system}
        if urllib.parse.urlparse(config['base_url']).hostname=='api.deepseek.com':
            payload['thinking']={'type':'disabled'}
        return request(endpoint(config,'messages'),'POST',payload,headers(config))
    payload={'model':config['model'],'messages':chat_messages(messages,system),'tools':[{'type':'function','function':{'name':t['name'],'description':t['description'],'parameters':t['input_schema']}} for t in tools],'max_tokens':2000,'stream':False}
    if urllib.parse.urlparse(config['base_url']).hostname=='api.deepseek.com':
        payload['thinking']={'type':'disabled'}
    result=request(endpoint(config,'chat/completions'),'POST',payload,headers(config))
    try:
        choice=result['choices'][0]
        response=choice['message']
        blocks=[]
        if response.get('content'):
            if not isinstance(response['content'],str):
                raise ValueError('目前仅支持文本模型响应')
            blocks.append({'type':'text','text':response['content']})
        for tool in response.get('tool_calls') or []:
            args=json.loads(tool['function']['arguments'])
            if not isinstance(args,dict):
                raise ValueError('工具参数必须为对象')
            blocks.append({'type':'tool_use','id':tool['id'],'name':tool['function']['name'],'input':args})
        return {'content':blocks,'stop_reason':'max_tokens' if choice.get('finish_reason')=='length' else ('tool_use' if response.get('tool_calls') else 'end_turn'),'usage':result.get('usage',{})}
    except (KeyError,IndexError,TypeError,json.JSONDecodeError):
        raise ValueError('服务响应不符合所选 Chat Completions 协议，或工具参数不是合法 JSON') from None


def list_models(request, config):
    result=request(endpoint(config,'models'),headers=headers(config))
    data=result.get('data',[])
    ids=[r['id'] for r in data if isinstance(r,dict) and isinstance(r.get('id'),str)]
    if not ids:
        raise ValueError('服务未返回模型列表，请手动填写该服务支持的模型 ID')
    return sorted(set(ids))[:200]
