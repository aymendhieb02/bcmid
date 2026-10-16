from pathlib import Path
from unittest.mock import patch
from streamlit.testing.v1 import AppTest
from n8n_client import parse_response
from test_n8n_client import result
APP=Path(__file__).parent/'app.py'
def load():return AppTest.from_file(str(APP),default_timeout=15).run()
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
