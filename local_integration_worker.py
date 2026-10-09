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
    lines += ["## 状態","",f"- 台本: {script_result.get('status')}",f"- 画像: {image_result.get('status')}",
      "- 注意: AI画像は元MP4へ合成済みとは限りません。最終動画は目視確認が必要です。",""]
    if script_result.get("path"):
        shutil.copy2(WORK/job_id/"narration_script.txt", folder/"narration_script.txt")
    for name in image_result.get("images",[]):
        src=WORK/job_id/name
        if src.is_file(): shutil.copy2(src, folder/name)
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
    vault=write_vault({**task,"video_url":task.get("video_url")},script,images)
    result={"job_id":task.get("job_id"),"claude":script,"images":images,"obsidian":vault,
      "local_artifact_dir":str(outdir),"human_review_required":True,"mp4_updated_with_ai_images":False}
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
