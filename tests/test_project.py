from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[1]

def test_required_project_files_exist():
    for name in ["index.html", "server.py", "video_engine.py", "c-validation.html", "manifest.webmanifest"]:
        assert (ROOT / name).exists(), name

def test_python_sources_parse():
    for name in ["server.py", "video_engine.py"]:
        ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)

def test_mobile_viewport_and_safety_notice():
    html = (ROOT / "index.html").read_text(encoding="utf-8")
    assert 'name="viewport"' in html
    assert "外部投稿・ログイン・金銭操作は行いません" in html
    assert "実AIが接続されていない場合、成果物を捏造せず停止します" in html

def test_c_validation_is_explicitly_no_mp4():
    html = (ROOT / "c-validation.html").read_text(encoding="utf-8")
    assert "実MP4は生成しません" in html
    assert "window.runCValidation" in html

def test_server_has_health_and_safety_controls():
    src = (ROOT / "server.py").read_text(encoding="utf-8")
    assert "VERSION=" in src
    assert "COPYRIGHT_TOPIC_TERMS" in src
    assert "SELF_TEST_TOKEN" in src
    assert "RUN_SMOKE_ON_START" in src
