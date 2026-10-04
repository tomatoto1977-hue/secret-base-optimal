import json, os, shutil, subprocess, tempfile
from pathlib import Path

def engine_status():
    return {"provider":"ffmpeg","available":bool(shutil.which("ffmpeg")),"paid":False,"external_saas":False}

def render(package, output_path=None):
    status=engine_status()
    if not status["available"]:
        return {"ok":False,"status":"ffmpeg_unavailable","engine":status}
    if not output_path:
        fd,path=tempfile.mkstemp(suffix=".mp4"); os.close(fd); output_path=path
    duration=float(package.get("duration_seconds",30))
    duration=max(1,min(duration,180))
    text=str(package.get("title") or package.get("command") or "秘密基地")
    # Generate a deterministic 9:16 MP4 card. Real visual assets can be supplied later through the same adapter contract.
    safe=text.replace(":"," ").replace("'","")
    vf=f"scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    cmd=["ffmpeg","-y","-f","lavfi","-i","color=c=0xF7F1E8:s=1080x1920:r=30","-t",str(duration),
         "-vf",vf,"-c:v","libx264","-pix_fmt","yuv420p","-movflags","+faststart",output_path]
    try:
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=300)
        if p.returncode!=0:
            return {"ok":False,"status":"ffmpeg_error","engine":status,"error":p.stderr[-1000:]}
        return {"ok":True,"status":"rendered","engine":status,"path":output_path,"format":{"width":1080,"height":1920,"fps":30,"container":"mp4"}}
    except Exception as e:
        return {"ok":False,"status":"render_exception","engine":status,"error":str(e)}
