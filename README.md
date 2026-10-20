# BCMID · Local Evidence Assistant

### A research interface for breast imaging records, with sources in view

<p align="center"><img src="docs/architecture.svg" alt="Architecture diagram showing the stable BCMID route and the separate unpublished agent and memory prototype" width="100%"></p>

<p align="center"><b>Search reports · Explore similar training images · Verify every answer</b></p>

BCMID combines a Streamlit interface, n8n request orchestration, FastAPI feature tools, E5 and Chroma report retrieval, saved ViT image features, a metadata catalog, and optional local Ollama support. n8n owns routing and response release. FastAPI exposes atomic capabilities; it does not contain a second planner.

> **Research demo only.** Similar cases are not facts about the person whose image or question was submitted. This project does not diagnose, assign BI-RADS, or provide clinical recommendations.

## Two workflow paths

### Stable demo · active local route

The Streamlit app posts to the published n8n webhook at `POST /webhook/bcmid-agent`. The stable workflow uses deterministic Code nodes to normalize requests, classify intent, validate an allowlisted plan, route only the selected retrieval lane, check evidence, and form the response. These are ordinary workflow nodes; the stable route is **not** an AI Agent with six specialist agents.

The portable export is [`projet/n8n/bcmid_workflow.n8n.json`](projet/n8n/bcmid_workflow.n8n.json). Its export status is not the live instance’s activation status. On the existing local n8n profile, use the workflow already published as `BCMID local tools — visible orchestration`; do not reimport it for routine use.

### Agent and memory prototype · unpublished

A separate local export was structurally inspected. It contains one n8n Orchestrator AI Agent, six specialist AI Agent Tool nodes, connected HTTP Request Tool nodes for FastAPI, a shared local Ollama chat model, and a Simple Memory node connected only to the Orchestrator. It is **not** the stable webhook path and has not passed end-to-end or memory isolation tests. Keep it unpublished until those tests pass.

The prototype export is not included in this public repository. The diagram below is a documentation diagram reconstructed from the inspected workflow export, not a screenshot of the n8n canvas.

See [the architecture diagram](docs/architecture.svg), [answer flow](docs/answer-flow.svg), [test guide](docs/testing.md), and [verification status](docs/verification-status.md).

## Responsibilities and boundaries

| Component | Responsibility | Does not do |
| --- | --- | --- |
| Streamlit | Collects a question, optional image, filters, and opaque conversation session key; displays evidence, citations, and status | Decide retrieval policy or treat similar cases as facts about the query patient |
| Stable n8n workflow | Owns request normalization, intent classification, allowlisted routing, evidence sequence, bounded retry decision, and final response | Delegate to specialist AI Agents |
| Prototype n8n Orchestrator | In the unpublished design, selects a relevant specialist, orders tool calls, and decides whether evidence is sufficient | Replace API validation or evidence checks |
| Specialist agents | In the prototype, translate an assigned task into calls to their connected API tool and return tool state | Act as independent orchestrators or bypass the evidence gate |
| FastAPI | Exposes atomic report, image, metadata, evidence-check, extraction, and paired-job operations | Select the user intent, plan tools, or release a final answer on its own |
| Local assets | Provide the saved report collection, image vectors and metadata catalog | Provide clinical validation or diagnostic confidence |

## Prototype agents and connected API tools

The table below describes the **unpublished prototype’s exported structure**. It is a plain-language guide to each role, not a claim that the full agent route has passed live testing. The Orchestrator is the only planner; the six specialists call their connected FastAPI tools and return state or job receipts.

