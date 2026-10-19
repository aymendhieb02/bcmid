"""Atomic tools only. n8n owns intent, branching, retries and response release."""
from __future__ import annotations
import asyncio, base64, binascii, hashlib, io, json, re, tempfile, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse
import httpx
from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from PIL import Image, UnidentifiedImageError
import tools as backend
from config import MAX_UPLOAD_BYTES, OLLAMA_BASE_URL, OLLAMA_MODEL, IMAGE_METADATA
from evidence import check_generated_answer, explicit_facts
from schemas import (State, Report, ImageHit, MetadataRow, ToolRequest, ReportRequest,
                     ImageRequest, CheckRequest, ToolResponse, JobResponse, CollectRequest, Checker)

app = FastAPI(title='BCMID local tools — orchestrated by n8n', version='0.2.0')
pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='bcmid-tool')
jobs: dict = {}
job_lock = threading.Lock()
model_lock = threading.Lock()

# Avoid concurrent first-import races in torch/transformers while retaining
# concurrent tool execution once the independent encoders have loaded.
def warm_encoder(kind):
    with model_lock:
        if kind == 'report': backend._e5_model()
        else: backend._image_runtime()


def record(s, name):
    s.tools_called.append(name)
    s.trace.append(name)
    return s


def fail(s, name, exc):
    s.status = 'tool_error'
    s.errors.append(f'{name}: {type(exc).__name__}')
    return s


def report_tool(req: ReportRequest):
    s = req.state.model_copy(deep=True)
    record(s, 'report_search')
    try:
        if not s.query.strip(): raise ValueError('Empty search query')
        warm_encoder('report')
        hits = backend.search_reports(s.query, req.top_k, s.patient_id)
        fields = set(Report.model_fields)
        s.reports = [Report(**{k:v for k,v in h.items() if k in fields}) for h in hits]
    except Exception as exc: fail(s, 'report_search', exc)
    return s


def image_tool(req: ImageRequest):
    s = req.state.model_copy(deep=True)
    record(s, 'image_search_vit')
    try:
        raw = base64.b64decode(req.image_base64, validate=True)
        if not raw or len(raw) > MAX_UPLOAD_BYTES: raise ValueError('Image size exceeds limit')
        with Image.open(io.BytesIO(raw)) as im:
            if im.width * im.height > 25_000_000: raise ValueError('Image dimensions exceed limit')
            if im.mode not in {'L','LA','RGB','RGBA','P','1'}: raise ValueError('Unsupported image bit depth')
            im.verify()
        warm_encoder('image')
        with tempfile.TemporaryDirectory(prefix='bcmid-tool-') as directory:
            path = Path(directory) / 'upload.img'
            path.write_bytes(raw)
            hits = backend.search_images(path, req.top_k, s.filters.modality, s.patient_id)
        fields = set(ImageHit.model_fields)
        s.images = [ImageHit(**{k:v for k,v in h.items() if k in fields}) for h in hits]
        s.limitations.append('Image search uses saved ViT features, not the Kaggle CLIP index; CLIP metrics do not validate this backend.')
    except Exception as exc: fail(s, 'image_search', exc)
    return s


def source_problems(s: State, reports=None):
    problems = []
    reports = s.reports if reports is None else reports
    if reports:
        _, collection = backend._report_index()
        data = collection.get(ids=list({r.passage_id for r in reports}), include=['documents','metadatas'])
        actual = {i:(t,m) for i,t,m in zip(data['ids'],data['documents'],data['metadatas'])}
        seen = set()
        for row in reports:
            if row.passage_id in seen: problems.append('duplicate_passage_id')
            seen.add(row.passage_id)
            canonical = actual.get(row.passage_id)
            if not canonical or canonical[0] != row.text or any(
                str(canonical[1].get(k)) != str(getattr(row,k)) for k in ['patient_id','source','split']
            ): problems.append('report_source_mismatch')
            if s.patient_id and row.patient_id == s.patient_id: problems.append('query_patient_leakage')
    if s.images:
        rows = json.loads(IMAGE_METADATA.read_text(encoding='utf-8'))
        image_map = {}
        for row in rows:
            ref = '/'.join(str(row['path']).replace('\\','/').split('/')[-3:])
            image_map['img_'+hashlib.sha256(ref.encode()).hexdigest()[:20]] = (row,ref)
        for hit in s.images:
            canonical = image_map.get(hit.image_id)
            if not canonical or canonical[0]['split'] != 'train' or canonical[0]['patient_id'] != hit.patient_id or canonical[0]['modalite'] != hit.modality or canonical[1] != hit.source_image_reference:
                problems.append('image_source_mismatch')
            if s.patient_id and hit.patient_id == s.patient_id: problems.append('query_patient_leakage')
    return sorted(set(problems))


