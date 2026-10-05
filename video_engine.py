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

TTS_VOICE=os.environ.get("VIDEO_TTS_VOICE","ja-JP-NanamiNeural")
TTS_VERSION="7.2.8"

def _ensure_edge_tts():
    try:
        import edge_tts  # noqa: F401
        return True
    except Exception:
        try:
            subprocess.run(
                [sys.executable,"-m","pip","install",f"edge-tts=={TTS_VERSION}","--quiet"],
                capture_output=True,text=True,timeout=120,check=True
            )
            import edge_tts  # noqa: F401
            return True
        except Exception as e:
            print("TTS_INSTALL_ERROR",str(e)[:500],flush=True)
            return False

def _make_narration_text(command, chunks):
    parts=[_clean(command)[:70]]
    for x in chunks[:5]:
        s=_clean(x)
        if s and s not in parts:
            parts.append(s[:70])
    parts.append("今日できることから一つ始めましょう。保存して後で見直してください。")
    return "。".join(p.rstrip("。") for p in parts if p)+"。"

def _render_narration(text, output_path):
    if not _ensure_edge_tts():
        return {"ok":False,"reason":"edge_tts_unavailable"}
    try:
        p=subprocess.run(
            [sys.executable,"-m","edge_tts","--voice",TTS_VOICE,"--rate","+5%","--volume","+0%",
             "--text",text,"--write-media",str(output_path)],
            capture_output=True,text=True,timeout=90
        )
        if p.returncode!=0 or not Path(output_path).exists() or Path(output_path).stat().st_size<1000:
            return {"ok":False,"reason":"tts_failed","error":p.stderr[-1200:]}
        return {"ok":True,"voice":TTS_VOICE,"path":str(output_path)}
    except Exception as e:
        return {"ok":False,"reason":"tts_exception","error":str(e)}

