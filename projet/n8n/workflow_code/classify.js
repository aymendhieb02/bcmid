const x=$input.first().json, s=x.state;
const q=s.question.toLowerCase();
const diagnosis=/\b(diagnos\w*|do i have|do they have|does (this|the) (image|patient).*cancer|is (this|it).*cancer|is my.*malignant|am i.*cancer|assess.*bi.?rads|assign.*bi.?rads)\b/i.test(q);
if(s.status==='invalid_request'||diagnosis) {s.intent='out_of_scope_or_insufficient';if(diagnosis)s.limitations.push('Diagnostic requests and BI-RADS assignment are outside this retrieval demo.');}
else if(x.requested_intent) s.intent=x.requested_intent;
else if(Object.keys(s.filters).some(k=>k!=='split' && (k!=='modality'||!x.has_image)) || /\b(metadata|patient id|patient identifier|lookup patient|find patient)\b/.test(q)) s.intent='metadata_lookup';
else if(x.has_image && (!q || /^(find |show |search |retrieve )?(similar|matching) (images|cases)/.test(q))) s.intent='image_search';
else if(x.has_image && /report|follow.?up|birads|bi-rads|finding|opinion/.test(q)) s.intent='image_and_report_question';
else if(!x.has_image && /report|follow.?up|birads|bi-rads|finding|opinion/.test(q)) s.intent='report_question';
else s.intent='out_of_scope_or_insufficient';
s.tools=({report_question:['report_search'],image_search:['image_search'],image_and_report_question:['report_search','image_search'],metadata_lookup:['metadata_lookup'],out_of_scope_or_insufficient:[]})[s.intent]??[];
s.needs_generation=!x.retrieve_only && ['report_question','image_and_report_question'].includes(s.intent) && /follow.?up|bi.?rads/i.test(q);
if(s.intent==='metadata_lookup' && !s.filters.patient_id && s.patient_id) s.filters.patient_id=s.patient_id;
s.trace.push('deterministic_classification');
return [{json:x}];
