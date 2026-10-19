from __future__ import annotations
import json,os,time
import uuid
from pathlib import Path
from urllib.parse import urlparse
import requests
import streamlit as st
from dotenv import dotenv_values
from n8n_client import DEFAULT_WEBHOOK,N8nError,ask_n8n,make_payload

ROOT=Path(__file__).resolve().parent
st.set_page_config(page_title='BCMID | Evidence workspace',page_icon=':material/radiology:',layout='wide')
for key,default in {'result':None,'result_question':'','elapsed':0.,'recent_runs':[],
                    'chat_messages':[],'chat_session_id':uuid.uuid4().hex}.items():
 if key not in st.session_state:st.session_state[key]=default
webhook=(dotenv_values(ROOT/'.env').get('N8N_WEBHOOK_URL') or os.getenv('N8N_WEBHOOK_URL') or DEFAULT_WEBHOOK).strip()
parsed=urlparse(webhook)

@st.cache_data(ttl=15,show_spinner=False)
def service_status(webhook_url):
 result={}
 parsed=urlparse(webhook_url)
 n8n_health=f'{parsed.scheme}://{parsed.netloc}/healthz' if parsed.hostname in {'localhost','127.0.0.1','::1'} else None
 for name,url in [('n8n',n8n_health),('Tools API','http://127.0.0.1:8000/health')]:
  if not url:result[name]=False;continue
  try:result[name]=requests.get(url,timeout=5).status_code==200
  except requests.RequestException:result[name]=False
 return result

def local_image(reference):
 root=(ROOT/'projet/bcmid/BCMID_extracted').resolve()
 path=(root/str(reference)).resolve()
 return path if path.is_relative_to(root) and path.is_file() else None

with st.sidebar:
 st.title(':material/radiology: BCMID')
 st.caption('EVIDENCE WORKSPACE')
 page=st.radio('Workspace',['Chat assistant','Explore evidence','Testing guide'],label_visibility='collapsed',key='page')
 st.divider()
 st.caption('LOCAL SERVICES')
 health=service_status(webhook)
 for name,up in health.items():st.badge(f'{name} · '+('reachable' if up else 'offline'),color='green' if up else 'orange')
 st.caption('Service reachability does not confirm workflow activation.')
 if st.button('Refresh services',icon=':material/refresh:',width='stretch'):
  service_status.clear();st.rerun()
 with st.expander('Connections'):
  st.caption('Requests go through this n8n webhook:');st.code(webhook,language=None)
  st.link_button('Open n8n workflow',f'{parsed.scheme}://{parsed.netloc}/workflow/bcmidLocalToolsDemo',width='stretch',disabled=parsed.hostname not in {'localhost','127.0.0.1','::1'})
  st.link_button('Tool API reference','http://127.0.0.1:8000/docs',width='stretch')
 st.divider()
 st.caption('Train-set evidence only. Similarity is not diagnostic confidence. Image search uses ViT, not the Kaggle CLIP backend.')
 if st.button('Clear results',icon=':material/delete:',width='stretch'):
  st.session_state.result=None;st.session_state.recent_runs=[];st.rerun()

