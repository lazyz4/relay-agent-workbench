"""Reproducible acceptance: engineering checks vs actual model task execution."""
import datetime as dt
import json
import secrets
import time
import urllib.parse


def run(runtime, mode='engineering'):
    if mode not in ('engineering','model'):
        raise ValueError('未知验收模式')
    # Acceptance writes are deliberately limited to the bundled demo services.
    expected={'list_tasks':('rd','/tasks'),'create_requirement':('rd','/requirements'),'list_documents':('docs','/documents'),'create_document':('docs','/documents')}
    tools=runtime.catalog()
    for name,(service,path) in expected.items():
        tool=tools.get(name,{})
        address=urllib.parse.urlparse(tool.get('base_url',''))
        if address.hostname not in ('localhost','127.0.0.1') or tool.get('path')!=path:
            raise ValueError('验收仅支持内置本地演示连接器，请恢复默认工具配置，避免向真实系统写入测试数据')
        try:
            identity=runtime.request_json(tool['base_url'].rstrip('/')+'/health')
            if identity.get('service')!=service or identity.get('ready') is not True:
                raise ValueError('服务身份不匹配')
        except Exception:
            raise ValueError('演示服务未就绪，无法运行验收') from None
    report={'mode':mode,'started_at':dt.datetime.now(dt.timezone.utc).isoformat(),'synthetic_data':True,'model_used':mode=='model','cases':[]}
    token=secrets.token_hex(3)
    started=time.monotonic()

    def case(name, callback):
        tick=time.monotonic()
        try:
            evidence=callback()
            report['cases'].append({'name':name,'passed':True,'evidence':evidence,'seconds':round(time.monotonic()-tick,2)})
        except Exception as exc:
            # No external response body or credential is included in the report.
            report['cases'].append({'name':name,'passed':False,'error':str(exc) if isinstance(exc,ValueError) else type(exc).__name__,'seconds':round(time.monotonic()-tick,2)})

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    if mode=='engineering':
        def query():
            rows=runtime.invoke('list_tasks',{'project':'星河'})['result']
            require({r['id'] for r in rows}=={'TASK-1','TASK-2','TASK-3'},'任务查询集合不符合演示数据')
            return {'ids':[r['id'] for r in rows],'transport':'actual HTTP'}
        case('任务查询返回真实记录',query)

        def create():
            args={'project':'星河','title':'验收需求-'+token,'description':'仅用于工程验收的虚构记录'}
            pending=runtime.invoke('create_requirement',args)
            with runtime.database('rd') as db:
                before=db.execute("SELECT count(*) FROM records WHERE request_key=?",('requirements:'+pending['pending_id'],)).fetchone()[0]
            require(before==0,'未确认前发生写入')
            first=runtime.decide(pending['pending_id'],True)
            again=runtime.decide(pending['pending_id'],True)
            require(first==again and first['verified'],'回查或去重失败')
            with runtime.database('rd') as db:
                count=db.execute("SELECT count(*) FROM records WHERE request_key=?",('requirements:'+pending['pending_id'],)).fetchone()[0]
            require(count==1,'重复创建')
            return {'id':first['record']['id'],'count':count,'verified':True}
        case('确认、持久化、回查与去重',create)

        def cross():
            tasks=runtime.invoke('list_tasks',{'project':'星河'})['result']
            complete=[t for t in tasks if t['status']=='已完成']
            text='\n'.join(t['id']+' '+t['title']+' '+t['status'] for t in complete)
            p=runtime.invoke('create_document',{'title':'工程验收周报-'+token,'body':text})
            result=runtime.decide(p['pending_id'],True)
            docs=runtime.invoke('list_documents',{})['result']
            require(any(d['id']==result['record']['id'] and d['body']==text for d in docs),'跨系统落盘验证失败')
            return {'document_id':result['record']['id'],'source_ids':[t['id'] for t in complete],'model_used':False,'verified':True}
        case('研发查询→文档保存的实际 HTTP 链路',cross)

        def cancel():
            p=runtime.invoke('create_document',{'title':'取消-'+token,'body':'不得保存'})
            runtime.decide(p['pending_id'],False)
            with runtime.database('docs') as db:
                require(db.execute('SELECT count(*) FROM records WHERE request_key=?',('documents:'+p['pending_id'],)).fetchone()[0]==0,'取消后出现写入')
            return {'cancelled':True,'writes':0}
        case('取消写入不产生记录',cancel)

        def reject():
            try:
                runtime.invoke('create_requirement',{})
            except ValueError:
                return {'rejected':True}
            raise ValueError('缺参没有被拒绝')
        case('必填字段校验',reject)
    else:
        import os
        if not runtime.providers.ready():
            raise ValueError('请先配置并测试模型')
        report['model']=os.getenv('MODEL_ID')

        def agent_task(prompt, expected):
            response=runtime.chat(prompt)
            traces=list(response.get('trace',[]))
            for _ in range(3):
                if response.get('error'):
                    raise ValueError(response['error'])
                pending=response.get('pending')
                if not pending:
                    break
                # Evaluation user explicitly authorizes only these fixed synthetic tasks.
                if pending['tool'] not in ('create_requirement','create_document') or token not in json.dumps(pending['args'],ensure_ascii=False):
                    runtime.chat(None,response['chat_id'],False)
                    raise ValueError('模型请求了不在验收授权范围的写入，已拒绝')
                response=runtime.chat(None,response['chat_id'],True)
                traces+=response.get('trace',[])
            if response.get('error'):
                raise ValueError(response['error'])
            require(not response.get('pending'),'任务超出确认步数上限')
            names=[t['tool'] for t in traces]
            require(all(n in names for n in expected),'模型未完成预期工具调用')
            records=[t['result']['record'] for t in traces if t.get('result',{}).get('verified')]
            return {'chat_id':response['chat_id'],'tools':names,'verified_records':records,'answer':response.get('answer','')}

        case('真实模型：自然语言查询',lambda:agent_task('请查询星河项目的全部任务，列出真实编号和当前状态。只查询，不写入。', ['list_tasks']))
        case('真实模型：理解参数并创建需求',lambda:agent_task('在星河项目创建一条需求，标题为“模型验收-'+token+'”，描述为“登录失败时明确提示原因”。这是虚构验收数据。不要增加负责人或日期等额外字段。', ['create_requirement']))

        def model_cross():
            result=agent_task('查询星河项目任务，只汇总状态为已完成的任务，在文档系统保存标题为“模型周报-'+token+'”的草稿。正文必须包含完成任务的真实编号、标题和状态，不得将未完成任务写成已完成。', ['list_tasks','create_document'])
            docs=[r for r in result['verified_records'] if r.get('title')=='模型周报-'+token]
            require(bool(docs),'没有找到目标文档的回查结果')
            require('TASK-2' in docs[0]['body'] and '需求评审' in docs[0]['body'],'周报缺少真实来源编号或标题')
            result['scoring_note']='自动检查调用链、落盘回查与关键来源；完整事实准确性仍须人工复核。'
            return result
        case('真实模型：研发→文档的跨系统任务',model_cross)
    report['passed']=sum(c['passed'] for c in report['cases'])
    report['total']=len(report['cases'])
    report['seconds']=round(time.monotonic()-started,2)
    report['limitations']='工程模式不使用模型；模型模式仅验证当前模型和当前合成任务，不能外推真实企业效果。'
    runtime.DATA.mkdir(exist_ok=True)
    (runtime.DATA/'latest-evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    runtime.audit('acceptance',mode,{'passed':report['passed'],'total':report['total']})
    return report
