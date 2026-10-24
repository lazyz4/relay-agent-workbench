
const demoTools=[{"name": "list_tasks", "description": "查询研发系统任务；project 为项目名称，可省略。返回原始任务状态和截止日期。", "base_url": "http://127.0.0.1:8876", "path": "/tasks", "method": "GET", "parameters": {"type": "object", "properties": {"project": {"type": "string"}}, "additionalProperties": false}}, {"name": "create_requirement", "description": "创建研发需求。必须先明确项目、标题和描述。写入需要用户确认。", "base_url": "http://127.0.0.1:8876", "path": "/requirements", "method": "POST", "verify_path": "/requirements/{id}", "parameters": {"type": "object", "properties": {"project": {"type": "string"}, "title": {"type": "string"}, "description": {"type": "string"}}, "required": ["project", "title", "description"], "additionalProperties": false}}, {"name": "list_documents", "description": "查询文档系统的已保存文档。", "base_url": "http://127.0.0.1:8877", "path": "/documents", "method": "GET", "parameters": {"type": "object", "properties": {}, "additionalProperties": false}}, {"name": "create_document", "description": "在文档系统保存草稿。title 是标题，body 是正文；周报须注明任务来源，不得编造完成情况。需要用户确认。", "base_url": "http://127.0.0.1:8877", "path": "/documents", "method": "POST", "verify_path": "/documents/{id}", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "body": {"type": "string"}}, "required": ["title", "body"], "additionalProperties": false}}];
const demoData={tasks:[{id:'TASK-1',project:'星河',title:'登录功能',status:'进行中',owner:'陈晨'},{id:'TASK-2',project:'星河',title:'需求评审',status:'已完成',owner:'王敏'},{id:'TASK-3',project:'星河',title:'回归测试',status:'未开始',owner:'李明'}],requirements:[],documents:[]};
const demoPending=new Map(),demoChats=new Map(),demoEvents=[];
let demoCount=0;
function demoId(prefix){return prefix+'-'+(++demoCount)}
function demoEvent(tool,state,detail){demoEvents.unshift({id:demoCount,time:new Date().toISOString(),tool,state,detail:JSON.stringify(detail)})}
function demoInvoke(name,args){
  if(!args||typeof args!=='object'||Array.isArray(args))throw Error('参数须为 JSON 对象');
  const tool=demoTools.find(t=>t.name===name);if(!tool)throw Error('预览仅支持内置示例工具');
  const props=tool.parameters.properties;for(const k of Object.keys(args))if(!(k in props)||typeof args[k]!=='string')throw Error('请检查参数名称与字符串类型');
  for(const k of tool.parameters.required||[])if(!args[k]?.trim())throw Error('缺少字段：'+k);
  if(name==='list_tasks'){const result=demoData.tasks.filter(t=>!args.project||t.project===args.project);demoEvent(name,'preview_read',result);return {result}}
  if(name==='list_documents'){demoEvent(name,'preview_read',demoData.documents);return {result:demoData.documents}}
  if(name==='create_requirement'&&args.project!=='星河')throw Error('演示中只有星河项目');
  const p={pending_id:demoId('preview'),tool:name,args:structuredClone(args),state:'awaiting'};demoPending.set(p.pending_id,p);demoEvent(name,'awaiting',p);return p;
}
function demoDecide(id,approve){const p=demoPending.get(id);if(!p)throw Error('预览操作不存在');if(p.state==='completed')return p.result;if(p.state!=='awaiting')throw Error('操作已处理');if(!approve){p.state='cancelled';demoEvent(p.tool,'cancelled',{id});return {cancelled:true}}
  const record={...p.args,id:demoId(p.tool==='create_document'?'DOC':'REQ')};demoData[p.tool==='create_document'?'documents':'requirements'].push(record);p.state='completed';p.result={record,verified:true,verification:'browser-only',source:'当前浏览器中的演示记录，非远程 API'};demoEvent(p.tool,'preview_completed',p.result);return p.result;
}
async function demoApi(path,data){
  if(path==='/api/status')return {app:'relay',version:'preview',model_ready:false,model_verified:false,model:'未连接模型',model_config:{provider:'deepseek',protocol:'openai',base_url:'https://api.deepseek.com',model:'未连接模型'},providers:{deepseek:{label:'DeepSeek',protocol:'openai',base_url:'https://api.deepseek.com',models:[]}},saved_model:false,secure_store_available:false,tools:demoTools};
  if(path==='/api/events')return structuredClone(demoEvents);
  if(path==='/api/records')return structuredClone(demoData);
  if(path==='/api/chats')return [...demoChats.values()].reverse().map(c=>({id:c.id,title:c.title,pending:!!c.pending}));
  if(path.startsWith('/api/chats/')){const c=demoChats.get(path.split('/').pop());if(!c)throw Error('刷新后演示会话已重置');return {chat_id:c.id,messages:c.messages,pending:c.pending,can_resume:false}}
  if(path.startsWith('/api/pending/')){const p=demoPending.get(path.split('/').pop());if(!p)throw Error('刷新后演示操作已重置');return p}
  if(path==='/api/invoke')return structuredClone(demoInvoke(data.tool,data.args));
  if(path==='/api/decide')return structuredClone(demoDecide(data.id,data.approve));
  if(path==='/api/health')return {mode:'浏览器内交互预览',model_connected:false,external_api_calls:false,note:'此站点不运行 Python 服务；完整模型和业务接口功能请下载运行。'};
  if(path==='/api/evaluations')return {mode:'preview',note:'这里演示交互，不代表真实模型或跨服务 HTTP 验收。'};
  if(path==='/api/evaluate'){
    if(data.mode==='model')throw Error('在线预览不运行真实模型。请下载项目，在本地验收中心配置并测试。');
    const before=demoData.documents.length;const p=demoInvoke('create_document',{title:'浏览器演示自检',body:'仅用于预览自检'});const notWritten=demoData.documents.length===before;demoDecide(p.pending_id,true);const once=demoData.documents.length===before+1;demoDecide(p.pending_id,true);return {mode:'browser-preview',passed:[notWritten,once,demoData.documents.length===before+1].filter(Boolean).length,total:3,seconds:0,model_used:false,http_requests:false,note:'仅检查浏览器演示状态，不是完整版工程验收。'};
  }
  if(path.startsWith('/api/model/'))throw Error('公开预览不接收密钥、不调用模型。请下载项目使用自己的 API。');
  if(path.startsWith('/api/connectors/'))throw Error('预览只展示连接器配置；真实接口接入请下载运行完整版。');
  if(path==='/api/chat'){
    let c=demoChats.get(data.chat_id);if(!c){c={id:demoId('CHAT'),title:data.text||'演示任务',messages:[],pending:null};demoChats.set(c.id,c)}
    let answer='',trace=[];
    if(c.pending){if(typeof data.decision!=='boolean')throw Error('请先确认或取消预览操作');const p=c.pending;const result=demoDecide(p.pending_id,data.decision);trace.push({tool:p.tool,result});c.pending=null;answer=data.decision?'演示记录已生成。可在业务数据页查看。这一步只修改浏览器内数据，没有请求外部系统。':'已取消演示写入。'}
    else {
      const text=data.text||'';c.messages.push({role:'user',content:text});
      if(/周报/.test(text)){const tasks=demoInvoke('list_tasks',{project:'星河'});trace.push({tool:'list_tasks',result:tasks});const body=tasks.result.filter(t=>t.status==='已完成').map(t=>t.id+' '+t.title+'：'+t.status).join('\n');c.pending=demoInvoke('create_document',{title:'星河项目周报（演示）',body});trace.push({tool:'create_document',result:c.pending});answer='预设流程演示：读取示例任务，再用模板组织周报，等待你确认保存。此内容没有经过模型生成。'}
      else if(/需求|反馈/.test(text)){c.pending=demoInvoke('create_requirement',{project:'星河',title:'优化登录提示（演示）',description:'登录失败时提示原因，并提供重试入口。'});trace.push({tool:'create_requirement',result:c.pending});answer='预设流程演示：这是一个固定示例需求。核对后可确认创建；完整版本才会由模型理解你的自定义内容。'}
      else if(/任务|清单|未完成/.test(text)){const r=demoInvoke('list_tasks',{project:'星河'});trace.push({tool:'list_tasks',result:r});answer='星河项目的演示任务：\n'+r.result.map(t=>t.id+' '+t.title+' · '+t.status).join('\n')+'\n\n这是浏览器内示例数据，未调用真实模型。'}
      else answer='此预览只提供三种预设交互：查询任务、创建示例需求、生成示例周报。自由对话与真实接口接入请下载项目运行。';
    }
    c.messages.push({role:'assistant',content:[{type:'text',text:answer}]});return structuredClone({chat_id:c.id,answer,trace,pending:c.pending});
  }
  throw Error('该功能仅在下载运行的完整版中提供');
}
