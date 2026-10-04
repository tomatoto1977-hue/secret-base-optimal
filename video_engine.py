import json, os, re, shutil, subprocess, tempfile, textwrap, uuid
from pathlib import Path

VIDEO_ROOT = Path(os.environ.get("VIDEO_OUTPUT_DIR", "/tmp/secret-base-videos"))
VIDEO_ROOT.mkdir(parents=True, exist_ok=True)

def engine_status():
    ffmpeg = bool(shutil.which("ffmpeg"))
    ffprobe = bool(shutil.which("ffprobe"))
    font = _font_file() if ffmpeg else ""
    return {"provider":"ffmpeg","available":ffmpeg and ffprobe,"paid":False,"external_saas":False,"ffmpeg":ffmpeg,"ffprobe":ffprobe,"japanese_font":font,"japanese_font_ok":bool(font)}

def _font_file():
    # Resolve an actual font file through fontconfig first; this is more reliable
    # than passing a font family name to FFmpeg's drawtext on minimal Render images.
    try:
        p = subprocess.check_output(["fc-match","-f","%{file}","Noto Sans CJK JP"], text=True, timeout=5).strip()
        if p and Path(p).exists():
            return p
    except Exception:
        pass
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansJP-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    return ""

def _clean(text):
    text = str(text or "").replace("\r"," ").replace("\n"," ")
    return " ".join(text.split())

def _scene_text(artifact, command):
    raw = _clean(artifact)
    raw = re.sub(r"https?://\\S+|\\b[\\w.-]+\\.onrender\\.com\\b", "", raw)
    if not raw:
        raw = _clean(command)
    # Keep the first few meaningful chunks. The renderer is deliberately deterministic.
    chunks = [x.strip(" -•・【】") for x in textwrap.wrap(raw, width=48, break_long_words=False, break_on_hyphens=False) if x.strip()]
    if not chunks:
        chunks = ["秘密基地 最適版"]
    return chunks[:12]

def _write_text(path, text):
    path.write_text(text, encoding="utf-8")

def _esc_filter_path(path):
    return str(path).replace("\\","/").replace(":","\\:")

