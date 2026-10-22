from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from n8n_client import parse_response
from test_n8n_client import result
APP=Path(__file__).parent/'app.py'
def load(page='Explore evidence'):
 a=AppTest.from_file(str(APP),default_timeout=15).run()
 if page!='Chat assistant':a.radio(key='page').set_value(page).run()
 return a
def submit(a):
 button=next(b for b in a.button if b.label in ['Search evidence','Look up cases'])
 return button.click().run()
def test_initial_page_and_modes():
 a=load();assert not a.exception
 for mode in ['Images','Image + reports','Metadata','Reports']:
  a.segmented_control(key='mode').set_value(mode).run();assert not a.exception

def test_report_submission_uses_current_contract():
 with patch('n8n_client.ask_n8n',return_value=parse_response(result())) as ask:
  a=submit(load());assert not a.exception
  p=ask.call_args.args[1];assert p['intent']=='report_question' and p['retrieve_only'] is True
  assert any('Retrieved evidence is ready' in b.value for b in a.info)

def test_metadata_not_found_is_not_transport_error():
 with patch('n8n_client.ask_n8n',return_value=parse_response(result('not_found'))) as ask:
  a=load();a.segmented_control(key='mode').set_value('Metadata').run();a.text_input(key='patient_Metadata').set_value('NONEXISTENT');a=submit(a)
  assert not a.exception and not a.error
  assert ask.call_args.args[1]['filters']['patient_id']=='NONEXISTENT'

def test_missing_image_never_calls_workflow():
 with patch('n8n_client.ask_n8n') as ask:
  a=load();a.segmented_control(key='mode').set_value('Images').run();a=submit(a)
  assert not a.exception and a.error;ask.assert_not_called()

def test_abstention_is_visible_not_fabricated_answer():
 d=result('abstained');d['checker']={'decision':'abstain','problems':['nonverbatim_claim']}
 with patch('n8n_client.ask_n8n',return_value=parse_response(d)):
  a=submit(load());assert not a.exception
  assert any('did not support' in x.value for x in a.info)

def test_testing_guide():
 a=load();a.radio(key='page').set_value('Testing guide').run();assert not a.exception
 assert any('Test one path' in t.value for t in a.title)

def test_chat_is_main_page_and_has_isolated_session():
 a=AppTest.from_file(str(APP),default_timeout=15).run()
 assert not a.exception
 assert any('Ask about the evidence' in t.value for t in a.title)
 first=a.session_state['conversation_session_id']
 assert len(first)==32 and first.isalnum()
 next(b for b in a.button if b.label=='Refresh services').click().run()
 assert a.session_state['conversation_session_id']==first
 assert not a.exception

def test_clear_conversation_rotates_session_and_drops_history():
 a=AppTest.from_file(str(APP),default_timeout=15).run()
 first=a.session_state['conversation_session_id']
 a.session_state['chat_messages']=[{'role':'user','content':'Follow up'}]
 a.run()
 next(b for b in a.button if b.label=='Clear conversation').click().run()
 assert a.session_state['chat_messages']==[]
 assert a.session_state['conversation_session_id']!=first
 assert not a.exception

def test_chat_replays_separate_report_evidence_and_trace():
 a=AppTest.from_file(str(APP),default_timeout=15).run()
 a.session_state['chat_messages']=[{'role':'assistant','label':'Evidence retrieved','color':'blue','answer':None,
  'notice':'Evidence ready.','seconds':1.2,'request_id':'synthetic','details':{
   'intent':'report_question','request_id':'synthetic','report_passages':[{'rank':1,'patient_id':'TRAIN_CASE','split':'train',
    'source':'synthetic.json','passage_id':'P_TEST','text':'Synthetic evidence excerpt.','similarity':0.9}],
   'similar_images':[],'citations':[],'tools_called':['Report_Search_API'],'checker':{'decision':'sufficient'},
   'trace':['report_search'],'errors':[],'limitations':[]}}]
 a.run()
 assert not a.exception
 assert any('Passage 1' in m.value for m in a.markdown)
 assert any('Synthetic evidence excerpt.' in m.value for m in a.markdown)

def test_pending_request_hides_uuid_and_new_chat_input_is_disabled():
 a=AppTest.from_file(str(APP),default_timeout=15).run()
 a.session_state['active_request']={'request_id':'a'*32,'question':'Synthetic report question'}
 a.run()
 assert not a.exception
 assert not any('a'*32 in c.value for c in a.code)
 assert any(b.label=='Check request status' for b in a.button)
 assert a.chat_input[0].disabled is True
 assert next(b for b in a.button if b.label=='Clear conversation').disabled is True

def test_same_request_can_recover_and_render_saved_result():
 from unittest.mock import patch
 saved=result('retrieved')
 with patch('n8n_client.lookup_n8n_request',return_value={'status':'completed','request_id':'b'*32,'result':saved}):
  a=AppTest.from_file(str(APP),default_timeout=15).run()
  a.session_state['active_request']={'request_id':'b'*32,'question':'Synthetic report question'}
  a.run()
  next(b for b in a.button if b.label=='Check request status').click().run()
 assert not a.exception
 assert a.session_state['active_request'] is None
 messages=a.session_state['chat_messages']
 assert messages[-1]['request_id']=='b'*32 and messages[-1]['label']=='Evidence retrieved'
 assert any('Retrieved evidence is ready' in m.value for m in a.info)