def check_tool(req: CheckRequest):
    s = req.state.model_copy(deep=True)
    record(s, 'evidence_check' if req.stage == 'evidence' else 'answer_check')
    try:
        selected = s.generation_evidence if req.stage == 'answer' else s.reports
        problems = source_problems(s, selected)
        if s.errors: problems.append('tool_failure')
        if req.stage == 'evidence':
            if s.intent in {'report_question','image_and_report_question'} and not s.reports: problems.append('no_report_evidence')
            if s.intent in {'image_search','image_and_report_question'} and not s.images: problems.append('no_image_evidence')
            if s.needs_generation and not any(explicit_facts(r.text) for r in s.reports): problems.append('no_explicit_followup_or_birads')
            decision = 'insufficient' if problems else 'sufficient'
        else:
            if not selected: problems.append('no_generation_evidence')
            base = check_generated_answer(s.candidate_answer, [r.model_dump() for r in selected], s.patient_id)
            if base['decision'] != 'accept': problems.extend(p.get('status','unsupported_claim') for p in base['problems'])
            # The narrow notebook-style fact checks are retained. Exact quotations
            # are required in addition so unrelated unsupported claims cannot hide
            # beside a supported BI-RADS/follow-up phrase.
            lines = [line.strip() for line in s.candidate_answer.splitlines() if line.strip()]
            if not lines: problems.append('empty_answer')
            for line in lines:
                m = re.fullmatch(r'Patient ([A-Za-z0-9_-]+): (.+) \[(E\d+)\]', line)
                if not m: problems.append('unvalidated_answer_format'); continue
                pid, quote, alias = m.groups(); index = int(alias[1:])-1
                if index < 0 or index >= len(selected): problems.append('invalid_citation'); continue
                row = selected[index]
                normal = lambda value: ' '.join(value.split())
                if pid != row.patient_id: problems.append('patient_attribution_mismatch')
                if not quote.strip() or normal(quote) not in normal(row.text): problems.append('nonverbatim_claim')
            decision = 'abstain' if problems else 'accept'
            if decision == 'accept':
                s.answer = s.candidate_answer
                s.citations = []
                for i,row in enumerate(selected,1):
                    if f'[E{i}]' in s.answer:
                        s.answer = s.answer.replace(f'[E{i}]',f'[{row.passage_id}]')
                        s.citations.append(row.passage_id)
            else:
                s.answer = None; s.citations = []
        s.checker = Checker(decision=decision, problems=sorted(set(problems)), checked_passage_ids=[r.passage_id for r in selected])
    except Exception as exc:
        fail(s,'evidence_check',exc)
        s.checker = Checker(decision='abstain', problems=['checker_unavailable'])
    return s


@app.get('/health')
async def health():
    state = backend.local_model_status()
    try:
        async with httpx.AsyncClient(timeout=3) as client: r = await client.get(OLLAMA_BASE_URL+'/api/tags')
        state['ollama_model_available'] = OLLAMA_MODEL in [x['name'] for x in r.json()['models']]
    except Exception: state['ollama_model_available'] = False
    return {'status':'ok','orchestrator':'n8n','components':state}

@app.post('/agent/query')
def retired_planner():
    raise HTTPException(410, 'Orchestration moved to the n8n /webhook/bcmid-agent flow; call individual /tools endpoints here.')

@app.post('/tools/report-search',response_model=ToolResponse)
def reports(req: ReportRequest): return ToolResponse(state=report_tool(req))

@app.post('/tools/image-search',response_model=ToolResponse)
def images(req: ImageRequest): return ToolResponse(state=image_tool(req))

@app.post('/tools/image-upload',response_model=ToolResponse)
async def image_upload(state_json: str=Form(...), image: UploadFile=File(...)):
    try:
        state=State.model_validate_json(state_json)
        raw=await image.read(MAX_UPLOAD_BYTES+1)
        if len(raw)>MAX_UPLOAD_BYTES: raise HTTPException(413,'Upload too large')
        req=ImageRequest(state=state,image_base64=base64.b64encode(raw).decode())
    except HTTPException: raise
    except Exception as exc: raise HTTPException(422,'Invalid state or image input') from exc
    finally: await image.close()
    return ToolResponse(state=await asyncio.to_thread(image_tool,req))