def render(package, output_path=None):
    status = engine_status()
    if not status["available"]:
        return {"ok":False,"status":"ffmpeg_unavailable","engine":status}

    command = _clean(package.get("command",""))
    artifact = str(package.get("production_spec","") or package.get("artifact",""))
    chunks = _scene_text(artifact, command)
    title = _clean(package.get("title") or command or "秘密基地")
    test_mode = bool(package.get("test_mode", False))

    # Reference benchmark: 71.05 sec / 9:16 / dense original visuals / scene change
    # every 2-6 sec. The production render uses 12 x 5.9 sec = 70.8 sec,
    # 1080x1920, original vector illustrations, narration, synthetic BGM/SFX,
    # captions and motion. No third-party media is embedded.
    scene_count = 1 if test_mode else 12
    scene_duration = 1 if test_mode else 5.9
    total = scene_count * scene_duration
    if output_path is None:
        output_path = str(VIDEO_ROOT / ("video_" + uuid.uuid4().hex[:12] + ".mp4"))
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(prefix="sbvideo_"))
    segment_files = []

    def esc_xml(s):
        return (str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
                .replace('"',"&quot;").replace("'","&apos;"))

    def scene_svg(i):
        # Original, rights-safe visual language: no celebrities, characters,
        # logos, screenshots, stock photos, or copied frames.
        palettes = [
            ("#0a1024","#1d2d66","#67e8f9","#fbbf24"),
            ("#160c24","#5b246e","#fb7185","#fde68a"),
            ("#071c1a","#0d6b61","#34d399","#fef08a"),
            ("#1b1208","#754c18","#f59e0b","#fca5a5"),
            ("#0b1524","#164e63","#38bdf8","#a7f3d0"),
            ("#170d1e","#7c2d5a","#f472b6","#fde68a"),
            ("#08171c","#155e75","#22d3ee","#bef264"),
            ("#17120b","#854d0e","#facc15","#fb7185"),
            ("#0d1020","#3730a3","#a78bfa","#67e8f9"),
            ("#10151b","#334155","#94a3b8","#fbbf24"),
            ("#120d1e","#4c1d95","#c084fc","#5eead4"),
            ("#07151a","#14532d","#4ade80","#fde68a"),
        ]
        bg, panel, accent, accent2 = palettes[i % len(palettes)]
        common = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920">
        <defs>
          <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="{bg}"/><stop offset=".55" stop-color="{panel}"/><stop offset="1" stop-color="#05070d"/>
          </linearGradient>
          <linearGradient id="glass" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="#ffffff" stop-opacity=".30"/><stop offset="1" stop-color="#ffffff" stop-opacity=".05"/>
          </linearGradient>
          <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stop-color="{accent}"/><stop offset="1" stop-color="{accent2}"/>
          </linearGradient>
          <filter id="shadow"><feGaussianBlur stdDeviation="22"/></filter>
        </defs>
        <rect width="1080" height="1920" fill="url(#bg)"/>
        <circle cx="150" cy="260" r="270" fill="{accent}" opacity=".10" filter="url(#shadow)"/>
        <circle cx="930" cy="1250" r="360" fill="{accent2}" opacity=".09" filter="url(#shadow)"/>
        <path d="M-80 1540 Q 300 1280 610 1530 T 1160 1460 L1160 1960 L-80 1960Z" fill="#000" opacity=".18"/>
        '''
        # Different scene-specific object compositions.
        if i == 0:
            art = '''
            <rect x="150" y="420" width="780" height="900" rx="70" fill="#09101d" opacity=".88"/>
            <rect x="185" y="455" width="710" height="830" rx="55" fill="url(#glass)" stroke="#fff" stroke-opacity=".18" stroke-width="3"/>
            <rect x="250" y="540" width="580" height="470" rx="42" fill="#0b1220"/>
            <circle cx="540" cy="760" r="145" fill="url(#accent)" opacity=".9"/>
            <path d="M460 760 h160 M540 680 v160" stroke="#fff" stroke-width="34" stroke-linecap="round" opacity=".9"/>
            <rect x="285" y="1060" width="510" height="34" rx="17" fill="#fff" opacity=".16"/>
            <rect x="285" y="1060" width="360" height="34" rx="17" fill="{accent}"/>
            <rect x="285" y="1140" width="430" height="26" rx="13" fill="#fff" opacity=".10"/>
            <rect x="285" y="1210" width="300" height="26" rx="13" fill="#fff" opacity=".10"/>
            '''
        elif i == 1:
            art = '''
            <ellipse cx="540" cy="1320" rx="330" ry="95" fill="#000" opacity=".35"/>
            <path d="M330 650 Q540 560 750 650 L715 1220 Q540 1320 365 1220Z" fill="#d9a441" opacity=".95"/>
            <path d="M365 700 Q540 615 715 700" fill="none" stroke="#fff1b8" stroke-width="20" opacity=".55"/>
            <rect x="400" y="820" width="280" height="210" rx="30" fill="#1d2330"/>
            <circle cx="540" cy="925" r="70" fill="url(#accent)"/>
            <path d="M540 875 v100 M505 910 h70" stroke="#fff" stroke-width="18" stroke-linecap="round"/>
            <circle cx="280" cy="1010" r="52" fill="{accent}" opacity=".7"/><circle cx="800" cy="1060" r="42" fill="{accent2}" opacity=".7"/>
            '''
        elif i == 2:
            art = '''
            <rect x="170" y="520" width="740" height="760" rx="60" fill="#0b1020" stroke="#fff" stroke-opacity=".12" stroke-width="3"/>
            <rect x="220" y="590" width="640" height="130" rx="30" fill="#fff" opacity=".08"/>
            <rect x="260" y="625" width="210" height="42" rx="21" fill="{accent}" opacity=".85"/>
            <g fill="#fff" opacity=".10"><rect x="250" y="820" width="580" height="72" rx="20"/><rect x="250" y="930" width="430" height="72" rx="20"/><rect x="250" y="1040" width="520" height="72" rx="20"/></g>
            <path d="M260 1190 L390 1080 L520 1140 L650 950 L820 1010" fill="none" stroke="url(#accent)" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="390" cy="1080" r="24" fill="#fff"/><circle cx="650" cy="950" r="24" fill="#fff"/>
            '''
        elif i == 3:
            art = '''
            <rect x="160" y="480" width="760" height="840" rx="70" fill="#efe7d1"/>
            <rect x="205" y="525" width="670" height="120" rx="25" fill="{accent}" opacity=".85"/>
            <g fill="#2b241c" opacity=".9">
              <rect x="250" y="710" width="130" height="130" rx="22"/><rect x="475" y="710" width="130" height="130" rx="22"/><rect x="700" y="710" width="130" height="130" rx="22"/>
              <rect x="250" y="900" width="130" height="130" rx="22"/><rect x="475" y="900" width="130" height="130" rx="22"/><rect x="700" y="900" width="130" height="130" rx="22"/>
            </g>
            <path d="M280 1110 h520" stroke="#7b6b54" stroke-width="28" stroke-linecap="round"/>
            <path d="M280 1170 h380" stroke="#b0a18b" stroke-width="22" stroke-linecap="round"/>
            '''
        elif i == 4:
            art = '''
            <path d="M240 640 h600 l-70 590 q-230 120-460 0z" fill="#0a1722" stroke="{accent}" stroke-width="8"/>
            <path d="M260 670 h560 l-55 500 q-205 100-450 0z" fill="#101f2d"/>
            <circle cx="540" cy="875" r="130" fill="url(#accent)"/>
            <path d="M470 875 h140 M540 805 v140" stroke="#fff" stroke-width="30" stroke-linecap="round"/>
            <path d="M350 1260 Q540 1370 730 1260" fill="none" stroke="#fff" stroke-opacity=".15" stroke-width="26"/>
            <path d="M540 420 v130" stroke="#fff" stroke-opacity=".2" stroke-width="16"/>
            '''
        elif i == 5:
            art = '''
            <rect x="150" y="470" width="780" height="820" rx="70" fill="#0c1019"/>
            <rect x="205" y="525" width="670" height="710" rx="48" fill="#121a28"/>
            <circle cx="350" cy="720" r="90" fill="{accent}" opacity=".9"/>
            <circle cx="540" cy="720" r="90" fill="{accent2}" opacity=".85"/>
            <circle cx="730" cy="720" r="90" fill="#fff" opacity=".15"/>
            <rect x="270" y="880" width="540" height="38" rx="19" fill="#fff" opacity=".12"/>
            <rect x="270" y="880" width="410" height="38" rx="19" fill="{accent}"/>
            <rect x="270" y="970" width="470" height="28" rx="14" fill="#fff" opacity=".10"/>
            <rect x="270" y="1050" width="350" height="28" rx="14" fill="#fff" opacity=".10"/>
            <path d="M300 1160 l70 -80 70 55 90 -120 100 80 90 -140" fill="none" stroke="#fff" stroke-width="20" opacity=".8"/>
            '''
        elif i == 6:
            art = '''
            <rect x="130" y="620" width="820" height="600" rx="80" fill="#0b111b" stroke="#fff" stroke-opacity=".12" stroke-width="4"/>
            <path d="M210 1100 L330 1010 L450 1060 L580 820 L700 900 L860 700" fill="none" stroke="url(#accent)" stroke-width="38" stroke-linecap="round" stroke-linejoin="round"/>
            <g fill="#fff"><circle cx="210" cy="1100" r="22"/><circle cx="330" cy="1010" r="22"/><circle cx="450" cy="1060" r="22"/><circle cx="580" cy="820" r="22"/><circle cx="700" cy="900" r="22"/><circle cx="860" cy="700" r="22"/></g>
            <rect x="210" y="1280" width="650" height="30" rx="15" fill="#fff" opacity=".12"/>
            '''
        elif i == 7:
            art = '''
            <ellipse cx="540" cy="1330" rx="310" ry="85" fill="#000" opacity=".35"/>
            <path d="M300 670 h480 l100 500 -110 90 H310 l-110-90z" fill="#e8f0f7" opacity=".95"/>
            <path d="M300 670 h480 l70 350 H230z" fill="#c7d6e4"/>
            <circle cx="380" cy="820" r="72" fill="{accent}"/><circle cx="700" cy="820" r="72" fill="{accent2}"/>
            <rect x="330" y="960" width="420" height="42" rx="21" fill="#344054" opacity=".7"/>
            <rect x="330" y="1030" width="300" height="32" rx="16" fill="#344054" opacity=".35"/>
            <path d="M300 1210 h480" stroke="#fff" stroke-width="26" opacity=".25"/>
            '''
        elif i == 8:
            art = '''
            <rect x="155" y="520" width="770" height="780" rx="75" fill="#0b0f1c"/>
            <rect x="215" y="580" width="650" height="120" rx="30" fill="{accent}" opacity=".18"/>
            <g fill="#fff" opacity=".13"><rect x="250" y="770" width="560" height="46" rx="23"/><rect x="250" y="870" width="480" height="46" rx="23"/><rect x="250" y="970" width="530" height="46" rx="23"/></g>
            <g fill="url(#accent)"><circle cx="285" cy="792" r="22"/><circle cx="285" cy="892" r="22"/><circle cx="285" cy="992" r="22"/></g>
            <path d="M420 1130 h280" stroke="#fff" stroke-width="26" stroke-linecap="round" opacity=".7"/>
            '''
        elif i == 9:
            art = '''
            <rect x="120" y="560" width="390" height="650" rx="45" fill="#141a28" stroke="#ef4444" stroke-opacity=".6" stroke-width="8"/>
            <rect x="570" y="560" width="390" height="650" rx="45" fill="#14261f" stroke="#4ade80" stroke-opacity=".7" stroke-width="8"/>
            <g fill="#fff" opacity=".12"><rect x="180" y="660" width="270" height="38" rx="19"/><rect x="180" y="740" width="200" height="38" rx="19"/><rect x="630" y="660" width="270" height="38" rx="19"/><rect x="630" y="740" width="220" height="38" rx="19"/></g>
            <path d="M220 1050 l70 70 160-180" fill="none" stroke="#ef4444" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M670 1050 l70 70 160-180" fill="none" stroke="#4ade80" stroke-width="30" stroke-linecap="round" stroke-linejoin="round"/>
            '''
        elif i == 10:
            art = '''
            <path d="M240 1160 L540 620 L840 1160 Z" fill="#0d1321" stroke="{accent}" stroke-width="7"/>
            <path d="M300 1100 L420 900 L510 980 L620 780 L780 1080" fill="none" stroke="url(#accent)" stroke-width="34" stroke-linecap="round" stroke-linejoin="round"/>
            <circle cx="420" cy="900" r="22" fill="#fff"/><circle cx="620" cy="780" r="22" fill="#fff"/>
            <rect x="370" y="1240" width="340" height="34" rx="17" fill="#fff" opacity=".15"/>
            '''
        else:
            art = '''
            <ellipse cx="540" cy="1270" rx="330" ry="90" fill="#000" opacity=".35"/>
            <path d="M270 670 Q540 540 810 670 L760 1190 Q540 1300 320 1190Z" fill="url(#accent)" opacity=".9"/>
            <path d="M340 720 Q540 620 740 720" fill="none" stroke="#fff" stroke-width="20" opacity=".45"/>
            <circle cx="540" cy="900" r="125" fill="#fff" opacity=".18"/>
            <path d="M460 900 l55 55 115-140" fill="none" stroke="#fff" stroke-width="34" stroke-linecap="round" stroke-linejoin="round"/>
            <path d="M330 1110 h420" stroke="#fff" stroke-opacity=".35" stroke-width="24" stroke-linecap="round"/>
            '''
        return common + art + "</svg>"

    try:
        font = _font_file()
        if not font:
            return {"ok":False,"status":"japanese_font_unavailable","engine":status}

        title_file = work / "title.txt"
        _write_text(title_file, _display_lines(title, max_chars=19, max_lines=2))

        colors = ["#0d1220","#17122b","#101c22","#21151b","#111d18","#181325",
                  "#101a27","#21170e","#14132a","#121820","#1a1224","#0d1b16"]
        accents = ["#67e8f9","#fb7185","#34d399","#f59e0b","#38bdf8","#f472b6",
                   "#22d3ee","#facc15","#a78bfa","#94a3b8","#c084fc","#4ade80"]
        kickers = ["まず結論","ムダを発見","数字で整理","比較して判断","仕組みを確認",
                   "優先順位を決める","変化を見える化","具体策に落とす","続けやすくする",
                   "Before → After","今日やること","保存して実践"]

        for i in range(scene_count):
            body = chunks[i % len(chunks)]
            body_file = work / f"body_{i}.txt"
            kicker_file = work / f"kicker_{i}.txt"
            _write_text(body_file, _display_lines(body, max_chars=17, max_lines=4))
            _write_text(kicker_file, kickers[i % len(kickers)])

            svg = work / f"scene_{i}.svg"
            svg.write_text(scene_svg(i), encoding="utf-8")
            seg = work / f"seg_{i}.mp4"

            # Each scene is an original illustrated composition with slow
            # camera movement, subtle light motion and fade transitions.
            zoom_expr = "min(zoom+0.0012,1.055)" if i % 2 == 0 else "max(zoom-0.0007,1.0)"
            x_expr = "iw/2-(iw/zoom/2)+sin(on*0.025)*18"
            y_expr = "ih/2-(ih/zoom/2)+cos(on*0.021)*24"
            vf = (
                f"scale=1080:1920,"
                f"zoompan=z='{zoom_expr}':x='{x_expr}':y='{y_expr}':d={int(scene_duration*30)}:s=1080x1920:fps=30,"
                f"eq=contrast=1.04:saturation=1.08,"
                f"fade=t=in:st=0:d=0.32,fade=t=out:st={max(scene_duration-0.36,0.5):.2f}:d=0.36,"
                f"drawbox=x=0:y=0:w=1080:h=1920:color=black@0.08:t=fill,"
                f"drawbox=x=52:y=72:w=976:h=8:color={accents[i]}@0.88:t=fill,"
                f"drawbox=x=72:y=1450:w=936:h=300:color=black@0.56:t=fill,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':text='SCENE {i+1}/{scene_count}':"
                f"fontcolor={accents[i]}:fontsize=31:borderw=2:bordercolor=black:x=78:y=96,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':textfile='{_esc_filter_path(kicker_file)}':"
                f"fontcolor=white:fontsize=34:borderw=3:bordercolor=black:x=78:y=145,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':textfile='{_esc_filter_path(title_file)}':"
                f"fontcolor=white:fontsize=56:borderw=5:bordercolor=black:x=(w-text_w)/2:y=190,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':textfile='{_esc_filter_path(body_file)}':"
                f"fontcolor=white:fontsize=54:borderw=5:bordercolor=black:x=(w-text_w)/2:y=1510:line_spacing=18,"
                f"drawtext=fontfile='{_esc_filter_path(font)}':text='保存して後で見直す':"
                f"fontcolor=white:fontsize=31:borderw=3:bordercolor=black:x=(w-text_w)/2:y=1690"
            )
            cmd=[
                "ffmpeg","-y","-loop","1","-i",str(svg),
                "-t",str(scene_duration),"-vf",vf,
                "-an","-c:v","libx264","-preset","ultrafast","-threads","1",
                "-pix_fmt","yuv420p","-r","30",str(seg)
            ]
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=150)
            if p.returncode!=0:
                return {"ok":False,"status":"scene_render_error","engine":status,"scene":i+1,"error":p.stderr[-1800:]}

            segment_files.append(seg)

        concat = work / "concat.txt"
        concat.write_text("".join(f"file '{p}'\n" for p in segment_files), encoding="utf-8")

        # Rights-safe synthetic BGM and per-scene SFX. These are generated
        # tones, not copyrighted recordings.
        audio = work / "audio.wav"
        sfx = work / "sfx.wav"
        ap=subprocess.run([
            "ffmpeg","-y",
            "-f","lavfi","-i",f"sine=frequency=196:sample_rate=48000:duration={total}",
            "-f","lavfi","-i",f"sine=frequency=294:sample_rate=48000:duration={total}",
            "-f","lavfi","-i",f"sine=frequency=392:sample_rate=48000:duration={total}",
            "-filter_complex","[0:a]volume=0.040[a0];[1:a]volume=0.025[a1];[2:a]volume=0.016[a2];[a0][a1][a2]amix=inputs=3:normalize=0,afade=t=in:st=0:d=1.0,afade=t=out:st="+str(max(0,total-2))+":d=2",
            "-c:a","pcm_s16le",str(audio)
        ],capture_output=True,text=True,timeout=60)
        if ap.returncode!=0:
            return {"ok":False,"status":"audio_render_error","engine":status,"error":ap.stderr[-1000:]}

        sp=subprocess.run([
            "ffmpeg","-y","-f","lavfi","-i",
            f"aevalsrc=0.075*sin(2*PI*880*t)*if(lt(mod(t\\,{scene_duration})\\,0.18)\\,1\\,0):s=48000:d={total}",
            "-c:a","pcm_s16le",str(sfx)
        ],capture_output=True,text=True,timeout=60)
        if sp.returncode!=0:
            return {"ok":False,"status":"sfx_render_error","engine":status,"error":sp.stderr[-1000:]}

        narration = work / "narration.mp3"
        narration_text = _make_narration_text(command,chunks)
        tts_result = _render_narration(narration_text,narration)

        if tts_result.get("ok"):
            p=subprocess.run([
                "ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),
                "-i",str(narration),"-i",str(audio),"-i",str(sfx),
                "-filter_complex",
                "[1:a]volume=1.0[voice];[2:a]volume=0.16[music];[3:a]volume=0.55[fx];"
                "[voice][music][fx]amix=inputs=3:duration=longest:normalize=0,"
                "loudnorm=I=-15:TP=-1.5:LRA=9[aout]",
                "-map","0:v:0","-map","[aout]",
                "-c:v","libx264","-preset","ultrafast","-threads","1","-pix_fmt","yuv420p",
                "-r","30","-c:a","aac","-b:a","128k","-threads","1","-shortest",
                "-movflags","+faststart",str(out)
            ],capture_output=True,text=True,timeout=300)
        else:
            p=subprocess.run([
                "ffmpeg","-y","-f","concat","-safe","0","-i",str(concat),
                "-i",str(audio),"-i",str(sfx),
                "-filter_complex",
                "[1:a]volume=0.16[music];[2:a]volume=0.55[fx];"
                "[music][fx]amix=inputs=2:duration=longest:normalize=0,loudnorm=I=-15:TP=-1.5:LRA=9[aout]",
                "-map","0:v:0","-map","[aout]",
                "-c:v","libx264","-preset","ultrafast","-threads","1","-pix_fmt","yuv420p",
                "-r","30","-c:a","aac","-b:a","128k","-threads","1","-shortest",
                "-movflags","+faststart",str(out)
            ],capture_output=True,text=True,timeout=300)

        if p.returncode!=0:
            return {"ok":False,"status":"final_mux_error","engine":status,"error":p.stderr[-1800:]}

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
        valid=(video.get("codec_name")=="h264" and video.get("width")==1080 and video.get("height")==1920
               and duration>=(0.9 if test_mode else 65) and audio_stream.get("codec_name")=="aac")
        if not valid:
            return {"ok":False,"status":"validation_failed","engine":status,"path":str(out),"probe":info}

        visual=_visual_frame_check(out,duration,scene_count)
        if not visual.get("ok"):
            return {"ok":False,"status":"visual_validation_failed","engine":status,"path":str(out),"probe":info,"visual_check":visual}

        return {
            "ok":True,"status":"rendered","engine":status,"path":str(out),
            "filename":out.name,"duration_seconds":round(duration,2),
            "format":{"width":1080,"height":1920,"fps":30,"container":"mp4","video_codec":"h264","audio_codec":"aac"},
            "scene_count":scene_count,"scene_change_seconds":round(scene_duration,1),
            "quality_tier":("cinematic_original_visuals_with_narration" if tts_result.get("ok") else "cinematic_original_visuals_synthetic_audio"),
            "final_pass":False,
            "final_pass_reason":"添付参考動画の特性（約71秒、9:16、高密度のオリジナルビジュアル、2〜6秒の変化、白字幕＋黒フチ、ナレーション、BGM/SFX）を最低品質基準として実装。最終合格は人間確認を必須とする。",
            "benchmark":{"reference_duration_seconds":71.05,"reference_resolution":"512x910","target_resolution":"1080x1920","target_scene_change_seconds":"2-6","visual_policy":"original_generated/vector only","people_policy":"no identifiable people"},
            "audio_mode":("neural_narration_plus_bgm_sfx" if tts_result.get("ok") else "synthetic_bgm_sfx_fallback"),
            "narration_voice":tts_result.get("voice") if tts_result.get("ok") else None,
            "narration_verified":bool(tts_result.get("ok")),
            "narration_error":tts_result.get("error") if not tts_result.get("ok") else None,
            "sfx":"synthetic per-scene cue",
            "rights_safe_assets":True,
            "external_editors":[
                {"name":"CapCut","url":"https://www.capcut.com/editor","purpose":"任意の人間仕上げ。素材・字幕・音声・トランジション"},
                {"name":"Canva","url":"https://www.canva.com/video-editor/","purpose":"任意の人間仕上げ。テンプレート・字幕・アニメーション"},
                {"name":"Adobe Express","url":"https://www.adobe.com/jp/express/feature/video/editor","purpose":"任意の人間仕上げ。テンプレート・音声・アニメーション"}
            ],
            "assets":"original vector illustrations generated locally; no external media",
            "quality":"reference-driven 9:16 render with original visual scenes, motion, captions, neural narration, synthetic BGM/SFX and technical validation",
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
