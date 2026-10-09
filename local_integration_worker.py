#!/usr/bin/env python3
"""Opt-in local companion for Secret Base Optimal. No paid APIs or publishing."""
from __future__ import annotations
import json, os, re, shutil, subprocess, time, urllib.error, urllib.request, urllib.parse
from pathlib import Path
from urllib.parse import urljoin

API = os.environ.get("SECRET_BASE_API", "https://secret-base-optimal-api.onrender.com").rstrip("/") + "/"
TOKEN = os.environ.get("SECRET_BASE_BRIDGE_TOKEN", "").strip()
VAULT = Path(os.environ.get("OBSIDIAN_VAULT_PATH", "")).expanduser()
COMFY = os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/")
WORK = Path(os.environ.get("SECRET_BASE_WORK_DIR", str(Path.home() / "SecretBaseWork"))).expanduser()
WORK.mkdir(parents=True, exist_ok=True)
WORKFLOW = Path(os.environ.get("COMFYUI_API_WORKFLOW", str(WORK / "workflow_api.json"))).expanduser()
POLL_SECONDS = max(5, int(os.environ.get("SECRET_BASE_POLL_SECONDS", "15")))
MAX_IMAGES = min(12, max(1, int(os.environ.get("SECRET_BASE_MAX_IMAGES", "12"))))
ALLOW_CLAUDE = os.environ.get("ALLOW_CLAUDE_CODE", "false").lower() == "true"
ALLOW_COMFY = os.environ.get("ALLOW_LOCAL_COMFYUI", "false").lower() == "true"

def request(path: str, method="GET", payload=None):
    if not TOKEN:
        raise RuntimeError("SECRET_BASE_BRIDGE_TOKEN is not configured; bridge disabled")
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(urljoin(API, path.lstrip("/")), data=data, method=method,
        headers={"Authorization": "Bearer " + TOKEN, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))

def safe_name(value):
    return re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "job"))[:60].strip("-") or "job"

def run_claude(command, artifact, outdir):
    if not ALLOW_CLAUDE:
        return {"status":"disabled","reason":"ALLOW_CLAUDE_CODE is false"}
    exe = shutil.which("claude")
    if not exe:
        return {"status":"unavailable","reason":"Claude Code CLI not found"}
    prompt = f"""あなたは日本語ショート動画の脚本編集者です。
企画: {command}
元資料: {artifact[:12000]}
自然な話し言葉の独自ナレーション台本を作成してください。企画書を読み上げないでください。
個人・芸能人・既存作品・歌詞・転載素材に依存せず、事実の捏造や根拠のない断定を避けます。
出力は台本本文のみ。"""
    p = subprocess.run([exe, "-p", prompt, "--output-format", "text"],
        capture_output=True, text=True, timeout=240, cwd=str(outdir))
    if p.returncode != 0 or not p.stdout.strip():
        return {"status":"failed","reason":(p.stderr or "Claude Code returned no script")[-1200:]}
    (outdir / "narration_script.txt").write_text(p.stdout.strip(), encoding="utf-8")
    return {"status":"generated","path":"narration_script.txt","characters":len(p.stdout.strip())}

def generate_images(outdir, prompt_text, count):
    if not ALLOW_COMFY:
        return {"status":"disabled","reason":"ALLOW_LOCAL_COMFYUI is false","images":[]}
    if not WORKFLOW.is_file():
        return {"status":"workflow_missing","reason":"ComfyUI API workflow JSON missing","images":[]}
    try:
        with urllib.request.urlopen(COMFY + "/system_stats", timeout=5) as r:
            if r.status != 200: raise RuntimeError("ComfyUI unavailable")
    except Exception as exc:
        return {"status":"unavailable","reason":str(exc)[:300],"images":[]}
    raw = WORKFLOW.read_text(encoding="utf-8")
    if "{{PROMPT}}" not in raw:
        return {"status":"workflow_invalid","reason":"Workflow must contain {{PROMPT}} placeholder","images":[]}
    images=[]
    for i in range(count):
        graph_text = raw.replace("{{PROMPT}}", prompt_text + f", original editorial illustration, vertical composition, scene {i+1}")
        graph_text = graph_text.replace("{{SEED}}", str(int(time.time()) + i))
        try:
            graph = json.loads(graph_text)
            req = urllib.request.Request(COMFY + "/prompt", data=json.dumps({"prompt":graph}).encode(),
                headers={"Content-Type":"application/json"})
            with urllib.request.urlopen(req, timeout=30) as r: queued=json.loads(r.read().decode())
            prompt_id = queued.get("prompt_id")
            if not prompt_id: continue
            deadline=time.time()+240
            while time.time()<deadline:
                time.sleep(2)
                with urllib.request.urlopen(COMFY + "/history/" + prompt_id, timeout=15) as r:
                    history=json.loads(r.read().decode()).get(prompt_id,{})
                found=[]
                for node in history.get("outputs",{}).values():
                    for img in node.get("images",[]):
                        params=urllib.parse.urlencode({"filename":img["filename"],"subfolder":img.get("subfolder",""),"type":img.get("type","output")})
                        with urllib.request.urlopen(COMFY + "/view?" + params, timeout=30) as r: blob=r.read()
                        dest=outdir / f"scene_{i+1:02d}.png"; dest.write_bytes(blob); found.append(dest.name)
                if found:
                    images.extend(found); break
        except Exception as exc:
            return {"status":"partial_failure" if images else "failed","reason":str(exc)[:500],"images":images}
    return {"status":"generated" if images else "failed","images":images,"count":len(images)}

