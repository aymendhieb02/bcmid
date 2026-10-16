const x=$input.first().json,s=x.state;
const allowed={report_question:['report_search'],image_search:['image_search'],image_and_report_question:['report_search','image_search'],metadata_lookup:['metadata_lookup'],out_of_scope_or_insufficient:[]};
try {
 if(!(s.intent in allowed)||JSON.stringify(s.tools)!==JSON.stringify(allowed[s.intent])) throw Error('Unknown intent or tool plan');
 if(!Number.isInteger(s.retry_count)||s.retry_count<0||s.retry_count>1) throw Error('Invalid retry count');
 if(s.tools.includes('image_search')&&!x.has_image) throw Error('Image intent requires an upload');
 if(s.tools.includes('report_search')&&!s.question) throw Error('Report intent requires a question');
 if(s.intent!=='metadata_lookup' && Object.keys(s.filters).some(k=>!['split','modality'].includes(k))) throw Error('Structured metadata filters require metadata_lookup');
 if(s.intent==='report_question' && s.filters.modality) throw Error('Modality filtering applies to images or metadata');
} catch(e) {s.status='invalid_request';s.errors.push(e.message);s.intent='out_of_scope_or_insufficient';s.tools=[];s.needs_generation=false;}
s.trace.push('allowlist_plan_validation');
return [{json:x}];
