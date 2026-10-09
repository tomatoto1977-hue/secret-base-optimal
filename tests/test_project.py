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
    assert "RUN_VIDEO_SELF_TEST_ON_START" in src
    assert "VIDEO_ENGINE_SELF_TEST_SKIPPED" in src

def test_reply_handles_client_disconnect():
    src=(ROOT/"server.py").read_text(encoding="utf-8")
    assert "BrokenPipeError" in src
    assert "ConnectionResetError" in src


def test_video_quality_policy_and_editor_handoff():
    engine=(ROOT/"video_engine.py").read_text(encoding="utf-8")
    # Test the real render pipeline rather than stale names from an older design.
    assert "def render(" in engine
    assert "def _render_narration(" in engine
    assert "def scene_svg(" in engine
    assert "ffmpeg" in engine.lower()
    server=(ROOT/"server.py").read_text(encoding="utf-8")
    assert '"duration_seconds":71.05' in server
    assert '"final_pass":False' in server
    assert "final_pass_reason" in server


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
    assert "localStorage.removeItem('sb3_active_run_job')" in html
    assert "MP4の完成は未確認です" in html

def test_video_jobs_are_serialized_and_logged():
    server=(ROOT/"server.py").read_text(encoding="utf-8")
    assert "VIDEO_EXECUTOR=concurrent.futures.ThreadPoolExecutor(max_workers=1" in server
    assert "RUN_EXECUTOR=concurrent.futures.ThreadPoolExecutor(max_workers=1" in server
    assert "VIDEO_RENDER_COMPLETED" in server
    assert "VIDEO_RENDER_FAILED" in server
    assert "VIDEO_RENDER_EXCEPTION" in server

def test_narration_failure_stops_instead_of_reading_the_brief():
    engine=(ROOT/"video_engine.py").read_text(encoding="utf-8")
    assert '"--retries","1","--timeout","12"' in engine
    assert '"stderr":(install.stderr or "")[-1800:]' in engine
    assert 'return {"ok":False,"reason":"edge_tts_unavailable"}' in engine
    assert '"status":"narration_script_missing"' in engine
    assert '"status":"narration_generation_failed"' in engine
    assert "if not narration_text:" not in engine

def test_video_ai_quota_fails_closed_and_does_not_use_fixed_script():
    server=(ROOT/"server.py").read_text(encoding="utf-8")
    assert "VIDEO_AI_RATE_LIMIT_SAFE_STOP" in server
    assert "動画制作を安全停止しました" in server
    assert "if is_video_request(command) and not (KEY or ALT_TOKEN):" in server
    assert "固定台本で代用せず" in server

def test_bgm_is_musical_and_observable():
    engine=(ROOT/"video_engine.py").read_text(encoding="utf-8")
    assert "def _write_bgm(" in engine
    assert "locally_synthesized_instrumental_bgm" in engine
    assert "bgm_details" in engine
    server=(ROOT/"server.py").read_text(encoding="utf-8")
    assert '"bgm_status"' in server

def test_obisidian_export_is_explicit_about_vault_sync():
    server=(ROOT/"server.py").read_text(encoding="utf-8")
    assert "def write_obsidian_note(" in server
    assert 'self.path.startswith("/obsidian/")' in server
    assert "downloadable_markdown_not_vault_sync" in server
    assert "Vaultへの自動同期は未接続" in server

def test_progress_metrics_do_not_claim_ai_images_exist():
    server=(ROOT/"server.py").read_text(encoding="utf-8")
    engine=(ROOT/"video_engine.py").read_text(encoding="utf-8")
    assert '"ai_images_created":0' in server
    assert '"ai_images_generated":False' in server
    assert '"ai_images_generated":False' in engine

def test_video_generation_keeps_run_locked_until_background_job_finishes():
    html=(ROOT/"index.html").read_text(encoding="utf-8")
    assert "await pollVideoJob(video.job_id)" in html
    assert "動画生成が停止しました：" in html
