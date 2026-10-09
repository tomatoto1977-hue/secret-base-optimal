from pathlib import Path
import ast
ROOT = Path(__file__).resolve().parents[1]

def test_required_files():
    for name in ["index.html","server.py","video_engine.py","c-validation.html","manifest.webmanifest","AGENTS.md"]:
        assert (ROOT/name).exists(), name

def test_python_parses():
    for name in ["server.py","video_engine.py"]:
        ast.parse((ROOT/name).read_text(encoding="utf-8"), filename=name)

def test_mobile_and_safety_ui():
    html=(ROOT/"index.html").read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    assert "外部投稿・ログイン・金銭操作は行いません" in html
    assert "成果物を捏造せず停止します" in html

def test_c_validation_is_not_real_mp4():
    html=(ROOT/"c-validation.html").read_text(encoding="utf-8")
    assert "実MP4は生成しません" in html
    assert "window.runCValidation" in html

def test_server_safety_controls():
    src=(ROOT/"server.py").read_text(encoding="utf-8")
    assert 'VERSION="3.8.1"' in src
    assert "COPYRIGHT_TOPIC_TERMS" in src
    assert "SELF_TEST_TOKEN" in src
    assert "RUN_SMOKE_ON_START" in src

def test_reply_handles_client_disconnect():
    src=(ROOT/"server.py").read_text(encoding="utf-8")
    assert "BrokenPipeError" in src
    assert "ConnectionResetError" in src


def test_video_quality_policy_and_external_editors():
    src=(ROOT/"video_engine.py").read_text(encoding="utf-8")
    assert "motion_graphics_draft" in src
    assert "final_pass" in src
    assert "CapCut" in src and "Canva" in src and "Adobe Express" in src
    server=(ROOT/"server.py").read_text(encoding="utf-8")
    assert '"duration_seconds":71.05' in server


def test_mp4_range_streaming_and_research_fallback():
    src=(ROOT/"server.py").read_text(encoding="utf-8")
    assert 'self.headers.get("Range","")' in src
    assert 'Accept-Ranges' in src
    assert 'Content-Range' in src
    assert 'RESEARCH_SOURCE_ERROR' in src
    assert '"source_warning":source_warning' in src

def test_stage_buttons_execute_and_retry_transient_errors():
    html=(ROOT/"index.html").read_text(encoding="utf-8")
    assert "setCommand(prompts[b.dataset.stage]||'制作工程を確認：');run();" in html
    assert "networkRetries<8" in html
    assert "j.source_warning" in html
