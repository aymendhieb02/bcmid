const s=$input.first().json.state;
if(s.retry_count!==0 || !s.tools.includes('report_search') || s.errors.length) throw Error('Retry limit or tool constraint violated');
s.retry_count=1;
s.query=(s.question+' OPINION explicit annual follow up close follow up BI-RADS').slice(0,2200);
s.reports=[];s.registry=[];s.generation_evidence=[];s.candidate_answer='';s.answer=null;s.citations=[];
s.checker={decision:'not_checked',problems:[],checked_passage_ids:[]};
s.trace.push('targeted_query_rewrite_retry_1_of_1');
return [{json:{state:s}}];
