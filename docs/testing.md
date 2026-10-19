# BCMID local test guide

Use synthetic or de-identified inputs. Keep the session on the stable workflow. Do not publish or activate the agent/memory prototype for these checks.

## Start the stable path

Run the API from the repository checkout:

```powershell
Set-Location .\projet\agentic_local
.\start_api.ps1
```

Confirm `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/docs` respond. If model-backed features are enabled, check only the already installed Ollama tags with `ollama list`.

In another PowerShell window:

```powershell
Set-Location .\projet\agentic_local
.\start_n8n_demo.ps1
```

Open `http://127.0.0.1:5678/workflow/bcmidLocalToolsDemo` and confirm the existing stable workflow is published. Its production webhook is `http://127.0.0.1:5678/webhook/bcmid-agent`.

In a separate window, from the repository root, start the interface:

```powershell
Set-Location <repository-root>
.\start_ui.ps1
```

Open `http://127.0.0.1:8501`. `.env` may override `N8N_WEBHOOK_URL`; keep it pointed at the stable local production webhook.

## Synthetic route checks

Use the Streamlit forms to submit one request at a time. Inspect the status, `tools_called`, evidence sources, checker decision, and citations. The expected outputs below describe route behavior, not relevance or clinical validity.

| Check | Input | Expected route and result |
| --- | --- | --- |
| Report retrieval | A synthetic question asking for report wording about follow-up; select source passages | Report retrieval and evidence check; return referenced passages with status `retrieved` when available |
| Image-only search | A de-identified or synthetic reference image; no report question | Image retrieval only; return similar training images with source metadata |
| Image plus report | A synthetic/de-identified image and a report question | Both retrieval lanes; show report passages separately from similar images |
| Metadata match | An allowed filter such as modality or report availability | Metadata lookup only; return matching catalog rows or a no-match status |
| Invalid filter | An unsupported filter value or forbidden split | Reject as `invalid_request`; no retrieval tool should run |
| Out of scope | Ask for diagnosis or a recommendation about the uploaded image | Safe out-of-scope response; no diagnosis or clinical recommendation |
| Checked quotation | Ask for an explicit follow-up or BI-RADS statement and enable checked quotation | Release source wording only when the answer checker accepts and returns citations; otherwise `abstained` with no answer or citations |

For each request verify the source split is `train`, a supplied query patient is excluded from similar-case results, the source identifiers point to retrieved records, and any released quotation is exact and attributed to its cited source. Never treat an image neighbor’s metadata or report as a fact about the uploaded image.

## Focused software checks

Run from the repository root:

```powershell
pytest test_n8n_client.py test_app.py -q
node projet\agentic_local\tests\test_workflow.cjs
pytest projet\agentic_local\tests\test_core.py -q
```

These are software checks. Mocked tests do not prove that a live service or workflow is available. Webhook retrieval checks do not prove that a checked answer will be accepted.

## Agent and memory prototype

The separate agent/memory workflow remains unpublished. Static export inspection alone is not a runtime pass. Before considering publication, run a synthetic report question, image-only search, image-plus-question, metadata lookup, unsupported request, and checked-answer path. Record each agent/tool call and final status without retaining raw patient text or image data.

Then test memory with an opaque random `session_id`: use two turns with the same ID, a turn with a fresh ID, and a clear/reset that rotates the ID. Confirm the Orchestrator receives only its own session context, each question performs fresh evidence retrieval, and answer citations pass the checker. Restart n8n and inspect whether the in-process memory is lost. Do not describe Simple Memory as durable storage. Do not publish the workflow unless all required staged checks pass.

See [verification status](verification-status.md) for which capabilities have evidence and which remain unverified.