if page=='Chat assistant':
 st.caption('BCMID / EVIDENCE ASSISTANT')
 st.title('Ask about the evidence.')
 st.write('Ask a report question, attach a reference image, or do both. Replies are limited to retrieved training evidence and checked quotations.')
 st.info('Research demonstration only. Similar-case evidence belongs to other cases; it is not a finding about the uploaded patient and cannot diagnose or recommend care.')
 allow_quote=st.toggle('Allow a checked quotation for explicit follow-up or BI-RADS wording',value=False,
                       help='Only source-verified, verbatim wording can be released. General questions return evidence cards.')
 for msg in st.session_state.chat_messages:
  with st.chat_message(msg['role']):
   if msg['role']=='user': st.write(msg['content'])
   else:
    st.badge(msg['label'],color=msg['color'])
    if msg.get('answer'): st.markdown(msg['answer'])
    elif msg.get('notice'): st.info(msg['notice'])
    details=msg.get('details')
    if details:
     if details.get('report_passages'):
      st.markdown('#### Report evidence')
      for row in details['report_passages']:
       with st.container(border=True):
        st.markdown(f"**Passage {row.get('rank','?')} · Similar case {row.get('patient_id','not supplied')}**")
        st.caption(f"{row.get('split','unknown split')} · {row.get('source','unknown source')} · {row.get('passage_id','no passage ID')}")
        st.write(row.get('text',''))
        if row.get('similarity') is not None: st.caption(f"Similarity {row['similarity']:.3f} · not a confidence score")
     if details.get('similar_images'):
      st.markdown('#### Similar images · other training cases')
      st.caption('These are visually similar training examples. Their reports and metadata are not facts about the uploaded image.')
      for row in details['similar_images']:
       with st.container(border=True):
        st.markdown(f"**Rank {row.get('rank','?')} · Similar case {row.get('patient_id','not supplied')}**")
        st.write(f"{row.get('modality','Unknown modality')} · {row.get('split','unknown split')} · similarity {row.get('similarity',0):.3f}")
        st.caption(f"{row.get('source_image_reference','')} · {row.get('image_id','')}")
     if details.get('citations'): st.caption('Checked source IDs: '+', '.join(details['citations']))
     with st.expander('Run details'):
      st.caption(f"Elapsed {msg.get('seconds',0):.1f} s · intent {details.get('intent','unknown')} · request {details.get('request_id','unknown')}")
      st.write('Tools called');st.code(' → '.join(details.get('tools_called',[])) or 'No tools reported',language=None)
      st.write('Evidence check');st.json(details.get('checker',{}))
      st.write('Execution trace');st.code('\n'.join(details.get('trace',[])) or 'No trace reported',language=None)
      if details.get('errors'): st.error(' · '.join(details['errors']))
      if details.get('limitations'):
       for item in details['limitations']: st.caption(item)
      st.download_button('Download this result',json.dumps(details,indent=2),file_name='bcmid_result.json',mime='application/json',key=f"download_{msg.get('request_id','none')}")
 if not st.session_state.chat_messages:
  st.markdown('**Try a first question**')
  st.caption('“Find report findings about annual follow up.”  ·  “Find similar images for this reference.”  ·  “Find report evidence for this image.”')
 if st.button('Clear conversation',icon=':material/delete_sweep:',width='content'):
  st.session_state.chat_messages=[]
  st.session_state.chat_session_id=uuid.uuid4().hex
  st.session_state.result=None
  st.rerun()
 submission=st.chat_input('Ask a question or attach a reference image',accept_file=True,
                          file_type=['png','jpg','jpeg','webp'],key='chat_input')
 if submission:
  question=(submission.text or '').strip()
  uploads=list(submission.files or [])
  upload=uploads[0] if uploads else None
  image_bytes=upload.getvalue() if upload else None
  if not question and not image_bytes:
   st.warning('Enter a question or attach one image.')
  else:
   user_label=question or 'Find similar images.'
   if upload: user_label += f"\n\nAttached image: {upload.name}"
   st.session_state.chat_messages.append({'role':'user','content':user_label})
   if not question and image_bytes: question='Find similar images.'
   with st.chat_message('user'):
    st.write(user_label)
    if upload: st.image(image_bytes,caption='Uploaded reference image',width=280)
   with st.chat_message('assistant'):
    status_slot=st.status('Sending this turn to the local n8n workflow…',expanded=True)
    start=time.monotonic()
    try:
     payload=make_payload(question,retrieve_only=not allow_quote,image=image_bytes,
                          filters={'split':'train'},session_id=st.session_state.chat_session_id)
     reply=ask_n8n(webhook,payload,timeout=180)
     elapsed=time.monotonic()-start
     d=reply.details
     label,colour={
      'answered':('Checked answer','green'),'retrieved':('Evidence retrieved','blue'),
      'abstained':('Insufficient evidence · answer withheld','orange'),'tool_error':('Tool error','red'),
      'out_of_scope':('Outside research scope','orange'),'not_found':('No matches','orange'),
      'ok':('Metadata found','green'),'invalid_request':('Invalid request','orange')
     }[reply.status]
     notice=None if reply.status=='answered' else reply.answer
     assistant_text=reply.answer if reply.status=='answered' else notice
     st.badge(label,color=colour)
     if assistant_text: (st.markdown(assistant_text) if reply.status=='answered' else st.info(assistant_text))
     if d.get('report_passages'):
      st.markdown('#### Report evidence')
      for row in d['report_passages']:
       with st.container(border=True):
        st.markdown(f"**Passage {row.get('rank','?')} · Similar case {row.get('patient_id','not supplied')}**")
        st.caption(f"{row.get('split','unknown split')} · {row.get('source','unknown source')} · {row.get('passage_id','no passage ID')}")
        st.write(row.get('text',''))
        if row.get('similarity') is not None: st.caption(f"Similarity {row['similarity']:.3f} · not a confidence score")
     if d.get('similar_images'):
      st.markdown('#### Similar images · other training cases')
      st.caption('Examples from other cases, shown separately from report evidence.')
      for row in d['similar_images']:
       with st.container(border=True):
        img_col,info_col=st.columns([1,3])
        path=local_image(row.get('source_image_reference',''))
        if path: img_col.image(str(path),width=180,alt='Retrieved similar training image')
        else: img_col.caption('Image preview unavailable locally')
        info_col.markdown(f"**Rank {row.get('rank','?')} · Similar case {row.get('patient_id','not supplied')}**")
        info_col.write(f"{row.get('modality','Unknown modality')} · {row.get('split','unknown split')} · similarity {row.get('similarity',0):.3f}")
        info_col.caption(f"{row.get('source_image_reference','')} · {row.get('image_id','')}")
     status_slot.update(label=f'Completed · {elapsed:.1f} seconds',state='complete',expanded=False)
     st.session_state.chat_messages.append({'role':'assistant','label':label,'color':colour,'answer':reply.answer if reply.status=='answered' else None,
       'notice':notice,'details':d,'seconds':elapsed,'request_id':d.get('request_id','unknown')})
    except N8nError as exc:
     elapsed=time.monotonic()-start
     status_slot.update(label='Request did not complete',state='error',expanded=True)
     st.error(str(exc))
     st.session_state.chat_messages.append({'role':'assistant','label':'Tool error','color':'red','notice':str(exc),
       'details':None,'seconds':elapsed,'request_id':'transport-error'})
  st.rerun()
 st.stop()

