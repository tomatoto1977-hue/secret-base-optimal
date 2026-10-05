import json, os, re, shutil, subprocess, tempfile, textwrap, uuid, sys, urllib.request
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
        if p and Path(p).exists() and "dejavu" not in p.lower():
            return p
    except Exception:
        pass
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
        "/usr/share/fonts/truetype/noto/NotoSansJP-Regular.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    # Last fallback: fetch the openly licensed IPAex Gothic font once into the
    # service's temporary working directory. This is a static font asset, not a
    # video-generation SaaS dependency.
    try:
        font_path = VIDEO_ROOT / "ipaexg.ttf"
        if not font_path.exists():
            urllib.request.urlretrieve(
                "https://raw.githubusercontent.com/uehara1414/japanize-matplotlib/master/japanize_matplotlib/fonts/ipaexg.ttf",
                str(font_path)
            )
        if font_path.exists() and font_path.stat().st_size > 1000000:
            return str(font_path)
    except Exception as e:
        print("JAPANESE_FONT_FALLBACK_ERROR", str(e)[:500], flush=True)
    return ""

def _clean(text):
    text = str(text or "").replace("\r"," ").replace("\n"," ")
    return " ".join(text.split())

def _scene_text(artifact, command):
    raw = _clean(artifact)
    raw = re.sub(r"https?://\\S+|\\b[\\w.-]+\\.onrender\\.com\\b", "", raw)
    risky_terms = [
        "ドラゴンズドグマ", "KINGDOM HEARTS", "キングダムハーツ",
        "ドラゴンクエスト", "ポケットモンスター", "ポケモン",
        "鬼滅の刃", "ONE PIECE", "ワンピース", "呪術廻戦",
        "進撃の巨人", "名探偵コナン", "マリオ", "ゼルダの伝説"
    ]
    for term in risky_terms:
        raw = raw.replace(term, "オリジナルテーマ")
    if not raw:
        raw = _clean(command)
    chunks = [x.strip(" -•・【】") for x in textwrap.wrap(raw, width=36, break_long_words=False, break_on_hyphens=False) if x.strip()]
    if not chunks:
        chunks = ["秘密基地 最適版"]
    return chunks[:12]

