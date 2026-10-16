const s=JSON.parse(JSON.stringify($input.first().json.state ?? $('Validate allowlisted plan').first().json.state));
s.status='tool_error';
s.errors.push('local_tool_transport_failed');
s.trace.push('local_tool_transport_failed');
s.answer=null;s.citations=[];
return [{json:{state:s}}];