if page=='Testing guide':
 st.caption('BCMID / DEMONSTRATION')
 st.title('Test one path at a time.')
 st.write('Start with metadata, then reports, then images. Add generation after retrieval is working.')
 for title,body in [
 ('1 · Start the three services','Run the tool API on 8000, publish/start n8n on 5685, then open this interface on 8501. Refresh the service badges.'),
 ('2 · Check metadata','Select Metadata. Enter NONEXISTENT as the patient ID. Expect No matches, no answer and no report/image calls. Clear the ID and choose Mammogram + Has a report to test combined filters.'),
 ('3 · Retrieve reports','Select Reports. Keep Return source passages selected. Search for annual follow up. Expect passages with patient, source, split, rank and similarity. No generated answer is expected.'),
 ('4 · Retrieve images','Select Images, upload a local PNG/JPEG and enter its known patient ID. Expect similar train cases with different patient IDs. Scores are similarities, not confidence.'),
 ('5 · Combine both sources','Select Image + reports, add the same image and a report question. Expect both evidence types. Run details must include parallel_tool_overlap_seconds greater than zero.'),
 ('6 · Check the answer guard','Select Reports → Checked quotations and ask for explicit annual follow up or BI-RADS. An abstention is valid when source checks fail. Retry count must never exceed one.'),
 ('7 · Check rejection and failures','Ask Do I have cancer? Expect out_of_scope without tool calls. Use the full guide for malformed filters, empty-evidence fixtures and the service-down test.')]:
  with st.container(border=True):st.subheader(title);st.write(body)
 report=ROOT/'projet/UI_WORKFLOW_TEST_GUIDE.md'
 if report.exists():st.download_button('Download full testing report',report.read_text(encoding='utf-8-sig'),file_name=report.name,mime='text/markdown',icon=':material/download:')
 st.stop()