def _display_lines(text, max_chars=18, max_lines=3):
    """Japanese-friendly fixed-width wrapping for FFmpeg drawtext textfile."""
    s = _clean(text)
    lines = []
    while s and len(lines) < max_lines:
        lines.append(s[:max_chars])
        s = s[max_chars:]
    if s and lines:
        lines[-1] = lines[-1][:-1] + "…"
    return "\n".join(lines)

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

    # Local render is a visual-motion draft. Final quality is intentionally
    # defined as a two-stage pipeline: this draft + free external editor finish.
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
        _write_text(title_file, _display_lines(title, max_chars=20, max_lines=2))

        # Six moving motion-graphic scenes. No third-party media is embedded.
        colors = ["#0d1220","#17122b","#101c22","#21151b","#111d18","#181325"]
        accents = ["#ffb36a","#8ee8d6","#ff8fa8","#a7e58b","#ffd27a","#9fb8ff"]
        kickers = ["課題を発見","ムダを可視化","3ステップで整理","数字で比較","今日から実践","保存して後で使う"]

        for i in range(scene_count):
            body = chunks[i % len(chunks)]
            body_file = work / f"body_{i}.txt"
            caption_file = work / f"caption_{i}.txt"
            kicker_file = work / f"kicker_{i}.txt"
            _write_text(body_file, _display_lines(body, max_chars=18, max_lines=4))
            _write_text(caption_file, _display_lines(f"{i+1}/{scene_count}  {body}", max_chars=22, max_lines=2))
            _write_text(kicker_file, kickers[i % len(kickers)])

            seg = work / f"seg_{i}.mp4"
            color = colors[i % len(colors)]
            accent = accents[i % len(accents)]
            scene_label = f"SCENE {i+1}/{scene_count}"

            # Animated cards, counters, icons, progress and subtle grain keep
            # the draft visually active instead of showing text on a flat screen.
            vf = (
                f"drawbox=x=0:y=0:w=1080:h=1920:color={color}:t=fill,"
                f"drawbox=x='-260+sin(t*0.55+{i})*340':y='{160+i*35}+cos(t*0.72)*160':w=760:h=760:color={accent}@0.22:t=fill,"
                f"drawbox=x='{570+40*i}+cos(t*0.42+{i})*260':y='{620+i*25}+sin(t*0.66)*220':w=640:h=720:color=#24d8c5@0.18:t=fill,"
                f"drawbox=x='{50+i*25}+sin(t*0.90+{i})*420':y='1240+cos(t*0.55)*160':w=520:h=360:color=#ff8f57@0.16:t=fill,"
                f"drawbox=x=48:y=55:w=984:h=340:color=black@0.46:t=fill,"
                f"drawbox=x=48:y=1515:w=984:h=300:color=black@0.52:t=fill,"
                f"drawbox=x=48:y=372:w=984:h=8:color={accent}:t=fill,"
                f"drawbox=x=90:y=1110:w=900:h=12:color=white@0.10:t=fill,"
                f"drawbox=x=90:y=1110:w='900*min(1,max(0,(t-0.25)/{max(scene_duration-0.5,0.5)}))':h=12:color={accent}:t=fill,"
                f"drawbox=x='-280+t*120':y=820:w=280:h=180:color=white@0.07:t=fill,"
                f"drawbox=x='1080-t*110':y=1020:w=280:h=180:color=white@0.06:t=fill,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':text='¥':fontcolor=white@0.14:fontsize='150+20*sin(t*1.2)':x='450+sin(t*0.5)*45':y=610,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':text='✓':fontcolor=white@0.20:fontsize='115+10*cos(t*1.6)':x='165+sin(t*0.8)*70':y=760,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':text='↗':fontcolor=white@0.18:fontsize='115+12*sin(t*1.1)':x='770+cos(t*0.7)*70':y=900,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':text='{scene_label}':fontcolor={accent}:fontsize=34:borderw=2:bordercolor=black:x=78:y=90,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':textfile='{_esc_filter_path(kicker_file)}':fontcolor=#d7d5e6:fontsize=30:borderw=2:bordercolor=black:x=78:y=135,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':textfile='{_esc_filter_path(title_file)}':fontcolor=white:fontsize=58:borderw=5:bordercolor=black:x=(w-text_w)/2:y=205,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':textfile='{_esc_filter_path(body_file)}':fontcolor=white:fontsize=54:borderw=5:bordercolor=black:x=(w-text_w)/2:y='720+14*sin(t*1.15)':line_spacing=16,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':text='保存して後で見直す':fontcolor=white:fontsize=34:borderw=3:bordercolor=black:x=(w-text_w)/2:y=1635,"
                "noise=alls=4:allf=t"
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

        # A synthetic music bed only: no copyrighted track is used.
        audio = work / "audio.wav"
        ap=subprocess.run([
            "ffmpeg","-y",
            "-f","lavfi","-i",f"sine=frequency=196:sample_rate=48000:duration={total}",
            "-f","lavfi","-i",f"sine=frequency=294:sample_rate=48000:duration={total}",
            "-f","lavfi","-i",f"sine=frequency=392:sample_rate=48000:duration={total}",
            "-filter_complex","[0:a]volume=0.020[a0];[1:a]volume=0.012[a1];[2:a]volume=0.008[a2];[a0][a1][a2]amix=inputs=3:normalize=0,afade=t=in:st=0:d=0.8,afade=t=out:st="+str(max(0,total-2)) + ":d=2",
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

        visual=_visual_frame_check(out,duration,scene_count)
        if not visual.get("ok"):
            return {"ok":False,"status":"visual_validation_failed","engine":status,"path":str(out),"probe":info,"visual_check":visual}

        return {
            "ok":True,"status":"rendered","engine":status,"path":str(out),
            "filename":out.name,"duration_seconds":round(duration,2),
            "format":{"width":1080,"height":1920,"fps":30,"container":"mp4","video_codec":"h264","audio_codec":"aac"},
            "scene_count":scene_count,"scene_change_seconds":5,
            "quality_tier":"motion_graphics_draft",
            "final_pass":False,
            "final_pass_reason":"ユーザー提供参考動画の最低ラインには、実写/生成ビジュアル素材＋ナレーション＋BGM/SFX＋編集演出が必要。無料外部編集で最終仕上げする設計。",
            "external_editors":[
                {"name":"CapCut","url":"https://www.capcut.com/editor","purpose":"無料枠で素材・字幕・音声・トランジションを仕上げる"},
                {"name":"Canva","url":"https://www.canva.com/video-editor/","purpose":"無料動画テンプレート・字幕・アニメーションで仕上げる"},
                {"name":"Adobe Express","url":"https://www.adobe.com/jp/express/feature/video/editor","purpose":"無料テンプレート・音声・アニメーションで仕上げる"}
            ],
            "assets":"generated-only local motion graphics; no external SaaS media",
            "quality":"1080x1920 draft validated by ffprobe plus decoded-frame visual check; final quality requires external editor finish",
            "visual_check":visual
        }
    finally:
        shutil.rmtree(work, ignore_errors=True)

def _visual_frame_check(path, total_seconds, samples=6):
    """Decode small RGB samples and reject a technically valid but visually blank MP4."""
    checks=[]
    for i in range(samples):
        ts=min(max(0.2, i*(total_seconds/max(samples,1))+0.2), max(0.2,total_seconds-0.2))
        p=subprocess.run([
            "ffmpeg","-v","error","-ss",str(ts),"-i",str(path),
            "-frames:v","1","-vf","scale=180:320","-f","rawvideo","-pix_fmt","rgb24","pipe:1"
        ],capture_output=True,timeout=30)
        raw=p.stdout
        if p.returncode!=0 or len(raw)<1000:
            return {"ok":False,"reason":"frame_decode_failed","sample":i+1}
        vals=list(raw)
        mean=sum(vals)/len(vals)
        mean_sq=sum(v*v for v in vals)/len(vals)
        variance=max(0.0,mean_sq-(mean*mean))
        checks.append({"sample":i+1,"mean":round(mean,1),"variance":round(variance,1)})
    visible=all(x["mean"]>8 and x["variance"]>25 for x in checks)
    return {"ok":visible,"samples":checks,"reason":"" if visible else "visually_blank_or_uniform"}
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
