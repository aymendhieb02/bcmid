const s=$input.first().json.state;
s.registry=[];
const seen=new Set();
for(const [kind,rows] of [['report',s.reports],['image',s.images]]) for(const row of rows) {
 const id=kind==='report'?row.passage_id:row.image_id;
 if(!id||!row.patient_id||row.split!=='train'||(s.patient_id&&row.patient_id===s.patient_id)||seen.has(kind+id)) {s.errors.push('Invalid evidence identity or patient/split leakage');continue;}
 seen.add(kind+id);
 s.registry.push({kind,id,patient_id:row.patient_id,source:kind==='report'?row.source:row.source_image_reference,split:row.split,modality:row.modality??null,rank:row.rank,similarity:row.similarity??null});
}
s.trace.push('assemble_evidence_registry');
return [{json:{state:s}}];