def compose_ai_images_video(task, outdir, image_result):
    """Create a local 9:16 MP4 from generated images and original video audio."""
    image_names = [name for name in image_result.get("images", []) if (outdir / name).is_file()]
    video_url = str(task.get("video_url") or "").strip()
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not image_names:
        return {"status": "skipped_no_images", "mp4_updated_with_ai_images": False}
    if not video_url.startswith("https://"):
        return {"status": "skipped_video_url_missing", "mp4_updated_with_ai_images": False}
    if not ffmpeg or not ffprobe:
        return {"status": "ffmpeg_unavailable", "mp4_updated_with_ai_images": False}
    base, slideshow, final = outdir / "base_video.mp4", outdir / "ai_image_video.mp4", outdir / "secret_base_ai_images.mp4"
    try:
        req = urllib.request.Request(video_url, headers={"User-Agent": "SecretBaseLocalWorker/1.0"})
        with urllib.request.urlopen(req, timeout=120) as response, base.open("wb") as dst:
            shutil.copyfileobj(response, dst)
        if not base.is_file() or base.stat().st_size < 10000:
            return {"status": "base_video_download_invalid", "mp4_updated_with_ai_images": False}
        probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(base)], capture_output=True, text=True, timeout=30)
        if probe.returncode:
            return {"status": "base_video_probe_failed", "mp4_updated_with_ai_images": False}
        info = json.loads(probe.stdout)
        duration = float(info.get("format", {}).get("duration") or 0)
        if duration < 1 or not any(s.get("codec_type") == "audio" for s in info.get("streams", [])):
            return {"status": "base_video_audio_or_duration_missing", "mp4_updated_with_ai_images": False}
        per_image = duration / len(image_names)
        concat = outdir / "ai_images_concat.txt"
        lines = []
        for name in image_names:
            path = str((outdir / name).resolve()).replace("\\", "/")
            lines.extend(["file '" + path + "'", "duration " + format(per_image, ".6f")])
        last = str((outdir / image_names[-1]).resolve()).replace("\\", "/")
        lines.append("file '" + last + "'")
        concat.write_text("\n".join(lines) + "\n", encoding="utf-8")
        render = subprocess.run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-vf",
            "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,format=yuv420p",
            "-t", format(duration, ".3f"), "-c:v", "libx264", "-preset", "ultrafast", "-threads", "2", "-an", "-movflags", "+faststart", str(slideshow)],
            capture_output=True, text=True, timeout=600)
        if render.returncode or not slideshow.is_file() or slideshow.stat().st_size < 10000:
            return {"status": "image_slideshow_render_failed", "mp4_updated_with_ai_images": False, "reason": (render.stderr or "")[-800:]}
        mux = subprocess.run([ffmpeg, "-y", "-i", str(slideshow), "-i", str(base), "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy", "-c:a", "aac", "-af", "apad", "-shortest", "-movflags", "+faststart", str(final)],
            capture_output=True, text=True, timeout=300)
        if mux.returncode or not final.is_file() or final.stat().st_size < 10000:
            return {"status": "ai_image_audio_mux_failed", "mp4_updated_with_ai_images": False, "reason": (mux.stderr or "")[-800:]}
        verify = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(final)], capture_output=True, text=True, timeout=30)
        if verify.returncode:
            return {"status": "ai_image_mp4_validation_failed", "mp4_updated_with_ai_images": False}
        result = json.loads(verify.stdout)
        streams = result.get("streams", [])
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        has_audio = any(s.get("codec_type") == "audio" for s in streams)
        output_duration = float(result.get("format", {}).get("duration") or 0)
        if video.get("width") != 1080 or video.get("height") != 1920 or not has_audio or output_duration < duration * 0.95:
            return {"status": "ai_image_mp4_validation_failed", "mp4_updated_with_ai_images": False}
        return {"status": "generated_and_validated", "mp4_updated_with_ai_images": True,
                "filename": final.name, "image_count": len(image_names), "duration_seconds": round(output_duration, 2)}
    except Exception as exc:
        return {"status": "ai_image_composition_failed", "mp4_updated_with_ai_images": False, "reason": str(exc)[:500]}