def render(package, output_path=None):
    status = engine_status()
    if not status["available"]:
        return {"ok":False,"status":"ffmpeg_unavailable","engine":status}

    command = _clean(package.get("command",""))
    artifact = str(package.get("production_spec","") or package.get("artifact",""))
    chunks = _scene_text(artifact, command)
    title = _clean(package.get("title") or command or "秘密基地")
    test_mode = bool(package.get("test_mode", False))
    # Production: six 5-second scenes. Self-test: one short scene to keep service startup fast.
    scene_count = 1 if test_mode else 6
    scene_duration = 1 if test_mode else 5
    total = scene_count * scene_duration
    if output_path is None:
        output_path = str(VIDEO_ROOT / ("video_" + uuid.uuid4().hex[:12] + ".mp4"))
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="sbvideo_"))
    segment_files = []
    try:
        font = _font_file()
        if not font:
            return {"ok":False,"status":"japanese_font_unavailable","engine":status}
        title_file = work / "title.txt"
        _write_text(title_file, title[:70])

        # Render scenes with a low-memory FFmpeg configuration.\n        # Explicit initialization keeps the startup self-test safe across reloads.
        for i in range(scene_count):
            body = chunks[i % len(chunks)]
            body_file = work / f"body_{i}.txt"
            caption_file = work / f"caption_{i}.txt"
            _write_text(body_file, body[:110])
            _write_text(caption_file, f"{i+1}/{scene_count}  {body[:55]}")
            seg = work / f"seg_{i}.mp4"
            # Different hue per scene. No external image/video assets are used.
            hue = [0.08,0.16,0.28,0.42,0.58,0.72][i]
            color = ["#20192f","#182b35","#2b2234","#19312d","#30251c","#20233a"][i]
            vf = (
                f"drawtext=fontfile='{_esc_filter_path(font)}':textfile='{_esc_filter_path(title_file)}':"
                f"fontcolor=white:fontsize=62:borderw=5:bordercolor=black:x=(w-text_w)/2:y=150,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':textfile='{_esc_filter_path(body_file)}':"
                f"fontcolor=white:fontsize=52:borderw=4:bordercolor=black:x=70:y=(h-text_h)/2-30:"
                f"line_spacing=12,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':textfile='{_esc_filter_path(caption_file)}':"
                f"fontcolor=white:fontsize=34:borderw=3:bordercolor=black:x=70:y=h-220"
            )
            cmd=[
                "ffmpeg","-y","-f","lavfi","-i",f"color=c={color}:s=1080x1920:r=30",
                "-t",str(scene_duration),"-vf",vf,
                "-c:v","libx264","-preset","ultrafast","-threads","1","-pix_fmt","yuv420p","-an",str(seg)
            ]
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=120)
            if p.returncode!=0:
                return {"ok":False,"status":"scene_render_error","engine":status,"scene":i+1,"error":p.stderr[-1500:]}
            segment_files.append(seg)

        concat = work / "concat.txt"
        concat.write_text("".join(f"file '{p}'\n" for p in segment_files), encoding="utf-8")
        # Concatenate the visual scenes and add generated, royalty-free synthetic audio.
        audio = work / "audio.wav"
        ap=subprocess.run([
            "ffmpeg","-y","-f","lavfi","-i",
            f"sine=frequency=196:sample_rate=48000:duration={total}",
            "-af","volume=0.035,afade=t=in:st=0:d=1,afade=t=out:st=27:d=3",
            "-c:a","pcm_s16le",str(audio)
        ],capture_output=True,text=True,timeout=60)
        if ap.returncode!=0:
            return {"ok":False,"status":"audio_render_error","engine":status,"error":ap.stderr[-1000:]}

        p=subprocess.run([
            "ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),"-i",str(audio),
            "-c:v","libx264","-preset","ultrafast","-threads","1","-pix_fmt","yuv420p","-r","30",
            "-c:a","aac","-b:a","96k","-threads","1","-shortest","-movflags","+faststart",str(out)
        ],capture_output=True,text=True,timeout=240)
        if p.returncode!=0:
            return {"ok":False,"status":"final_mux_error","engine":status,"error":p.stderr[-1500:]}

        probe=subprocess.run([
            "ffprobe","-v","error","-show_entries",
            "format=duration:stream=codec_name,width,height,r_frame_rate,codec_type",
            "-of","json",str(out)
        ],capture_output=True,text=True,timeout=30)
        if probe.returncode!=0:
            return {"ok":False,"status":"probe_failed","engine":status,"error":probe.stderr[-1000:]}
        info=json.loads(probe.stdout)
        streams=info.get("streams",[])
        video=next((s for s in streams if s.get("codec_type")=="video"),{})
        audio_stream=next((s for s in streams if s.get("codec_type")=="audio"),{})
        duration=float(info.get("format",{}).get("duration",0) or 0)
        valid=(video.get("codec_name")=="h264" and video.get("width")==1080 and video.get("height")==1920 and duration>=(0.9 if test_mode else 29) and audio_stream.get("codec_name")=="aac")
        if not valid:
            return {"ok":False,"status":"validation_failed","engine":status,"path":str(out),"probe":info}
        return {
            "ok":True,"status":"rendered","engine":status,"path":str(out),
            "filename":out.name,"duration_seconds":round(duration,2),
            "format":{"width":1080,"height":1920,"fps":30,"container":"mp4","video_codec":"h264","audio_codec":"aac"},
            "scene_count":scene_count,"scene_change_seconds":5,
            "assets":"generated-only; no external SaaS media",
            "quality":"draft MP4 validated by ffprobe"
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)

def self_test():
    status=engine_status()
    if not status["available"]:
        return {"ok":False,"status":"ffmpeg_unavailable","engine":status}
    pkg={"command":"テスト動画","production_spec":"完成成果物。9:16。1080x1920。冒頭2秒フック。2〜6秒。白文字。黒フチ。CTA。","test_mode":True}
    path=str(VIDEO_ROOT / ("selftest_"+uuid.uuid4().hex[:8]+".mp4"))
    r=render(pkg,path)
    if r.get("ok"):
        try: Path(path).unlink(missing_ok=True)
        except Exception: pass
    return r

def multi_test():
    results=[]
    for i in range(3):
        r=self_test(); r["run"]=i+1; results.append(r)
    return {"ok":len(results)==3 and all(r.get("ok") for r in results),"runs":results}
