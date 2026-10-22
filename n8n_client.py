"""The Streamlit UI calls n8n only; requests match the active local workflow."""
from __future__ import annotations
import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
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

_PATIENT_ID = r'[A-Za-z0-9]+y\d{2}'
_PATIENT_ID_IN_QUESTION = re.compile(
 rf'\bpatient(?:[\s_]+(?:id|identifier))?\s*(?:is\s+|[:=#]\s*)?({_PATIENT_ID})\b',
 re.IGNORECASE,
)
_PATIENT_ID_IN_FILENAME = re.compile(rf'^({_PATIENT_ID})(?=_|$)', re.IGNORECASE)

def infer_chat_request_context(question:str,*,image_name:str|None=None,has_image:bool=False)->tuple[str,str|None]:
 """Infer a safe chat route and preserve an explicitly supplied patient ID as text.

 An image query must carry its query-patient ID so the API can exclude that patient
 from similar-case results. The ID may come from explicit question text or the
 conventional dataset filename prefix (for example, 0263y19_US_L_1.png).
 """
 text=(question or '').strip()
 matches=_PATIENT_ID_IN_QUESTION.findall(text)
 if len(matches)>1 and len(set(matches))>1:
  raise ValueError('Include only one patient ID per chat request.')
 question_id=matches[0] if matches else None
 filename_id=None
 if image_name:
  filename_id_match=_PATIENT_ID_IN_FILENAME.match(Path(image_name).name)
  if filename_id_match:
   filename_id=filename_id_match.group(1)
 if question_id and filename_id and question_id.casefold()!=filename_id.casefold():
  raise ValueError('The patient ID in the question does not match the uploaded image filename.')
 patient_id=question_id or filename_id

 normalized=re.sub(r'[^a-z0-9]+',' ',text.casefold()).strip()
 metadata_request=bool(re.search(
  r'\b(metadata|patient id|patient identifier|patient lookup|lookup patient|look up patient|patient record|catalog lookup)\b',
  normalized,
 ))
 if metadata_request:
  if not patient_id:
   bare_ids=re.findall(rf'\b({_PATIENT_ID})\b',text,re.IGNORECASE)
   unique_ids={value.casefold():value for value in bare_ids}
   if len(unique_ids)>1:raise ValueError('Include only one patient ID per metadata lookup.')
   if unique_ids:patient_id=next(iter(unique_ids.values()))
  return 'metadata_lookup',patient_id

 if has_image:
  if not patient_id:
   raise ValueError('Include the query patient ID in the question or image filename so the workflow can exclude that patient from similar-case results.')
  report_terms=bool(re.search(r'\b(report|findings?|follow up|birads|bi rads|recommendation|impression)\b',normalized))
  similarity_only=bool(re.search(r'\b(similar|matching) (?:training )?images?\b',normalized))
  if not text or (similarity_only and not report_terms):
   return 'image_search',patient_id
  return 'image_and_report_question',patient_id

 return 'report_question',patient_id

class N8nError(RuntimeError):pass
class N8nTimeout(N8nError):
 def __init__(self,request_id:str):
  self.request_id=request_id
  super().__init__(f'This request is still processing. Request ID: {request_id}')
@dataclass
class N8nReply:
 answer:str
 sources:list
 evidence:dict
 details:dict
 status:str