def write_vault(task, script_result, image_result):
    if not str(VAULT) or not VAULT.is_dir():
        return {"status":"vault_path_missing","reason":"Set OBSIDIAN_VAULT_PATH to an existing vault"}
    job_id=safe_name(task.get("job_id"))
    folder=VAULT / "Secret Base" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    title=str(task.get("command") or "動画制作")[:80]
    lines=["---","source: Secret Base Optimal",f"job_id: {job_id}","human_review_required: true","---","",
      "# "+title,"",f"- 作成日時: {time.strftime('%Y-%m-%d %H:%M:%S')}",
      f"- Claude Code: {script_result.get('status','unknown')}",
      f"- AI画像生成: {image_result.get('status','unknown')}",
      "- 自動投稿: 無効","- 課金API: 使用しない",""]
    if task.get("video_url"): lines += [f"- 元MP4: {task['video_url']}",""]
    if script_result.get("path"): lines += ["## ナレーション台本","","![[narration_script.txt]]",""]
    if image_result.get("images"):
        lines += ["## AI生成シーン画像",""] + [f"![[{name}]]" for name in image_result["images"]] + [""]
    composition=task.get("ai_image_video") or {}
    if composition.get("filename"):
        lines += ["## AI画像反映版MP4","",f"- ファイル: [[{composition['filename']}]]",
                  f"- 状態: {composition.get('status')}",f"- 画像数: {composition.get('image_count',0)}",
                  "- iPhone等で再生して最終確認してください。",""]
    else:
        lines += ["## AI画像反映版MP4","",f"- 状態: {composition.get('status','not_created')}",
                  "- AI画像がMP4へ反映できたとは確認できていません。",""]
    lines += ["## 状態","",f"- 台本: {script_result.get('status')}",f"- 画像: {image_result.get('status')}",
      "- 自動投稿は無効。公開前に人間確認が必要です。",""]
    if script_result.get("path"):
        shutil.copy2(WORK/job_id/"narration_script.txt", folder/"narration_script.txt")
    for name in image_result.get("images",[]):
        src=WORK/job_id/name
        if src.is_file(): shutil.copy2(src, folder/name)
    composition=task.get("ai_image_video") or {}
    if composition.get("filename"):
        src=WORK/job_id/composition["filename"]
        if src.is_file(): shutil.copy2(src,folder/src.name)
    (folder / "制作記録.md").write_text("\n".join(lines), encoding="utf-8")
    return {"status":"synced_to_local_vault","path":str(folder / "制作記録.md")}

def handle(task):
    job_id=safe_name(task.get("job_id"))
    outdir=WORK/job_id; outdir.mkdir(parents=True, exist_ok=True)
    command=str(task.get("command") or "")
    artifact=str(task.get("artifact") or "")
    script=run_claude(command,artifact,outdir)
    prompt=(outdir/"narration_script.txt").read_text(encoding="utf-8") if script.get("path") else artifact
    images=generate_images(outdir,prompt,MAX_IMAGES)
    composition=compose_ai_images_video(task,outdir,images)
    task_for_vault={**task,"video_url":task.get("video_url"),"ai_image_video":composition}
    vault=write_vault(task_for_vault,script,images)
    result={"job_id":task.get("job_id"),"claude":script,"images":images,"ai_image_video":composition,"obsidian":vault,
      "human_review_required":True,"mp4_updated_with_ai_images":composition.get("mp4_updated_with_ai_images",False)}
    request("/integration/result","POST",result)
    print(json.dumps(result,ensure_ascii=False))

def main():
    if not TOKEN: raise SystemExit("Bridge disabled: configure SECRET_BASE_BRIDGE_TOKEN. No requests sent.")
    print("Local companion running; paid providers, auto-publishing, and remote shell execution are disabled.")
    while True:
        try:
            result=request("/integration/next")
            if result.get("task"): handle(result["task"])
        except urllib.error.HTTPError as exc:
            if exc.code not in (204,404): print("bridge HTTP error",exc.code,exc.read()[:300].decode(errors="replace"))
        except Exception as exc: print("bridge error:",str(exc)[:300])
        time.sleep(POLL_SECONDS)

if __name__=="__main__": main()
