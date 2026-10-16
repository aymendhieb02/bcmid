$ErrorActionPreference = 'Stop'
try {
  $response = Invoke-RestMethod -Uri 'http://127.0.0.1:5678/healthz' -TimeoutSec 2
  if ($response.status -eq 'ok') {
    Write-Host 'Your existing n8n instance is running at http://127.0.0.1:5678.'
    Write-Host 'Published BCMID workflow: http://127.0.0.1:5678/workflow/bcmidLocalToolsDemo'
    return
  }
} catch { }
# Start the normal n8n profile; do not override N8N_USER_FOLDER or port settings.
$env:N8N_DIAGNOSTICS_ENABLED = 'false'
# The UI permits 20 MiB images and sends base64 JSON (up to ~27 MiB).
# n8n's default webhook body limit is 16 MiB, so allow headroom for that payload.
$env:N8N_PAYLOAD_SIZE_MAX = '32'
n8n start
