"""Reproducible native n8n 2.22 workflow export; no credentials or clinical data."""
import json, uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parent
nodes=[]; connections={}
def node(name,kind,params,version=1):
    nodes.append(dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL,'bcmid/'+name)),name=name,type='n8n-nodes-base.'+kind,typeVersion=version,position=[(len(nodes)%6)*280,(len(nodes)//6)*220],parameters=params))
def link(a,b,out=0,inp=0):
    outputs=connections.setdefault(a,{'main':[]})['main']
    while len(outputs)<=out: outputs.append([])
    outputs[out].append(dict(node=b,type='main',index=inp))
def code(name,file): node(name,'code',{'jsCode':(ROOT/'workflow_code'/file).read_text(encoding='utf-8-sig')},2)
def http(name,path,body):
    node(name,'httpRequest',dict(method='POST',url='http://127.0.0.1:8000'+path,sendBody=True,specifyBody='json',jsonBody='={{ JSON.stringify('+body+') }}',options={'timeout':180000}),4.2)
    nodes[-1]['onError']='continueErrorOutput'
    link(name,'Tool transport failure',1)
def condition(name,expression):
    node(name,'if',{'conditions':{'options':{'caseSensitive':True,'leftValue':'','typeValidation':'strict'},'conditions':[{'id':name,'leftValue':'={{ '+expression+' }}','rightValue':'','operator':{'type':'boolean','operation':'true','singleValue':True}}],'combinator':'and'},'options':{}},2.2)
node('Ask webhook','webhook',{'httpMethod':'POST','path':'bcmid-agent','responseMode':'responseNode','options':{}},2)
nodes[-1]['webhookId']='bcmid-agent-local'
for name,file in [('Normalize request','normalize.js'),('Classify intent','classify.js'),('Validate allowlisted plan','plan.js')]: code(name,file)
node('Route intent','switch',{'mode':'expression','numberOutputs':5,'output':"={{ ['report_question','image_search','image_and_report_question','metadata_lookup','out_of_scope_or_insufficient'].indexOf($json.state.intent) }}"},3.2)
http('Report retrieval','/tools/report-search','{state:$json.state,top_k:5}')
http('Image retrieval ViT','/tools/image-search','{state:$json.state,image_base64:$json.image_base64,top_k:5}')
http('Start report job','/tools/report-jobs','{state:$json.state,top_k:5}')
http('Start image job','/tools/image-jobs','{state:$json.state,image_base64:$json.image_base64,top_k:5}')
node('Merge parallel receipts','merge',{'mode':'append','numberInputs':2},3)
code('Validate parallel receipts','merge_jobs.js')
http('Collect parallel retrievals','/tools/jobs/collect','{state:$json.state,jobs:$json.jobs}')
http('Metadata lookup','/tools/metadata','{state:$json.state}')
code('Assemble evidence registry','registry.js')
http('Check evidence sufficiency','/tools/evidence-check',"{state:$json.state,stage:'evidence'}")
condition('Evidence sufficient',"$json.state.checker.decision === 'sufficient'")
condition('Generation needed','$json.state.needs_generation === true')
code('Freeze generation evidence','generation.js')
http('Generate local quotations','/tools/generate','{state:$json.state}')
http('Check exact answer evidence','/tools/evidence-check',"{state:$json.state,stage:'answer'}")
condition('Answer accepted',"$json.state.checker.decision === 'accept'")
condition('One retry allowed',"$json.state.retry_count === 0 && $json.state.tools.includes('report_search') && !$json.state.errors.length && !$json.state.checker.problems.some(p => /mismatch|leakage|duplicate/.test(p))")
code('Targeted rewrite retry 1','retry.js')
http('Retry report retrieval','/tools/report-search','{state:$json.state,top_k:8}')
code('Tool transport failure','error.js')
code('Finalize safe response','finalize.js')
node('Respond','respondToWebhook',{'respondWith':'json','responseBody':'={{ $json }}','options':{}},1.4)
node('Administration note','stickyNote',{'content':'## Local tools, visible n8n orchestration\nAsk only. Existing train E5/Chroma and ViT vectors are reused. Ingestion is deliberately omitted: the old cloud embedding/store nodes would create an incompatible index.\nCombined: dispatch two atomic jobs, Merge receipts, collect concurrently executing tools.\nOne report retry maximum. Generation is checked against frozen passages. ViT is not Kaggle CLIP.\nNative Windows URLs; Docker n8n needs host.docker.internal and an explicitly reachable API bind.','height':280,'width':500},1)
for a,b in [('Ask webhook','Normalize request'),('Normalize request','Classify intent'),('Classify intent','Validate allowlisted plan'),('Validate allowlisted plan','Route intent')]: link(a,b)
for i,names in enumerate([['Report retrieval'],['Image retrieval ViT'],['Start report job','Start image job'],['Metadata lookup'],['Finalize safe response']]):
    for name in names: link('Route intent',name,i)
link('Start report job','Merge parallel receipts',inp=0);link('Start image job','Merge parallel receipts',inp=1)
link('Merge parallel receipts','Validate parallel receipts');link('Validate parallel receipts','Collect parallel retrievals')
for name in ['Report retrieval','Image retrieval ViT','Collect parallel retrievals','Retry report retrieval']:link(name,'Assemble evidence registry')
for a,b in [('Assemble evidence registry','Check evidence sufficiency'),('Check evidence sufficiency','Evidence sufficient'),('Freeze generation evidence','Generate local quotations'),('Generate local quotations','Check exact answer evidence'),('Check exact answer evidence','Answer accepted'),('Targeted rewrite retry 1','Retry report retrieval'),('Finalize safe response','Respond')]:link(a,b)
link('Evidence sufficient','Generation needed');link('Evidence sufficient','One retry allowed',1)
link('Generation needed','Freeze generation evidence');link('Generation needed','Finalize safe response',1)
link('Answer accepted','Finalize safe response');link('Answer accepted','One retry allowed',1)
link('One retry allowed','Targeted rewrite retry 1');link('One retry allowed','Finalize safe response',1)
for name in ['Metadata lookup','Tool transport failure']:link(name,'Finalize safe response')
# Deliberate left-to-right reading order. Positions/notes only; tool decisions,
# connections, node IDs and the one-retry loop remain unchanged.
positions={
 'Ask webhook':(0,0),'Normalize request':(220,0),'Classify intent':(440,0),
 'Validate allowlisted plan':(660,0),'Route intent':(880,0),
 'Report retrieval':(1260,-240),'Image retrieval ViT':(1260,0),
 'Start report job':(1260,260),'Start image job':(1260,460),
 'Merge parallel receipts':(1500,340),'Validate parallel receipts':(1740,340),
 'Collect parallel retrievals':(1980,340),'Metadata lookup':(1260,720),
 'Assemble evidence registry':(2380,0),'Check evidence sufficiency':(2620,0),
 'Evidence sufficient':(2860,0),'Generation needed':(3100,0),
 'Freeze generation evidence':(3400,0),'Generate local quotations':(3640,0),
 'Check exact answer evidence':(3880,0),'Answer accepted':(4120,0),
 'One retry allowed':(3100,680),'Targeted rewrite retry 1':(2820,680),
 'Retry report retrieval':(2540,680),'Finalize safe response':(4460,0),
 'Respond':(4700,0),'Tool transport failure':(4460,680),
 'Administration note':(0,550),
}
for item in nodes:item['position']=list(positions[item['name']])
admin=next(n for n in nodes if n['name']=='Administration note')
admin['parameters'].update(width=1020,height=360,color=7,content='## Reading this workflow\nFollow 01 → 05 from left to right. Only one intent lane is selected. Combined requests dispatch both retrieval jobs and meet at Merge.\n\n**Lower lane:** one report retry maximum; the counter is visible. Metadata and unsupported requests go straight to the final response. HTTP failures converge on the lower-right handler.\n\n**Saved artifacts:** E5 / Chroma reports and ViT images. ViT is not Kaggle CLIP. Ingestion is an offline administrative notebook task, never part of Ask.\n\n**Local endpoints:** n8n :5685 · Python tools :8000 · Streamlit :8501.')
groups=[
 ('01 · Receive and route',(-80,-430),1120,760,5,'Normalize input → classify intent → validate tools.\nSwitch outputs: reports / images / combined / metadata / unsupported.'),
 ('02 · Retrieve the right evidence',(1160,-470),1100,1410,4,'Top lanes: reports or images. Middle: both tools → Merge.\nBottom: metadata only. These paths never rebuild indexes.'),
 ('03 · Validate evidence',(2280,-430),1000,760,3,'Keep source identities, check sufficiency, then decide whether a generated answer is needed.\nTrue continues right; insufficient evidence enters the retry lane.'),
 ('04 · Generate and check',(3300,-430),1000,760,6,'Freeze exact passages → local Qwen → check source quotations.\nOnly an accepted answer can be released. A failure may use the one retry.'),
 ('05 · Respond',(4360,-430),620,760,5,'One consistent response for every path.\nAnswer / retrieval / metadata / abstention / rejection.'),
 ('06 · One retry, then stop',(2420,450),940,500,2,'Read this lane right → left. Counter 0 → 1; rewrite; retrieve reports again.\nThe next failure abstains. Images are retained for combined requests.'),
 ('07 · Tool unavailable',(4360,450),620,500,7,'Transport errors return safe JSON with no answer.\nThis is an error exit, not another retry loop.'),
]
for title,pos,width,height,color,description in groups:
    node(title,'stickyNote',{'content':f'## {title}\n{description}','width':width,'height':height,'color':color})
    nodes[-1]['position']=list(pos)
workflow=dict(id='bcmidLocalToolsDemo',name='BCMID local tools — visible orchestration',active=False,nodes=nodes,connections=connections,settings={'executionOrder':'v1','executionTimeout':600,'saveDataSuccessExecution':'none','saveDataErrorExecution':'none','saveManualExecutions':False,'saveExecutionProgress':False},pinData={})
for name in ['bcmid_workflow.json','bcmid_agent_workflow.json']:(ROOT/name).write_text(json.dumps(workflow,indent=2,ensure_ascii=False),encoding='utf-8')
print(f'Wrote {len(nodes)} nodes; two filenames are aliases: import only one.')
