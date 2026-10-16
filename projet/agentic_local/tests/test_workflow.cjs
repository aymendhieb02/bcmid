const fs=require('fs'),path=require('path'),assert=require('assert/strict');
const root=path.resolve(__dirname,'../../n8n'), AsyncFunction=Object.getPrototypeOf(async function(){}).constructor;
async function run(file,json,items){return (await new AsyncFunction('$input',fs.readFileSync(path.join(root,'workflow_code',file),'utf8'))({first:()=>({json}),all:()=>items??[{json}]}))[0].json;}
async function route(body){let x=await run('normalize.js',{body});x=await run('classify.js',x);return run('plan.js',x);}
const cases=[
['text report',{question:'Find report findings'},'report_question','report_search'],
['similar image',{question:'Find similar images',image_base64:'AA=='},'image_search','image_search'],
['image modality',{question:'Find similar images',image_base64:'AA==',filters:{modality:'Mammogram'}},'image_search','image_search'],
['combined',{question:'Report follow up',image_base64:'AA=='},'image_and_report_question','report_search,image_search'],
['patient metadata',{question:'lookup patient',patient_id:'train-a'},'metadata_lookup','metadata_lookup'],
['combined filters',{filters:{modality:'Mammogram',has_report:true}},'metadata_lookup','metadata_lookup'],
['unknown patient',{filters:{patient_id:'NONEXISTENT'}},'metadata_lookup','metadata_lookup'],
['invalid filter',{filters:{split:'test'}},'out_of_scope_or_insufficient',''],
['diagnosis',{question:'Diagnose this image',image_base64:'AA=='},'out_of_scope_or_insufficient',''],
['no evidence path',{question:'Find report of nonexistent phrase'},'report_question','report_search'],
['query exclusion',{question:'Find similar images',image_base64:'AA==',patient_id:'query'},'image_search','image_search'],
['diagnosis explicit bypass',{question:'Do I have cancer?',intent:'report_question'},'out_of_scope_or_insufficient',''],
['unknown intent',{question:'report',intent:'shell'},'out_of_scope_or_insufficient',''],
['missing required image',{intent:'image_search'},'out_of_scope_or_insufficient','']];
(async()=>{
for(const [name,body,intent,tools]of cases){const x=await route(body);assert.equal(x.state.intent,intent,name);assert.equal(x.state.tools.join(','),tools,name);}
let x=await route({question:'report follow up'});x.state.tools=['shell'];assert.equal((await run('plan.js',x)).state.status,'invalid_request');
x=await route({question:'report follow up'});let retry=await run('retry.js',x);assert.equal(retry.state.retry_count,1);await assert.rejects(()=>run('retry.js',retry));
const s=(await route({question:'report'})).state;
const failure=(await new AsyncFunction('$input','$',fs.readFileSync(path.join(root,'workflow_code/error.js'),'utf8'))({first:()=>({json:{}})},()=>({first:()=>({json:{state:s}})})))[0].json.state;assert.equal(failure.status,'tool_error');assert.equal(failure.intent,'report_question');assert.equal(failure.answer,null);
const pair=await run('merge_jobs.js',{},[{json:{state:s,kind:'report',job_id:'a'}},{json:{state:s,kind:'image',job_id:'b'}}]);assert.deepEqual(pair.jobs,['a','b']);
await assert.rejects(()=>run('merge_jobs.js',{},[{json:{state:s,kind:'report',job_id:'a'}},{json:{state:{...s,request_id:'other'},kind:'image',job_id:'b'}}]));
s.candidate_answer='Unsupported answer';s.checker.decision='abstain';let final=await run('finalize.js',{state:s});assert.equal(final.answer,null);assert.equal(final.status,'abstained');assert.ok(!('candidate_answer'in final));
s.patient_id='query';s.reports=[{passage_id:'p',patient_id:'query',split:'train',source:'r',rank:1}];let reg=await run('registry.js',{state:s});assert.equal(reg.state.registry.length,0);assert.ok(reg.state.errors.length);
const wf=JSON.parse(fs.readFileSync(path.join(root,'bcmid_workflow.json')));assert.ok(wf.nodes.length>=25);assert.ok(!wf.nodes.some(n=>/agent/i.test(n.type)));for(const [name,c]of Object.entries(wf.connections)){assert.ok(wf.nodes.some(n=>n.name===name));for(const out of c.main)for(const edge of out)assert.ok(wf.nodes.some(n=>n.name===edge.node));}
console.log(JSON.stringify({routing_cases:cases.length,additional:'plan, retry, merge, abstention, exclusion, graph',status:'passed'}));
})().catch(e=>{console.error(e);process.exitCode=1});
