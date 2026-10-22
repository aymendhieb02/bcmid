# BCMID verification status

This page separates implementation and canvas evidence from live execution evidence. No local report text, image bytes, credentials, or unnecessary patient identifiers are published here.

## What this repository confirms

| Area | Evidence in this repository | Limit |
| --- | --- | --- |
| Streamlit route selection | `.env.example` and `app.py` configure Chat assistant and Explore evidence separately. | Configuration does not prove a webhook is registered or active. |
| n8n seven-agent canvas | The supplied screenshot visibly shows the Orchestrator, specialist roles, memory, API tools, and final answer gate. | The screenshot’s own note says the depicted candidate is inactive and runtime untested. It does not prove the live graph revision or any tool execution. |
| FastAPI checks | API code contains retrieval, evidence sufficiency, generation/extraction, and final answer-check endpoints. | Code structure alone does not prove the live service or returned decisions. |
| Streamlit source and metadata views | The UI renders report passages, similar-image previews, patient metadata, and available local PDF pages. | Local data files must exist; image/report ownership still depends on validated API records. |
| Safe answer handling | The client accepts an answer only with checker `accept`, nonempty citations, and citations contained in generation evidence. | Runtime behavior must be matched to a saved n8n execution for each claimed route. |
| Clinical accuracy | No clinical performance claim is made. | Not evaluated by UI or software tests. |

## Runtime status

The public repository does not contain a current saved execution trace proving that the configured Chat assistant route invoked each expected native Agent tool, passed evidence and citation checks, and returned the same result to Streamlit. The screenshot documents a canvas, not an execution. Treat agent-tool invocation, image exclusion, memory isolation, and successful final answer release as **requiring live verification** unless a current execution is reviewed in n8n.

Explore evidence uses the normal evidence webhook configured in `.env.example`. Chat assistant uses the seven-agent webhook configured there. Verify the workflow associated with each path in the local n8n UI before testing.

## Privacy and evidence handling

Keep local datasets, reports, uploaded images, model files, indexes, credentials, and raw execution exports out of GitHub. If n8n saves execution data, inspect its retention settings before submitting an image or report request. Use sanitized node/tool facts when writing test notes.

For repeatable steps, see [the test guide](testing.md). The workflow screenshot is at [`n8n-seven-agent-canvas.png`](n8n-seven-agent-canvas.png).
