const s=$input.first().json.state;
s.generation_evidence=s.reports.slice(0,5);
s.candidate_answer='';s.answer=null;s.citations=[];
s.trace.push('freeze_exact_generation_evidence');
return [{json:{state:s}}];
