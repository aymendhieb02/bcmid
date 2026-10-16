const items=$input.all().map(x=>x.json);
if(items.length!==2 || new Set(items.map(x=>x.kind)).size!==2 || items.some(x=>!['report','image'].includes(x.kind)||!x.job_id||x.state.request_id!==items[0].state.request_id)) throw Error('Invalid paired retrieval jobs');
return [{json:{state:items.find(x=>x.kind==='report').state,jobs:items.map(x=>x.job_id)}}];
