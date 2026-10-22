# BCMID local test guide

Use synthetic or de-identified inputs. The Streamlit pages use separate routes:

- **Chat assistant:** `N8N_WEBHOOK_URL`, configured by default to `/webhook/bcmid-seven-native-agents-5a4b5466e029`.
- **Explore evidence:** `N8N_EVIDENCE_WEBHOOK_URL`, configured by default to `/webhook/bcmid-agent`.

Confirm both values in the app’s local `.env` and check that the intended workflow is active in the existing n8n instance on port `5678`. A canvas screenshot or a successful HTTP status does not prove an end-to-end tool call.

## Start the local services

Run the API from the repository checkout:

```powershell
Set-Location .\projet\agentic_local
.\start_api.ps1
```

Check `http://127.0.0.1:8000/health`. Use the existing n8n service at `http://127.0.0.1:5678`; do not create another profile or instance for these checks. Start Streamlit from the repository root:

```powershell
Set-Location <repository-root>
.\start_ui.ps1
```

Open `http://127.0.0.1:8501`. The app’s Connections panel shows the selected route for each page.

## Route checks

Submit one request at a time. Inspect the matching n8n execution and compare the request intent with the actual API node calls.

| Scenario | Page and input | Verify |
| --- | --- | --- |
| Report retrieval | Chat assistant: “Find report findings about annual follow up.” | Report search ran; displayed passages retain their source IDs, patient, and train split; accepted answers pass the final citation check. |
| Image-only search | Chat assistant: attach a de-identified query image and ask for similar images | Image retrieval ran on training data, excludes the query patient, and shows retrieved thumbnails as examples from other cases. |
| Image plus report | Chat assistant: attach a de-identified image and ask a report question | Both evidence types were returned and stay attributed to their own records; no image interpretation is claimed. |
| Metadata | Chat assistant: request a catalog lookup for a supplied string ID | Metadata tool ran; leading zeros are preserved; every image/report source belongs to the requested patient. |
| Source-only report search | Explore evidence: select Reports and “Return source passages” | Normal evidence workflow returned passages without a generated answer. |
| Checked quotation | Explore evidence: select Reports and “Checked quotations” | The checker accepted exact supported wording and matching citations, or the app safely withheld the answer. |
| Invalid or out-of-scope request | Either page: use an unsupported field or ask for diagnosis/recommendation | Safe rejection or abstention; no unsupported clinical claim is displayed. |

For image checks, inspect execution retention before upload. Saved executions must not retain raw image bytes, report text, or unnecessary identifiers. Do not delete executions manually from the database.

## Session memory checks

If the n8n canvas includes Simple Memory, check the execution data for the same opaque random session key on two turns, then use a new key and verify context isolation. The memory node should connect only to the Orchestrator. Clear conversation should rotate the key. Memory is conversational context, never evidence; each answer still needs retrieval and validation. Simple Memory is in-process and does not survive an n8n restart.

## Focused software checks

Run from the repository root when validating code changes:

```powershell
pytest test_n8n_client.py test_app.py -q
node projet\agentic_local\tests\test_workflow.cjs
pytest projet\agentic_local\tests\test_core.py -q
```

Mocked tests validate software behavior, not live n8n routing, retrieval relevance, or clinical accuracy. Record runtime claims only from the corresponding saved n8n execution.
