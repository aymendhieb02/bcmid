# BCMID verification status

This note separates code checks, stable-path requests, answer release, and the unpublished prototype. It contains no report passages, image data, credentials, or patient identifiers.

## Stable workflow and API

| Capability | Status | Evidence and limit |
| --- | --- | --- |
| Stable workflow topology | **Runtime tested** | The local active workflow is `BCMID local tools — visible orchestration`, serving `POST /webhook/bcmid-agent` on the local n8n instance. The public JSON is a portable export and is not proof of live activation. |
| Report retrieval | **Runtime tested** | Synthetic stable-webhook checks returned report evidence and source references. This is functional routing evidence, not a retrieval benchmark. |
| Image retrieval | **Runtime tested** | Synthetic stable-webhook checks returned similar training-image results. This does not establish diagnostic performance. |
| Combined image and report retrieval | **Runtime tested** | Synthetic stable-webhook checks exercised both evidence collections through the stable workflow. Similar images and other patients’ reports remain separate from facts about the query patient. |
| Metadata lookup and invalid-input handling | **Runtime tested** | Local synthetic calls exercised matching/no-match and rejected-input behavior. |
| Stable checked quotation after deterministic extraction change | **Runtime tested** | A synthetic stable-webhook check after the extraction change returned an answer accepted by the checker with citations. The claim is limited to that request and route. |
| Historical model-generated checked-quotation run | **Failed safely / abstained** | The saved run review records successful workflow completion but no released answer or citations: the answer checker rejected nonverbatim/unsupported candidate claims, including after the one retry. A separate later verification record reports a `tool_error` with no answer or citations. These are model-generation failures, not retrieval-score results. |
| Source and answer checker | **Implemented; unit tested** | The API validates canonical source identity, training split, query-patient exclusion, attribution, exact quotation wording, and citations. A checker decision other than accept blocks answer release. |
| Clinical accuracy | **Not tested** | Synthetic requests and software tests do not measure clinical correctness or safety in clinical use. |

## Agent and memory prototype

| Capability | Status | Evidence and limit |
| --- | --- | --- |
| One Orchestrator with six specialist AI Agent Tools | **Structurally verified** | Confirmed in the separate local workflow export. The stable active workflow does not use this topology. |
| API tools connected to specialist agents | **Structurally verified** | The prototype has connected HTTP Request Tool nodes for the report, image, metadata, evidence-check, generation, and multimodal job/collect endpoints. End-to-end tool selection and successful final responses are **not verified**. |
| Orchestrator chat model connections | **Structurally verified** | The inspected export connects the configured local Ollama model to the Orchestrator and specialist agents. Model-backed end-to-end behavior is **not verified**. |
| Session-scoped memory connection | **Structurally verified** | The Simple Memory node connects directly to the Orchestrator memory input only. The normalized opaque session key is structurally present. |
| Same-session continuity, separate-session isolation, clear/reset, restart behavior | **Not runtime tested** | Do not claim memory isolation or persistence has passed. Simple Memory is in-process, not durable database storage, and is not part of the stable workflow. |
| Prototype publication or activation | **Not performed** | Keep the prototype unpublished until staged agent and memory checks pass. |

## Automated checks inspected

Existing local reports record passing mocked checks for the Streamlit/client tests, FastAPI/core contracts, and n8n workflow routing assertions. Those checks cover software behavior and schemas; they do not substitute for a live prototype test, retrieval benchmark, or clinical evaluation. Use [the testing guide](testing.md) to reproduce the appropriate stable-path checks.

## Evidence sources

- Stable export in this repository: [`projet/n8n/bcmid_workflow.n8n.json`](../projet/n8n/bcmid_workflow.n8n.json).
- Local stable run review and summaries: `projet/agentic_local/verification/` in the development workspace. Raw run records are intentionally not published because they may contain report text, image payloads, or identifiers.
- Separate memory verification notes and prototype export: local development workspace only. The prototype export is not included in this public repository.

The diagrams are architecture diagrams reconstructed from workflow exports and code. They are not screenshots of the n8n canvas.