@app.post('/tools/metadata',response_model=ToolResponse)
def metadata(req: ToolRequest):
    s=req.state.model_copy(deep=True);record(s,'metadata_lookup')
    try:
        result=backend.metadata_lookup(s.filters.model_dump(exclude_none=True))
        keys=set(MetadataRow.model_fields)
        s.metadata=[MetadataRow(**{k:v for k,v in row.items() if k in keys}) for row in result['results']]
        s.status=result['status']
    except Exception as exc: fail(s,'metadata_lookup',exc)
    return ToolResponse(state=s)

@app.post('/tools/evidence-check',response_model=ToolResponse)
def check(req: CheckRequest): return ToolResponse(state=check_tool(req))

@app.post('/tools/generate',response_model=ToolResponse)
async def generate(req: ToolRequest):
    s=req.state.model_copy(deep=True);record(s,'generate_ollama')
    s.answer=None;s.candidate_answer='';s.citations=[]
    try:
        if not s.generation_evidence or source_problems(s,s.generation_evidence): raise ValueError('Unverified source evidence')
        # This endpoint only extracts verbatim BI-RADS/follow-up evidence. Do
        # that exactly from verified source text instead of asking an LLM to
        # repeat facts that are already present in the source.
        lines=[]
        for index, report in enumerate(s.generation_evidence,1):
            sentences=[part.strip() for part in re.split(r'(?<=[.!?])\s+|\r?\n+',report.text) if part.strip()]
            if not sentences and report.text.strip(): sentences=[report.text.strip()]
            for sentence in sentences:
                if explicit_facts(sentence):
                    quote=' '.join(sentence.split())
                    lines.append(f'Patient {report.patient_id}: {quote} [E{index}]')
                    if len(lines)>=5: break
            if len(lines)>=5: break
        s.candidate_answer='\n'.join(lines)
    except Exception as exc: fail(s,'generate_ollama',exc)
    return ToolResponse(state=s)


def submit(req,kind,fn):
    with job_lock:
        now=time.monotonic()
        for key in list(jobs):
            if now-jobs[key]['created']>600 and jobs[key]['future'].done(): del jobs[key]
        if len(jobs)>=16: raise HTTPException(429,'Local tool job capacity reached')
        peers=[j for j in jobs.values() if j['request_id']==req.state.request_id]
        if any(j['kind']==kind for j in peers): raise HTTPException(409,'Duplicate job kind for request')
        start_gate=peers[0]['start_gate'] if peers else threading.Event()
        job_id=uuid.uuid4().hex
        timing={}
        def run():
            # Atomic workers wait for both dispatch receipts. No planning or retry
            # occurs here; n8n explicitly chooses and dispatches both tools.
            if not start_gate.wait(timeout=15):
                timing['start']=timing['end']=time.monotonic()
                return fail(req.state.model_copy(deep=True),'paired_dispatch',TimeoutError())
            timing['start']=time.monotonic()
            try: return fn(req)
            finally: timing['end']=time.monotonic()
        jobs[job_id]={'future':pool.submit(run),'created':now,'request_id':req.state.request_id,'kind':kind,'timing':timing,'start_gate':start_gate}
        if peers: start_gate.set()
    return JobResponse(state=req.state,job_id=job_id,kind=kind)

@app.post('/tools/report-jobs',response_model=JobResponse)
def report_job(req:ReportRequest): return submit(req,'report',report_tool)

@app.post('/tools/image-jobs',response_model=JobResponse)
def image_job(req:ImageRequest): return submit(req,'image',image_tool)

@app.post('/tools/jobs/collect',response_model=ToolResponse)
async def collect(req:CollectRequest):
    with job_lock:
        selected=[jobs.get(j) for j in req.jobs]
    if len(set(req.jobs))!=2 or any(j is None or j['request_id']!=req.state.request_id for j in selected) or {j['kind'] for j in selected}!={'report','image'}:
        raise HTTPException(422,'Jobs must be one report and one image job belonging to this request')
    results=await asyncio.gather(*(asyncio.wrap_future(j['future']) for j in selected))
    s=req.state.model_copy(deep=True)
    for job,result in zip(selected,results):
        if job['kind']=='report': s.reports=result.reports
        else: s.images=result.images
        s.tools_called += result.tools_called[len(req.state.tools_called):]
        s.errors += result.errors
        s.limitations += result.limitations
    timings=[j['timing'] for j in selected]
    overlap=max(0,min(t['end'] for t in timings)-max(t['start'] for t in timings))
    s.trace.append(f'parallel_tool_overlap_seconds={overlap:.3f}')
    with job_lock:
        for key in req.jobs: jobs.pop(key,None)
    return ToolResponse(state=s)
