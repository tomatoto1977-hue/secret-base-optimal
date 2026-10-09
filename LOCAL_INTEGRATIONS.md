# Secret Base local integrations (Windows + Obsidian)

This optional companion runs on the user's PC because Render cannot access a Windows folder, local ComfyUI, or the Obsidian vault on an iPhone. It is opt-in and requires a bridge token.

## Connections
- Claude Code CLI for script drafting, disabled by default. It uses the locally signed-in account; usage limits depend on that account.
- ComfyUI API at http://127.0.0.1:8188 for local image generation, disabled by default. It requires a local model and API-format workflow JSON with {{PROMPT}} and optionally {{SEED}} placeholders.
- Obsidian vault on the same computer. Writes Secret Base/<job-id>/制作記録.md and generated images directly to the vault.
- Render API bridge authenticated with a bearer token. Never commit the token.

## Setup
1. Install Python 3.11+ and FFmpeg on Windows.
2. Install Claude Code and confirm the account usage limits before enabling it.
3. Install ComfyUI locally and a licensed model. Export an API-format workflow JSON to %USERPROFILE%\\SecretBaseWork\\workflow_api.json. Include {{PROMPT}} in the prompt field and optionally {{SEED}} in the seed field.
4. Find the actual local Obsidian vault folder. An iPhone-only vault is not a Windows path; use an existing synced folder or approved sync method.
5. In Render, set INTEGRATION_BRIDGE_TOKEN to a long random secret. This setting is not automatically changed by this code.
6. On Windows, set the same secret as SECRET_BASE_BRIDGE_TOKEN, plus OBSIDIAN_VAULT_PATH. Set ALLOW_CLAUDE_CODE=true and/or ALLOW_LOCAL_COMFYUI=true only after manually testing those tools. Both default to false.
7. Set the token and vault path for the current PowerShell session, then run `./start_secret_base_local.ps1`. The launcher keeps Claude Code and ComfyUI disabled unless explicitly enabled. Alternatively run `python local_integration_worker.py` directly. Keep the PC awake and connected.

Example PowerShell (replace values locally; never paste the token into GitHub):

```powershell
$env:SECRET_BASE_API="https://secret-base-optimal-api.onrender.com"
$env:SECRET_BASE_BRIDGE_TOKEN="YOUR_LOCAL_SECRET"
$env:OBSIDIAN_VAULT_PATH="C:\\Users\\YOUR_USER\\Documents\\Obsidian Vault"
$env:ALLOW_CLAUDE_CODE="false"
$env:ALLOW_LOCAL_COMFYUI="false"
./start_secret_base_local.ps1
```

## Safety and limitations
- No paid image APIs or credit purchases; image generation is local ComfyUI only.
- No automatic social publishing, login automation, money operations, or arbitrary remote shell commands.
- The server exposes authenticated /integration/next and /integration/result routes. The Render environment variable INTEGRATION_BRIDGE_TOKEN must be configured before the worker can connect. Until then the bridge remains disabled.
- ComfyUI workflows vary by model/node graph; incompatible workflows fail closed.
- When local ComfyUI produces images and the Render MP4 URL is available, the worker can build a separate local 1080x1920 MP4 using those images and the original video's audio, probe the output, and archive it in the Obsidian vault. This is a separate local artifact; it does not overwrite or upload to Render. If image generation, download, FFmpeg, audio, or validation fails, it records mp4_updated_with_ai_images=false and keeps the original MP4 unchanged. End-to-end composition still requires testing on the user's Windows PC.
- iPhone access relies on the user's existing Obsidian sync; this script runs on Windows, not iOS.