def test_chat_timeout_keeps_request_id_and_blocks_duplicate_submit():
 from unittest.mock import patch
 from n8n_client import N8nTimeout
 calls=[]
 def timeout(webhook,payload,timeout):
  calls.append(payload.copy())
  raise N8nTimeout(payload['request_id'])
 with patch('n8n_client.ask_n8n',side_effect=timeout):
  a=AppTest.from_file(str(APP),default_timeout=20).run()
  a.chat_input[0].set_value('Find report findings about annual follow up').run()
 assert not a.exception and len(calls)==1
 request_id=a.session_state['active_request']['request_id']
 assert calls[0]['request_id']==request_id and len(request_id)==32
 assert calls[0]['intent']=='report_question' and calls[0]['retrieve_only'] is False
 assert a.chat_input[0].disabled is True
 assert next(b for b in a.button if b.label=='Clear conversation').disabled is True

def test_metadata_card_shows_patient_association_and_not_checker_failure():
 from unittest.mock import patch
 data=result('ok');data['metadata']=[{'patient_id':'0583y19','split':'train','modalities':['Mammogram','Ultrasound'],'image_ids':['img_a','img_b'],
  'image_references':['0583y19/Mammogram/0583y19_L_CC_1.png'],'report_sources':['0583y19/0583y19_US_MG_Report.pdf'],
  'has_report':True,'has_structured_report':True,'image_count':2,'report_count':1,
  'association_level':'patient','association_exam_verified':False,
  'association_warning':'Patient-level association; exam-level link not verified.'}]
 data['intent']='metadata_lookup';data['filters']={'patient_id':'0583y19'}
 with patch('n8n_client.ask_n8n',return_value=parse_response(data)):
  a=load();a.segmented_control(key='mode').set_value('Metadata').run()
  a.text_input(key='patient_Metadata').set_value('0583y19');a=submit(a)
 assert not a.exception
 rendered=' '.join(x.value for x in a.markdown)
 assert 'Patient 0583y19' in rendered
 assert {'Images','Reports'} <= {m.label for m in a.metric}
 assert any('0583y19/0583y19_US_MG_Report.pdf' in c.value for c in a.code)
 assert any('not applicable' in x.value.lower() for x in a.caption)

def test_metadata_card_withholds_cross_patient_source():
 from metadata_ui import metadata_row_problems
 row={'patient_id':'1193y16','split':'train','report_sources':['9639y18/9639y18_US_MG_Report.pdf']}
 assert 'report_source_patient_mismatch' in metadata_row_problems(row,'1193y16')

def test_chat_metadata_lookup_displays_patient_card_and_preserves_id():
 from unittest.mock import patch
 data=result('ok');data['metadata']=[{'patient_id':'0583y19','split':'train','modalities':['Ultrasound'],'image_ids':['img_1'],
  'image_references':['0583y19/Ultrasound/0583y19_US_1.png'],'report_sources':['0583y19/0583y19_US_MG_Report.pdf'],
  'has_report':True,'has_structured_report':True,'image_count':1,'report_count':1,'association_level':'patient',
  'association_exam_verified':False,'association_warning':'Patient-level association; exam-level link not verified.'}]
 with patch('n8n_client.ask_n8n',return_value=parse_response(data)) as ask:
  a=AppTest.from_file(str(APP),default_timeout=15).run()
  a.chat_input[0].set_value('Metadata lookup patient ID 0583y19').run()
 assert not a.exception
 assert ask.call_args.args[1]['patient_id']=='0583y19'
 assert any('Patient 0583y19' in m.value for m in a.markdown)
 assert any('0583y19/0583y19_US_MG_Report.pdf' in c.value for c in a.code)

def test_chat_metadata_lookup_filters_bare_id_mention():
 from unittest.mock import patch
 data=result('ok');data['metadata']=[{'patient_id':'1193y16','split':'train','modalities':[],'image_ids':[],
  'image_references':[],'report_sources':['1193y16/1193y16_US_MG_Report.pdf'],'has_report':True,
  'has_structured_report':True,'image_count':0,'report_count':1,'association_level':'patient',
  'association_exam_verified':False,'association_warning':'Patient-level association; exam-level link not verified.'}]
 with patch('n8n_client.ask_n8n',return_value=parse_response(data)) as ask:
  a=AppTest.from_file(str(APP),default_timeout=15).run()
  a.chat_input[0].set_value('Metadata lookup 1193y16').run()
 assert not a.exception and ask.call_args.args[1]['patient_id']=='1193y16'

def test_recovery_by_id_is_hidden_and_stale_upload_notice_is_gone():
 from metadata_ui import chat_request_error
 a=AppTest.from_file(str(APP),default_timeout=15).run()
 assert not a.exception
 labels=[x.label for x in a.expander]
 assert not any('Recover a request by ID' in label for label in labels)
 visible=' '.join(x.value for x in a.caption)+ ' '.join(x.value for x in a.info)
 assert 'Image upload rejected with HTTP 403' not in visible
 assert chat_request_error('HTTP 403',has_image=True)=='Image request failed: HTTP 403'
 assert chat_request_error('HTTP 403',has_image=False)=='Request failed: HTTP 403'
