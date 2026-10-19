"""The Streamlit UI calls n8n only; requests match the active local workflow."""
from __future__ import annotations
import base64
from dataclasses import dataclass
from typing import Any,Callable
from urllib.parse import urlparse
import requests

DEFAULT_WEBHOOK='http://127.0.0.1:5678/webhook/bcmid-agent'
STATUS_TEXT={
 'retrieved':'Retrieved evidence is ready. No generated answer was requested.',
 'answered':'The answer passed the source and citation checks.',
 'abstained':'The evidence checks did not support releasing an answer. You can inspect the retrieved sources below.',
 'out_of_scope':'This workspace retrieves similar cases. It cannot diagnose the uploaded patient or assign a new BI-RADS category.',
 'not_found':'No training-set metadata matched these filters.',
 'ok':'Matching training-set metadata is ready.',
 'invalid_request':'The workflow rejected this request. Review the fields and filters.',
 'tool_error':'A local tool could not complete the request. Check the services and run details.',
}
class N8nError(RuntimeError):pass
@dataclass
class N8nReply:
 answer:str
 sources:list
 evidence:dict
 details:dict
 status:str

def make_payload(question:str='',*,patient_id:str|None=None,filters:dict|None=None,
                 image:bytes|None=None,intent:str|None=None,retrieve_only:bool=True,
                 session_id:str|None=None)->dict:
 if len(question.strip())>2000:raise N8nError('Keep the question within 2,000 characters.')
 payload={'question':question.strip(),'retrieve_only':retrieve_only}
 if patient_id and patient_id.strip():payload['patient_id']=patient_id.strip()
 if filters is not None:payload['filters']=filters
 if intent:payload['intent']=intent
 if session_id:
  if not 16<=len(session_id)<=128 or not all(c.isalnum() or c in '-_' for c in session_id):
   raise N8nError('The conversation session identifier is invalid.')
  payload['session_id']=session_id
 if image is not None:
  if not image or len(image)>20*1024*1024:raise N8nError('Choose a nonempty image smaller than 20 MiB.')
  payload['image_base64']=base64.b64encode(image).decode('ascii')
 return payload

def parse_response(data:Any)->N8nReply:
 if not isinstance(data,dict) or data.get('status') not in STATUS_TEXT:raise N8nError('The webhook returned an unsupported response. Check that the BCMID local workflow is published.')
 for key in ('sources','report_passages','similar_images','metadata','citations','tools_called','limitations','errors','trace'):
  if not isinstance(data.get(key),list):raise N8nError(f'The webhook response is missing the {key} list.')
 if not isinstance(data.get('checker'),dict):raise N8nError('The webhook response is missing its evidence check.')
 status=data['status'];answer=STATUS_TEXT[status]
 if status=='answered':
  if data['checker'].get('decision')!='accept' or not isinstance(data.get('answer'),str) or not data['answer'].strip() or not data['citations']:
   raise N8nError('The workflow marked an answer accepted without checked text and citations.')
  if not set(data['citations'])<=set(data.get('generation_passage_ids',[])):raise N8nError('Answer citations do not match the generation evidence.')
  answer=data['answer']
 # Failed/retrieval responses never display a stray candidate or unaccepted answer.
 safe=dict(data)
 if status!='answered':safe['answer']=None;safe['citations']=[]
 safe.pop('candidate_answer',None)
 return N8nReply(answer,safe['sources'],safe['checker'],safe,status)

def ask_n8n(webhook_url:str,payload:dict,timeout:int=180,post:Callable|None=None)->N8nReply:
 url=urlparse(webhook_url.strip())
 if url.scheme not in {'http','https'} or url.hostname not in {'localhost','127.0.0.1','::1'}:
  raise N8nError('Use a local n8n webhook URL (localhost or 127.0.0.1).')
 body=dict(payload)
 session_id=body.pop('session_id',None)
 headers={'X-BCMID-Session-ID':session_id} if session_id else None
 try:response=(post or requests.post)(webhook_url,json=body,headers=headers,timeout=timeout)
 except requests.Timeout as exc:raise N8nError('The workflow timed out. Check its execution before submitting again.') from exc
 except requests.RequestException as exc:raise N8nError('Cannot reach n8n. Start the demo and confirm the published webhook URL.') from exc
 if not 200<=response.status_code<300:raise N8nError(f'n8n returned HTTP {response.status_code}. Publish the workflow and use its production webhook.')
 try:data=response.json()
 except ValueError as exc:raise N8nError('n8n returned an empty or invalid JSON response. Inspect the workflow execution.') from exc
 return parse_response(data)