st.caption('BCMID / BREAST IMAGING RESEARCH')
st.title('Explore the evidence.')
st.write('Find report passages, compare similar images, or look up a training case. Every result keeps its source.')
with st.container(horizontal=True):
 st.badge('Training cases',icon=':material/database:',color='blue')
 st.badge('Source checks',icon=':material/fact_check:',color='green')
 st.badge('Local processing',icon=':material/computer:',color='gray')
st.space('small')
mode=st.segmented_control('Search mode',['Reports','Images','Image + reports','Metadata'],default='Reports',key='mode') or 'Reports'
left,right=st.columns([2,1],gap='large')
with left:
 with st.container(border=True):
  st.subheader({'Reports':'Search report evidence','Images':'Find similar images','Image + reports':'Compare images and reports','Metadata':'Find a training case'}[mode])
  with st.form('search_form'):
   question='';upload=None;filters=None;generate=False;modality='Any';has_report='Any';birads='Any'
   if mode in ['Reports','Image + reports']:
    question=st.text_area('Question',value='Find report findings about annual follow up.',height=100,max_chars=2000,key=f'question_{mode}')
    output=st.radio('Result type',['Return source passages','Checked quotations'],key=f'output_{mode}',help='Checked quotations are available for explicit follow-up / BI-RADS wording. Failed checks produce an abstention.')
    generate=output=='Checked quotations'
   if mode in ['Images','Image + reports']:
    upload=st.file_uploader('Reference image',type=['png','jpg','jpeg','webp'],key=f'image_{mode}')
    modality=st.selectbox('Image modality',['Any','Mammogram','Ultrasound'],key=f'modality_{mode}')
    if mode=='Images':question='Find similar images'
   pid=st.text_input('Patient ID' if mode=='Metadata' else 'Query patient ID (optional)',key=f'patient_{mode}',help='Metadata searches this ID. Similar-case retrieval excludes this ID when supplied.')
   if mode=='Metadata':
    a,b=st.columns(2)
    modality=a.selectbox('Modality',['Any','Mammogram','Ultrasound'],key='metadata_modality')
    has_report=b.selectbox('Report availability',['Any','Has a report','No report'],key='metadata_has_report')
    birads=st.selectbox('Recorded BI-RADS filter',['Any','0','1','2','3','4','4a','4b','4c','5','6'],help='Filters existing train metadata; does not assign a category to an image.')
   submitted=st.form_submit_button('Search evidence' if mode!='Metadata' else 'Look up cases',type='primary',icon=':material/search:',width='stretch')
with right:
 with st.container(border=True):
  st.subheader('A traceable search')
  st.markdown('**01 · Choose** a question, image or filter.\n\n**02 · Retrieve** matching training evidence.\n\n**03 · Inspect** the sources and checks.')
  st.caption('Similar cases describe their own patients. Findings are never assigned to your uploaded patient.')
 if mode in ['Images','Image + reports']:st.info('Image search uses saved ViT vectors. Report links are patient-level; the exact examination match is not verified.')
 else:st.info('This is an evidence research workspace. It does not diagnose patients or provide new BI-RADS assessments.')

if submitted:
 st.session_state.result=None
 try:
  if mode in ['Images','Image + reports'] and upload is None:raise N8nError('Upload a reference image to run this search.')
  if mode in ['Reports','Image + reports'] and not question.strip():raise N8nError('Enter a report question.')
  filters={'split':'train'}
  if modality!='Any':filters['modality']=modality
  if mode=='Metadata':
   if pid.strip():filters['patient_id']=pid.strip()
   if has_report!='Any':filters['has_report']=has_report=='Has a report'
   if birads!='Any':filters['birads']=birads
  intent={'Reports':'report_question','Images':'image_search','Image + reports':'image_and_report_question','Metadata':'metadata_lookup'}[mode]
  payload=make_payload(question,patient_id=pid if mode!='Metadata' else None,filters=filters,image=upload.getvalue() if upload else None,intent=intent,retrieve_only=not generate)
  start=time.monotonic()
  with st.spinner('Retrieving and checking evidence…'):
   reply=ask_n8n(webhook,payload)
  st.session_state.result=reply
  st.session_state.result_question=question or 'Structured metadata lookup'
  st.session_state.elapsed=time.monotonic()-start
  st.session_state.recent_runs=([{'mode':mode,'status':reply.status,'seconds':round(st.session_state.elapsed,1)}]+st.session_state.recent_runs)[:6]
 except N8nError as exc:st.error(str(exc))