def make_payload(question:str='',*,patient_id:str|None=None,filters:dict|None=None,
                 image:bytes|None=None,intent:str|None=None,retrieve_only:bool=True,
                 session_id:str|None=None,request_id:str|None=None)->dict:
 if len(question.strip())>2000:raise N8nError('Keep the question within 2,000 characters.')
 payload={'question':question.strip(),'retrieve_only':retrieve_only}
 if patient_id and patient_id.strip():payload['patient_id']=patient_id.strip()
 if filters is not None:payload['filters']=filters
 if intent:payload['intent']=intent
 if session_id:
  if not 16<=len(session_id)<=128 or not all(c.isalnum() or c in '-_' for c in session_id):
   raise N8nError('The conversation session identifier is invalid.')
  payload['session_id']=session_id
 if request_id:
  if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',request_id):
   raise N8nError('The request identifier is invalid.')
  payload['request_id']=request_id
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
 request_id=body.pop('request_id',None)
 headers={}
 if session_id:headers['X-BCMID-Session-ID']=session_id
 if request_id:headers['X-BCMID-Request-ID']=request_id
 if not headers:headers=None
 try:response=(post or requests.post)(webhook_url,json=body,headers=headers,timeout=timeout)
 except requests.Timeout as exc:
  if request_id:raise N8nTimeout(request_id) from exc
  raise N8nError('The workflow timed out. Check its execution before submitting again.') from exc
 except requests.RequestException as exc:raise N8nError('Cannot reach n8n. Start the demo and confirm the published webhook URL.') from exc
 if not 200<=response.status_code<300:raise N8nError(f'n8n returned HTTP {response.status_code}. Publish the workflow and use its production webhook.')
 try:data=response.json()
 except ValueError as exc:raise N8nError('n8n returned an empty or invalid JSON response. Inspect the workflow execution.') from exc
 return parse_response(data)


def _n8n_database_path()->Path:
 configured=os.getenv('N8N_DB_PATH')
 if configured:return Path(configured).expanduser()
 return Path.home()/'.n8n'/'database.sqlite'


def _flatted_package_path()->Path:
 configured=os.getenv('N8N_FLATTED_PATH')
 if configured:return Path(configured)
 appdata=Path(os.getenv('APPDATA',Path.home()/'AppData'/'Roaming'))
 return appdata/'npm'/'node_modules'/'n8n'/'node_modules'/'flatted'


def decode_saved_execution(data:str)->dict:
 """Decode only the saved Respond to Webhook payload from an n8n Flatted record."""
 node=shutil.which('node')
 package=_flatted_package_path()
 if not node or not package.exists():raise N8nError('Local n8n result recovery is unavailable (Node/flatted not found).')
 script=(
  "const fs=require('fs');const {parse}=require(process.argv[1]);"
  "const x=parse(fs.readFileSync(0,'utf8'));"
  "const r=x.resultData?.runData?.['Respond to Webhook']?.[0]?.data?.main?.[0]?.[0]?.json;"
  "if(r)process.stdout.write(JSON.stringify(r));"
 )
 try:
  p=subprocess.run([node,'-e',script,str(package)],input=data,text=True,capture_output=True,timeout=10,check=True)
  return json.loads(p.stdout) if p.stdout else {}
 except (subprocess.SubprocessError,ValueError):return {}


def lookup_n8n_request(request_id:str,*,database_path:Path|str|None=None,
                       decoder:Callable[[str],dict]|None=None)->dict:
 """Read n8n's local execution history without writing to its database."""
 if not re.fullmatch(r'[A-Za-z0-9_-]{16,128}',request_id):
  raise N8nError('The request identifier is invalid.')
 path=Path(database_path) if database_path else _n8n_database_path()
 if not path.is_file():return {'status':'unavailable','request_id':request_id}
 try:
  uri=path.resolve().as_uri()+'?mode=ro'
  with sqlite3.connect(uri,uri=True,timeout=2) as db:
   row=db.execute(
    "SELECT e.status,e.finished,d.data FROM execution_entity e "
    "LEFT JOIN execution_data d ON d.executionId=e.id "
    "WHERE d.data LIKE ? ORDER BY e.id DESC LIMIT 1",('%'+request_id+'%',)
   ).fetchone()
 except sqlite3.Error:
  return {'status':'unavailable','request_id':request_id}
 if not row:return {'status':'pending','request_id':request_id}
 status,finished,data=row
 if not finished:return {'status':'processing','request_id':request_id}
 response=(decoder or decode_saved_execution)(data or '')
 if not response:return {'status':'failed','request_id':request_id}
 return {'status':'completed','request_id':request_id,'result':response}