| Agent | Simple role (FR) | Runs when… | Uses | Produces |
| --- | --- | --- | --- | --- |
| **Orchestrator AI Agent** | **Le chef d’orchestre** — chooses the route | A request arrives | Normalized request, local Ollama chat model, six specialist tools | Selects the needed specialist(s), orders checks, and returns a final state or safe abstention |
| **Report Retrieval Agent** | **Le documentaliste** — finds report passages | A report question needs evidence, including the report half of a combined request | `POST /tools/report-search`; E5 embeddings and the Chroma report index | Up to five ranked training-report passages with source metadata |
| **Image Retrieval Agent** | **Le chercheur d’images** — finds similar examples | A reference image is supplied for image-only search | `POST /tools/image-search`; saved ViT image vectors and optional modality filter | Similar training-image hits with source metadata and similarity scores; no image interpretation |
| **Metadata Retrieval Agent** | **La fiche catalogue** — looks up structured fields | Validated catalog filters are requested | `POST /tools/metadata`; the local metadata JSON catalog | Matching metadata rows, counts, and provenance fields, or a no-match status |
| **Evidence Checker Agent** | **Le surligneur / contrôleur** — checks support | After retrieval and before a checked answer can be released | `POST /tools/evidence-check`; retrieved state, canonical sources, attribution, and citations | Evidence sufficiency or answer decision with problems; failed checks mean abstention |
| **Response Generator Agent** | **Le préparateur de citations** — extracts supported wording | Explicit follow-up or BI-RADS wording is requested and evidence is sufficient | `POST /tools/generate`; frozen, verified report passages | A verbatim extractive candidate with citation aliases for the checker to validate |
| **Multimodal Retrieval Agent** | **Le chercheur combiné** — pairs image and report search | An image and a report question are submitted together | `POST /tools/report-jobs`, `POST /tools/image-jobs`, then `POST /tools/jobs/collect` | Combined report and image evidence from the training split |

**Implementation details:** image search uses saved ViT features, not the Kaggle CLIP/Chroma experiment. Metadata comes from the local JSON catalog, not `df_alignement_v2`. The FastAPI quotation endpoint performs deterministic extraction; it does not ask Qwen to write the quoted answer. The answer checker still decides whether any candidate may be released.

These API nodes are connected as **AI-callable HTTP Request Tool nodes** in the prototype export. They are not merely ordinary HTTP nodes whose names contain “tool”. In the stable workflow, API calls are ordinary HTTP Request nodes following deterministic routing.

## Request-to-route map

| User input | Stable route | Prototype intent / specialist route | Interface result |
| --- | --- | --- | --- |
| Report question | Report retrieval → evidence registry and sufficiency check; optional narrow extraction only when requested | `report_question` → Report Retrieval; Evidence Checker; optional Response Generator followed by answer check | Ranked cited passages; a checked quotation only if accepted, otherwise abstention |
| Image-only search | Image retrieval | `image_search` → Image Retrieval | Similar training images with source metadata; no report-based answer |
| Image plus report question | Report and image retrieval lanes; distinct evidence collections | `image_and_report_question` → Multimodal Retrieval, which dispatches report and image jobs and collects both | Separate report passages and similar-image results, each with source references |
| Metadata filter | Metadata lookup only | `metadata_lookup` → Metadata Retrieval | Matching catalog rows or an explicit no-match result |
| Unsupported or out-of-scope request | Reject or return a safe out-of-scope response without unsupported clinical claims | `out_of_scope_or_insufficient` → safe response; no retrieval agent should be called | Clear scope message or abstention |

The Orchestrator should call only the specialist(s) relevant to the selected intent. Retrieval is constrained to the training split; when the query patient is known, its own records must be excluded from similar-case evidence. Similar-image neighbors are examples from other cases, not evidence about the uploaded patient.

## Evidence, extraction, retry, and abstention

<p align="center"><img src="docs/answer-flow.svg" alt="Stable and prototype evidence-gated answer flow" width="100%"></p>

The stable route assembles a source registry and checks evidence before answer extraction. The current `/tools/generate` implementation extracts explicit follow-up or BI-RADS sentences from verified passages; it does not ask Ollama to paraphrase those facts. The candidate must pass the answer checker, including source identity, patient attribution, exact wording, and citation checks. The interface only accepts an answer with checker decision `accept` and non-empty citations. Failed checks withhold candidate text and citations.

The stable workflow permits one targeted report-search retry only when its retry conditions allow it. If the retry does not yield an accepted answer, the route abstains. A successful retrieval response is not the same as a checked answer. Neither unit tests nor synthetic webhook checks demonstrate clinical accuracy.

## Conversation memory in the prototype

The memory export uses n8n **Simple Memory** (`memoryBufferWindow`) with a three-interaction context window. Its memory output connects directly to the Orchestrator’s memory input; specialist agents do not share that memory connection. The prototype normalizer accepts an opaque random session ID from the `X-BCMID-Session-ID` header or `session_id` request field, validates its character set and length, and maps it to the node’s Session Key. The ID must never be derived from `patient_id`.

Memory is conversational context for interpreting follow-up wording. It is not report evidence. Each question still needs fresh retrieval, evidence checks, and answer citation validation. Simple Memory is in-process memory, not durable database storage; it does not survive an n8n restart. The stable workflow does not consume this session key and has no memory node. Same-session continuity, cross-session isolation, clear/reset behavior, and restart behavior have **not** been demonstrated by passing runtime tests.

