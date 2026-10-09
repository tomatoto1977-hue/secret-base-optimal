from pathlib import Path
import ast
ROOT = Path(__file__).resolve().parents[1]

def test_local_integration_worker_parses():
    ast.parse((ROOT / "local_integration_worker.py").read_text(encoding="utf-8"))

def test_local_integration_is_opt_in_and_safe():
    src=(ROOT / "local_integration_worker.py").read_text(encoding="utf-8")
    docs=(ROOT / "LOCAL_INTEGRATIONS.md").read_text(encoding="utf-8")
    assert 'ALLOW_CLAUDE_CODE", "false"' in src
    assert 'ALLOW_LOCAL_COMFYUI", "false"' in src
    assert 'SECRET_BASE_BRIDGE_TOKEN' in src
    assert 'mp4_updated_with_ai_images' in src
    assert 'arbitrary remote shell commands' in docs
