const item = $input.first();
const body = item.json.body ?? item.json;
const state = {request_id: `bcmid-${Date.now()}-${Math.random().toString(36).slice(2)}`, question:'',query:'',patient_id:null,filters:{split:'train'},intent:'out_of_scope_or_insufficient',tools:[],needs_generation:false,retry_count:0,status:'pending',reports:[],images:[],metadata:[],registry:[],generation_evidence:[],candidate_answer:'',answer:null,citations:[],checker:{decision:'not_checked',problems:[],checked_passage_ids:[]},tools_called:[],trace:['normalize'],limitations:['Research similar-case retrieval; no diagnosis of the query patient. Patient-level image/report links are not verified for the exact examination. Similarity is not confidence.'],errors:[]};
let image_base64=''; let requested_intent=null; let retrieve_only=false;
try {
  if (!body || typeof body !== 'object' || Array.isArray(body)) throw Error('Request must be an object');
  const allowed=['question','patient_id','intent','filters','filters_json','retrieve_only','image_base64'];
  if(Object.keys(body).some(k=>!allowed.includes(k))) throw Error('Unknown request field');
  if(body.question!=null && typeof body.question!=='string') throw Error('question must be text');
  state.question=(body.question??'').trim(); state.query=state.question;
  if(state.question.length>2000) throw Error('question exceeds 2000 characters');
  if(body.patient_id!=null && typeof body.patient_id!=='string') throw Error('patient_id must be text');
  state.patient_id=(body.patient_id??'').trim()||null;
  if(state.patient_id && !/^[A-Za-z0-9_-]{1,128}$/.test(state.patient_id)) throw Error('Invalid patient_id');
  let f=body.filters ?? body.filters_json ?? {};
  if(typeof f==='string') f=JSON.parse(f);
  if(!f || typeof f!=='object' || Array.isArray(f)) throw Error('filters must be an object');
  const keys=['patient_id','image_id','modality','split','has_report','has_structured_report','birads'];
  if(Object.keys(f).some(k=>!keys.includes(k))) throw Error('Unknown filter');
  if(f.split!=null && f.split!=='train') throw Error('Serving tools only expose the train split');
  if(f.modality!=null && !['Mammogram','Ultrasound'].includes(f.modality)) throw Error('Invalid modality');
  for(const k of ['has_report','has_structured_report']) if(f[k]!=null && typeof f[k]!=='boolean') throw Error(`${k} must be boolean`);
  for(const k of ['patient_id','image_id']) if(f[k]!=null && (typeof f[k]!=='string'||!/^[A-Za-z0-9_-]{1,128}$/.test(f[k]))) throw Error(`Invalid ${k}`);
  if(f.birads!=null && (typeof f.birads!=='string'||!/^[0-6][a-cA-C]?$/.test(f.birads))) throw Error('Invalid BI-RADS filter');
  state.filters={...f,split:'train'};
  requested_intent=body.intent||null;
  if(requested_intent && typeof requested_intent!=='string') throw Error('intent must be text');
  if(body.retrieve_only!=null && ![true,false,'true','false'].includes(body.retrieve_only)) throw Error('Invalid retrieve_only');
  retrieve_only=body.retrieve_only===true||body.retrieve_only==='true';
  const binaries=Object.keys(item.binary??{});
  if(binaries.length>1) throw Error('Upload one image');
  if(binaries.length) {
    const buffer=await this.helpers.getBinaryDataBuffer(0,binaries[0]);
    if(buffer.length>20971520) throw Error('Image exceeds 20 MiB');
    image_base64=buffer.toString('base64');
  } else {
    image_base64=body.image_base64??'';
    if(typeof image_base64!=='string'||image_base64.length>27962028|| (image_base64 && !/^[A-Za-z0-9+/]*={0,2}$/.test(image_base64))) throw Error('Invalid image_base64');
  }
} catch(e) {state.status='invalid_request';state.errors=[e.message];image_base64='';}
return [{json:{state,image_base64,requested_intent,retrieve_only,has_image:!!image_base64}}];
