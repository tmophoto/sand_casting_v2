# Register this Windows PC as a Cursor "My Machine" worker so cloud agents
# run commands HERE (on your 3090s) instead of Cursor's generic cloud VM.
#
# Run once on the GPU PC, keep the worker running while you use agents.
$ErrorActionPreference = "Stop"

Write-Host @"

=== Why cloud agents can't see your GPUs ===

This chat is running on Cursor's managed cloud VM (no GPU, no Docker).
Your Mac and DGX Spark work because they have a Cursor worker installed:
  agent worker start

Your Windows 3090 box is NOT registered yet — only Mac workers show up.

"@

Write-Host "Installing Cursor CLI..."
irm 'https://cursor.com/install?win32=true' | iex

Write-Host ""
Write-Host @"
=== Next steps (on THIS machine) ===

1. Start the worker (leave this window open):

     agent worker start

   Or with a GPU pool label (Enterprise teams):

     agent worker --pool gpu start

2. In Cursor, start a NEW cloud agent and select:
   - "My Machine" / your Windows worker
   NOT the default cloud infrastructure

3. Then ask the agent to run:

     cd scripts/vllm-3090
     ./install-and-launch-tailscale.sh

   It will download twolven/Qwen3.8-27B-abliterated-AWQ-MTP and launch vLLM.

4. Tailscale: install on Windows if not already
     https://tailscale.com/download/windows
   Connect to: http://<tailscale-ip>:8080/v1

Docs: https://cursor.com/docs/cloud-agent/bring-your-own-machine
"@