reply=st.session_state.result
if reply:
 d=reply.details
 st.divider();st.subheader('Search results')
 st.caption(st.session_state.result_question)
 labels={'retrieved':'Evidence retrieved','answered':'Checked answer','abstained':'Answer withheld','ok':'Metadata found','not_found':'No matches','out_of_scope':'Outside scope','invalid_request':'Invalid request','tool_error':'Tool unavailable'}
 st.badge(labels[reply.status],color='green' if reply.status in ['retrieved','answered','ok'] else 'orange')
 if reply.status=='answered':st.write(reply.answer)
 elif reply.status in ['tool_error','invalid_request']:st.error(reply.answer)
 else:st.info(reply.answer)
 cols=st.columns(4)
 for col,label,value in zip(cols,['Report passages','Similar images','Metadata rows','Retrieval retries'],[len(d['report_passages']),len(d['similar_images']),len(d['metadata']),d['retry_count']]):col.metric(label,value,border=True)
 evidence,provenance,execution=st.tabs(['Evidence','Sources','Run details'])
 with evidence:
  if d['metadata']:st.dataframe(d['metadata'],hide_index=True,width='stretch')
  for row in d['report_passages']:
   with st.container(border=True):
    st.markdown(f"**Passage {row['rank']} · Patient {row['patient_id']}**")
    st.caption(f"{row['split']} · {row['source']} · {row['passage_id']}")
    st.text(row['text'])
    if row.get('similarity') is not None:st.caption(f"Similarity {row['similarity']:.3f}")
  for row in d['similar_images']:
   with st.container(border=True):
    image_col,text_col=st.columns([1,3])
    path=local_image(row['source_image_reference'])
    if path:image_col.image(str(path),width=180,alt=f"Retrieved {row['modality']} for patient {row['patient_id']}")
    else:image_col.caption('Image preview unavailable locally')
    text_col.markdown(f"**Rank {row['rank']} · Patient {row['patient_id']}**")
    text_col.write(f"{row['modality']} · {row['split']} · similarity {row['similarity']:.3f}")
    text_col.caption(row['source_image_reference']);text_col.caption(row['image_id'])
  if not any(d[k] for k in ['metadata','report_passages','similar_images']):st.caption('No evidence returned for this request.')
 with provenance:
  if d['sources']:st.dataframe(d['sources'],hide_index=True,width='stretch')
  else:st.caption('No retrieval source registry for this request. Metadata provenance is included in its rows.')
  if d['citations']:st.write('Accepted citations');st.code('\n'.join(d['citations']),language=None)
  for limitation in d['limitations']:st.caption(limitation)
 with execution:
  st.caption(f"Elapsed: {st.session_state.elapsed:.1f} s · Intent: {d['intent']} · Request: {d['request_id']}")
  st.write('Evidence checker');st.json(d['checker'])
  st.write('Tools called');st.code(' → '.join(d['tools_called']) or 'No tools called',language=None)
  st.write('Execution trace');st.code('\n'.join(d['trace']),language=None)
  if d['errors']:st.error(' · '.join(d['errors']))
  st.download_button('Download this result',json.dumps(d,indent=2),file_name='bcmid_result.json',mime='application/json',icon=':material/download:')
 if st.session_state.recent_runs:
  with st.expander('Recent runs in this session'):st.dataframe(st.session_state.recent_runs,hide_index=True)
else:
 st.caption('Your evidence, source references and execution details will appear here after a search.')
