const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const path=require('node:path');
const context=vm.createContext({structuredClone});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../docs/preview-api.js'),'utf8'),context);
async function call(route,body){context.route=route;context.body=body;return JSON.parse(JSON.stringify(await vm.runInContext('demoApi(route,body)',context)))}
(async()=>{
 let checks=0;
 const tasks=await call('/api/invoke',{tool:'list_tasks',args:{project:'星河'}});assert.equal(tasks.result.length,3);checks++;
 const pending=await call('/api/invoke',{tool:'create_document',args:{title:'测试草稿',body:'仅用于浏览器预览'}});
 assert.equal((await call('/api/records')).documents.length,0);checks++;
 const created=await call('/api/decide',{id:pending.pending_id,approve:true});assert.equal(created.verification,'browser-only');assert.equal((await call('/api/records')).documents.length,1);checks++;
 await call('/api/decide',{id:pending.pending_id,approve:true});assert.equal((await call('/api/records')).documents.length,1);checks++;
 const cancel=await call('/api/invoke',{tool:'create_requirement',args:{project:'星河',title:'取消',description:'不应保存'}});await call('/api/decide',{id:cancel.pending_id,approve:false});assert.equal((await call('/api/records')).requirements.length,0);checks++;
 const chat=await call('/api/chat',{text:'生成示例周报'});assert.equal(chat.pending.tool,'create_document');assert.match(chat.answer,/没有经过模型/);await call('/api/chat',{chat_id:chat.chat_id,decision:true});assert.equal((await call('/api/records')).documents.length,2);checks++;
 await assert.rejects(()=>call('/api/model/configure',{key:'must-not-leave-browser'}),/不接收密钥/);checks++;
 const report=await call('/api/evaluate',{mode:'engineering'});assert.equal(report.passed,3);assert.equal(report.http_requests,false);checks++;
 console.log(`${checks} browser-preview state checks passed; no model or external API calls`);
})().catch(e=>{console.error(e);process.exitCode=1});
