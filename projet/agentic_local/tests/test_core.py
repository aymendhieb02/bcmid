"""Mocked tool contracts; no model downloads or index writes."""
import asyncio,sys,time,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock,MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import api,tools
from schemas import State,Report,ReportRequest,ImageRequest,CheckRequest,CollectRequest,ToolRequest
ROW=dict(passage_id='p1',text='Annual follow up. BIRADS 2.',patient_id='train-a',source='train-a/report.pdf',split='train',rank=1,similarity=.8)
def state(**kw):return State(request_id='unit',**kw)
class Collection:
 def count(self):return 3
 def get(self,**kw):return {'ids':['p1'],'documents':[ROW['text']],'metadatas':[ROW]}
 def query(self,**kw):return {'ids':[['p1','p2','p3']],'documents':[['Annual follow up']*3],'metadatas':[[ROW,{**ROW,'patient_id':'query'},{**ROW,'patient_id':'test','split':'test'}]],'distances':[[.1,.2,.3]]}
class CoreTests(unittest.TestCase):
 def setUp(self):self.client=TestClient(api.app)
 def test_schema(self):
  for payload in [{'filters':{'split':'test'}},{'filters':{'expected_answer':'x'}},{'image_path':'C:/x'},{'tools':['shell']},{'retry_count':2}]:
   with self.subTest(payload=payload):self.assertEqual(self.client.post('/tools/report-search',json={'state':{'request_id':'x',**payload}}).status_code,422)
 def test_retired_planner(self):self.assertEqual(self.client.post('/agent/query').status_code,410)
 def test_train_filter_query_exclusion(self):
  with patch.object(tools,'_report_index',return_value=(None,Collection())),patch.object(tools,'embed_query',return_value=[0]):rows=tools.search_reports('report',5,'query')
  self.assertEqual([r['passage_id'] for r in rows],['p1']);self.assertEqual(rows[0]['source'],ROW['source'])
 def test_report_endpoint(self):
  with patch.object(api,'warm_encoder'),patch.object(tools,'search_reports',return_value=[ROW]):r=self.client.post('/tools/report-search',json={'state':state(query='report').model_dump()})
  self.assertEqual(r.status_code,200);self.assertEqual(r.json()['state']['reports'][0]['passage_id'],'p1')
 def test_invalid_image(self):
  with patch.object(api,'warm_encoder') as warm:r=self.client.post('/tools/image-search',json={'state':state().model_dump(),'image_base64':'ZmFrZQ=='})
  self.assertEqual(r.json()['state']['status'],'tool_error');warm.assert_not_called()
 def test_metadata_strips_annotations(self):
  row=dict(patient_id='train-a',split='train',modalities=[],image_ids=[],report_sources=[],has_report=False,has_structured_report=False,image_count=0,report_count=0,expected_answer='secret',birads_values=['2'])
  with patch.object(tools,'metadata_lookup',return_value={'status':'ok','results':[row]}):result=self.client.post('/tools/metadata',json={'state':state().model_dump()}).json()['state']['metadata'][0]
  self.assertNotIn('expected_answer',result);self.assertNotIn('birads_values',result)
 def checked(self,answer,**kw):
  s=state(intent='report_question',reports=[Report(**ROW)],generation_evidence=[Report(**ROW)],candidate_answer=answer,**kw)
  with patch.object(tools,'_report_index',return_value=(None,Collection())):return api.check_tool(CheckRequest(state=s,stage='answer'))
 def test_verbatim_accept(self):
  s=self.checked('Patient train-a: Annual follow up. [E1]');self.assertEqual(s.checker.decision,'accept');self.assertEqual(s.citations,['p1']);self.assertIn('[p1]',s.answer)
 def test_wrong_patient(self):self.assertEqual(self.checked('Patient other: Annual follow up. [E1]').checker.decision,'abstain')
 def test_query_patient(self):self.assertEqual(self.checked('Patient train-a: Annual follow up. [E1]',patient_id='train-a').checker.decision,'abstain')
 def test_bad_citation(self):self.assertEqual(self.checked('Patient train-a: Annual follow up. [E9]').checker.decision,'abstain')
 def test_extra_claim(self):self.assertIn('nonverbatim_claim',self.checked('Patient train-a: Annual follow up. You have cancer. [E1]').checker.problems)
 def test_forged_source(self):
  s=state(intent='report_question',reports=[Report(**{**ROW,'source':'forged'})])
  with patch.object(tools,'_report_index',return_value=(None,Collection())):result=api.check_tool(CheckRequest(state=s))
  self.assertIn('report_source_mismatch',result.checker.problems)
 def test_no_evidence(self):self.assertEqual(api.check_tool(CheckRequest(state=state(intent='report_question'))).checker.decision,'insufficient')
 def test_frozen_evidence(self):
  s=state(reports=[Report(**ROW)],candidate_answer='Patient train-a: Annual follow up. [E1]');self.assertEqual(api.check_tool(CheckRequest(state=s,stage='answer')).checker.decision,'abstain')
 def test_parallel_jobs(self):
  def report(req):time.sleep(.12);return state(reports=[Report(**ROW)],tools_called=['report_search'])
  def image(req):time.sleep(.12);return state(tools_called=['image_search_vit'])
  a=api.submit(ReportRequest(state=state()),'report',report);b=api.submit(ImageRequest(state=state(),image_base64='AA=='),'image',image)
  result=asyncio.run(api.collect(CollectRequest(state=state(),jobs=[a.job_id,b.job_id]))).state
  self.assertEqual(result.reports[0].passage_id,'p1');self.assertIn('image_search_vit',result.tools_called);self.assertGreater(float(result.trace[-1].split('=')[1]),0)
 def test_foreign_jobs(self):
  a=api.submit(ReportRequest(state=state()),'report',lambda req:req.state);b=api.submit(ImageRequest(state=state(),image_base64='AA=='),'image',lambda req:req.state)
  with self.assertRaises(api.HTTPException):asyncio.run(api.collect(CollectRequest(state=State(request_id='foreign'),jobs=[a.job_id,b.job_id])))
  asyncio.run(api.collect(CollectRequest(state=state(),jobs=[a.job_id,b.job_id])))
 def test_generate_empty(self):
  with patch.object(api.httpx,'AsyncClient') as client:result=asyncio.run(api.generate(ToolRequest(state=state())))
  client.assert_not_called();self.assertIsNone(result.state.answer);self.assertEqual(result.state.status,'tool_error')
 def test_generate_deterministic_quote_no_release(self):
  s=state(question='follow up',generation_evidence=[Report(**ROW)])
  with patch.object(api,'source_problems',return_value=[]),patch.object(api.httpx,'AsyncClient') as client:result=asyncio.run(api.generate(ToolRequest(state=s)))
  client.assert_not_called();self.assertIsNone(result.state.answer);self.assertEqual(result.state.candidate_answer,'Patient train-a: Annual follow up. [E1]\nPatient train-a: BIRADS 2. [E1]')
  self.assertEqual(result.state.status,'pending')
 def test_generate_without_explicit_facts_is_empty(self):
  row=Report(**{**ROW,'text':'No additional finding is documented.'})
  with patch.object(api,'source_problems',return_value=[]),patch.object(api.httpx,'AsyncClient') as client:result=asyncio.run(api.generate(ToolRequest(state=state(generation_evidence=[row]))))
  client.assert_not_called();self.assertEqual(result.state.candidate_answer,'')
if __name__=='__main__':unittest.main(verbosity=2)
