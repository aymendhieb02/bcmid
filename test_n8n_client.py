import base64
import pytest
import requests
from n8n_client import N8nError,ask_n8n,make_payload,parse_response

def result(status='retrieved'):
 return dict(status=status,request_id='test',intent='report_question',answer=None,sources=[],report_passages=[],similar_images=[],metadata=[],citations=[],tools_called=[],limitations=[],errors=[],trace=[],checker={'decision':'sufficient','problems':[]},generation_passage_ids=[],retry_count=0)

def test_payload_current_contract():
 p=make_payload('Question',patient_id='query',filters={'split':'train'},image=b'png',intent='image_and_report_question')
 assert p['image_base64']==base64.b64encode(b'png').decode()
 assert p['patient_id']=='query' and p['retrieve_only'] is True
 assert not {'case_id','chat_history','image_mime'}&p.keys()

@pytest.mark.parametrize('status',['retrieved','abstained','out_of_scope','not_found','ok','invalid_request','tool_error'])
def test_non_answer_statuses_are_displayable_and_hide_candidate(status):
 d=result(status);d['answer']='unaccepted';d['candidate_answer']='unaccepted'
 reply=parse_response(d)
 assert reply.status==status and 'unaccepted' not in reply.answer
 assert reply.details['answer'] is None and 'candidate_answer' not in reply.details

def test_accepted_answer_requires_exact_evidence_ids():
 d=result('answered');d.update(answer='Exact quotation [p1]',citations=['p1'],generation_passage_ids=['p1']);d['checker']['decision']='accept'
 assert parse_response(d).answer==d['answer']
 d['generation_passage_ids']=[]
 with pytest.raises(N8nError):parse_response(d)

def test_legacy_response_not_silently_accepted():
 with pytest.raises(N8nError):parse_response({'birads':3,'status':'ok'})

def test_empty_or_oversize_upload_rejected():
 for image in [b'',b'x'*(20*1024*1024+1)]:
  with pytest.raises(N8nError):make_payload(image=image)

def test_no_remote_webhook():
 with pytest.raises(N8nError):ask_n8n('https://example.com/webhook',{})

def test_http_error():
 class Response:status_code=503
 with pytest.raises(N8nError,match='503'):ask_n8n('http://localhost/webhook',{},post=lambda *a,**k:Response())

def test_connection_error():
 def post(*a,**k):raise requests.ConnectionError()
 with pytest.raises(N8nError,match='Cannot reach'):ask_n8n('http://localhost/webhook',{},post=post)

def test_timeout_no_automatic_resubmit():
 calls=[]
 def post(*a,**k):calls.append(1);raise requests.Timeout()
 with pytest.raises(N8nError,match='timed out'):ask_n8n('http://localhost/webhook',{},post=post)
 assert len(calls)==1