## Project map

| Path | Role |
| --- | --- |
| `app.py` · `n8n_client.py` | Streamlit interface and local webhook client |
| `projet/agentic_local/api.py` | FastAPI feature tools and health route |
| `projet/agentic_local/evidence.py` | Source, quotation, attribution, and answer checks |
| `projet/agentic_local/tools.py` | E5/Chroma, ViT, and metadata retrieval implementations |
| `projet/agentic_local/schemas.py` | Shared request, state, evidence, and response models |
| `projet/n8n/bcmid_workflow.n8n.json` | Portable stable n8n workflow export |
| `projet/n8n/workflow_code/` | Stable route and safe-response Code node logic |
| `notebooks/` | Modular RAG and local model notebooks |
| `docs/architecture.svg` · `docs/answer-flow.svg` | Documentation diagrams reconstructed from workflow/code structure |
| `docs/testing.md` · `docs/verification-status.md` | Safe local checks and evidence-backed status summary |

The retired `/agent/query` API route returns HTTP 410: orchestration belongs in n8n.

## Run the stable demo locally · Windows

Local data, indexes, model assets, and Ollama model tags must already exist. Startup does not download or rebuild them. Run each service in a separate PowerShell window.

### FastAPI feature tools

```powershell
Set-Location .\projet\agentic_local
.\start_api.ps1
```

Open [FastAPI docs](http://127.0.0.1:8000/docs) or [health](http://127.0.0.1:8000/health). The default API host and port are `127.0.0.1:8000`; override with `BCMID_API_HOST`, `BCMID_API_PORT`, or `BCMID_PYTHON` as needed. The API launcher uses offline Hugging Face settings and requires an environment with its listed dependencies.

### Ollama and n8n

The stable deterministic extraction path does not need Ollama. The unpublished agent prototype uses a local Ollama chat model. If inspecting that prototype, check installed model tags with `ollama list`; do not download a model as part of this setup. API health configuration defaults are `OLLAMA_BASE_URL=http://127.0.0.1:11434` and `OLLAMA_MODEL=qwen2.5-coder:7b`.

```powershell
Set-Location .\projet\agentic_local
.\start_n8n_demo.ps1
```

Open [n8n](http://127.0.0.1:5678) and confirm the existing stable workflow is published. The stable production webhook is `POST http://127.0.0.1:5678/webhook/bcmid-agent`. `start_n8n_demo.ps1` reuses the existing n8n instance when its health endpoint is available; otherwise it starts n8n with its normal profile. The stable workflow is already present in the intended local profile. The JSON export is for review or restoration, not routine startup.

### Streamlit interface

From the repository root:

```powershell
Set-Location <repository-root>
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
.\start_ui.ps1
```

Open [the interface](http://127.0.0.1:8501). `.env.example` sets `N8N_WEBHOOK_URL` to the stable local webhook; the same value is the client default. Keep `.env`, n8n credentials, execution exports, report text, image data, and patient identifiers out of GitHub.

## Explore and verify

The interface offers Reports, Images, Image + reports, Metadata, and an optional checked-quotation path for explicit follow-up or BI-RADS evidence. Read the [testing guide](docs/testing.md) for safe inputs and expected route/status checks. It separates retrieval checks from checked-answer checks and from the unpublished agent/memory prototype.

Relevant existing checks include:

```powershell
Set-Location <repository-root>
pytest test_n8n_client.py test_app.py -q
node projet\agentic_local\tests\test_workflow.cjs
pytest projet\agentic_local\tests\test_core.py -q
```

The [verification status note](docs/verification-status.md) distinguishes checked-answer outcomes from retrieval success and structural prototype inspection. Read [the stable workflow export](projet/n8n/bcmid_workflow.n8n.json) alongside the diagrams when reviewing routing. Never activate the experimental workflow as part of the stable demo setup.

## Local assets and responsible use

Configure BCMID data, Chroma reports, image vectors, metadata catalog, and model cache through `projet/agentic_local/config.py` or its supported environment variables. Large datasets, report text, model weights, vector databases, and execution outputs are intentionally excluded from this public repository.

Use retrieved evidence for research exploration only. Image and report similarity do not establish that records belong to the same patient or examination, and they do not provide a diagnosis or recommendation.
