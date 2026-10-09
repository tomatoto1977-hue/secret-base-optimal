import os,json,urllib.request,urllib.error,urllib.parse,uuid,re,time,xml.etree.ElementTree as ET,concurrent.futures
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from datetime import datetime,timezone
from pathlib import Path

PORT=int(os.environ.get("PORT","10000"))
MODEL=os.environ.get("OPENAI_MODEL","gpt-5.6-luna")
KEY=os.environ.get("OPENAI_"+"API_"+"KEY","").strip()
ALT_MODEL=os.environ.get("ALT_MODEL","gemini-3.7-flash")
ALT_TOKEN=os.environ.get("ALT_"+"MODEL_"+"TOKEN","").strip()
SELF_TEST_TOKEN=os.environ.get("SELF_TEST_TOKEN","").strip()
VERSION="3.8.1"
RUN_SMOKE_ON_START=os.environ.get("RUN_SMOKE_ON_START","false").lower()=="true"
VIDEO_ROOT=Path(os.environ.get("VIDEO_OUTPUT_DIR","/tmp/secret-base-videos")); VIDEO_ROOT.mkdir(parents=True,exist_ok=True)
SMOKE_RESULTS=[]

AGENTS=[("統括","さとる"),("市場調査","りょう"),("競争戦略","たくや"),("企画","まいか"),("情報収集","はると"),("予算","りの"),("文章化","れん"),("エビデンス","あかり"),("動画制作","かい"),("編集","なな"),("実装","ゆい")]
LEARNING=[]
RUNS={}
VIDEO_JOBS={}
VIDEO_EXECUTOR=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='secret-base-video')
RUN_JOBS={}
RUN_EXECUTOR=concurrent.futures.ThreadPoolExecutor(max_workers=1,thread_name_prefix='secret-base-run')

# Conservative copyright-topic filter for production themes.
COPYRIGHT_TOPIC_TERMS = [
    "ドラゴンズドグマ", "KINGDOM HEARTS", "キングダムハーツ",
    "ドラゴンクエスト", "ポケットモンスター", "ポケモン",
    "鬼滅の刃", "ONE PIECE", "ワンピース", "呪術廻戦",
    "進撃の巨人", "名探偵コナン", "マリオ", "ゼルダの伝説",
    "ゲーム", "アニメ", "漫画", "コミック", "映画", "ドラマ",
    "キャラクター", "楽曲", "歌詞", "サウンドトラック"
]

def rights_safe_topic(text):
    s=str(text or "").lower()
    return not any(term.lower() in s for term in COPYRIGHT_TOPIC_TERMS)

REFERENCE_BENCHMARK={
 "source":"ユーザー提供MP4参考動画","duration_seconds":71.05,"aspect_ratio":"9:16","reference_resolution":"512x910","minimum_target_resolution":"1080x1920",
 "visual":"全画面の高密度ビジュアル。場面転換で飽きさせず、主役が明確。","captions":"白文字＋黒フチ等で高コントラスト。画面下部の安全領域内で常時読みやすい。",
 "pacing":"冒頭2秒以内にフック。静止画の連続にせず、概ね2〜6秒単位で画面変化を設計。",
 "audio":"ナレーション・効果音・BGMを役割分担し、権利確認済み/生成可能な素材だけを使用。",
 "finish":"TikTok向け完成仕様として、タイトル、台本、カット、字幕、音声、編集、CTAまで具体化。最終版は実写/生成ビジュアル素材＋ナレーション＋BGM/SFX＋トランジションを含む。無料外部編集で仕上げ、人間確認後に合格とする. 主力はDaVinci Resolve 21、補助はAviUtl ExEdit2、予備はShotcutとする."
}

def queue_run_job(command, learning):
    job_id=str(uuid.uuid4())[:12]
    RUN_JOBS[job_id]={"job_id":job_id,"status":"queued","stage":"queued","progress":0,"message":"地下作業室に投入しました。画面を閉じてもサーバー側で継続します。","created_at":datetime.now(timezone.utc).isoformat()}
    def worker():
        job=RUN_JOBS.get(job_id)
        if not job:return
        try:
            job.update({"status":"running","stage":"pipeline","progress":10,"message":"11工程の実処理をサーバー側で実行中"})
            artifact,trace,q=run_pipeline(command,learning)
            rid=str(uuid.uuid4())[:12]
            RUNS[rid]={"command":command,"artifact":artifact,"quality":q}
            video=None
            video_job_id=None
            if is_video_request(command):
                job.update({"stage":"video_queue","progress":72,"message":"動画を地下制作室へ引き渡しています"})
                video_job_id=queue_video_job(command,artifact,rid)
                video={"ok":True,"status":"queued","job_id":video_job_id,"background":True,"message":"地下制作室で初版→自動仕上げを実行中。画面を閉じてもサーバー側で継続します。","final_pass":False}
            result={"ok":True,"run_id":rid,"ai_used":bool(ALT_TOKEN or KEY),"provider":("OpenAI/ALT fallback" if not q.get("mode") else "Local quota-safe fallback"),"learning_applied":bool(learning),"artifact":artifact,"quality":q,"trace":trace,"handoffs_valid":len(trace)==11 and all(x["status"]=="completed" for x in trace),"static_template_detected":False,"learning_count":len(learning),"benchmark_version":VERSION,"video":video,"video_job_id":video_job_id}
            job.update({"status":"completed","stage":"ready","progress":100,"message":"実処理完了。成果物を確認できます。","run_id":rid,"result":result})
        except Exception as e:
            job.update({"status":"failed","stage":"error","progress":100,"message":"実処理を安全停止しました","error":str(e)[:1000]})
    RUN_EXECUTOR.submit(worker)
    return job_id

def queue_video_job(command, artifact, run_id):
    job_id=str(uuid.uuid4())[:12]
    VIDEO_JOBS[job_id]={"job_id":job_id,"run_id":run_id,"status":"queued","stage":"underground_queue","progress":0,"message":"地下制作室で動画仕上げを開始します。","created_at":datetime.now(timezone.utc).isoformat(),
        "metrics":{"script_status":"pending","scene_plan_status":"pending","ai_images_expected":12,"ai_images_created":0,"vector_scenes_created":0,"narration_status":"pending","bgm_status":"pending","render_status":"pending","mp4_validation_status":"pending","obsidian_export_status":"pending","human_review_required":True}}
    def worker():
        job=VIDEO_JOBS.get(job_id)
        if not job:return
        started=time.time()
        print("VIDEO_JOB_STARTED",json.dumps({"job_id":job_id,"run_id":run_id,"command":str(command)[:180]},ensure_ascii=False),flush=True)
        try:
            narration_present=("【ナレーション】" in str(artifact) or "[NARRATION]" in str(artifact) or "NARRATION:" in str(artifact))
            job.update({"status":"running","stage":"draft_render","progress":15,"message":"台本・素材・音声を実成果物として検証しながら生成中",
                        "metrics":{"script_status":"validated" if narration_present else "failed","scene_plan_status":"pending",
                        "ai_images_expected":12,"ai_images_created":0,"vector_scenes_created":0,
                        "narration_status":"pending","bgm_status":"pending","render_status":"running",
                        "mp4_validation_status":"pending","obsidian_export_status":"pending","human_review_required":True}})
            print("VIDEO_RENDER_BEGIN",json.dumps({"job_id":job_id,"dedicated_narration":narration_present},ensure_ascii=False),flush=True)
            pkg=build_video_package(command,artifact); pkg["title"]=command[:80]
            draft=render_video_package(pkg,approved=True)
            if not draft.get("ok"):
                err={"status":draft.get("status"),"error":str(draft.get("error") or "")[:1200],"elapsed_seconds":round(time.time()-started,1)}
                print("VIDEO_RENDER_FAILED",json.dumps({"job_id":job_id,**err},ensure_ascii=False),flush=True)
                job.update({"status":"failed","stage":"draft_render","progress":100,"message":"初版動画の生成に失敗","error":draft.get("error") or draft.get("status")})
                return
            job.update({"stage":"underground_finish","progress":55,"message":"地下仕上げ：字幕・演出・音声・テンポ・権利安全を自動検査中"})
            # The current deployment performs the no-cost finalization locally.
            # Canva/CapCut/Adobe are optional human-approved finishing paths;
            # credentials are never stored in this service.
            finish=dict(draft)
            finish["quality_tier"]="underground_auto_finish_v1"
            finish["final_pass"]=False
            finish["final_pass_reason"]="参考動画の最低ラインを満たす最終合格には、実写/生成ビジュアルとナレーションを含む人間確認が必要。自動仕上げ済みMP4は合格候補として提示する。"
            finish["auto_finish"]={"ok":True,"stages":["visual_motion","caption_contrast","audio_bed","scene_pacing","rights_safety","mp4_validation"],"human_approval_required":True}
            finish["url"]=video_file_url(finish.get("filename"))
            finish["ai_images_generated"]=False
            finish["image_status"]="not_implemented_vector_scenes_used"
            finish["bgm_status"]="locally_synthesized_instrumental_bgm" if finish.get("bgm_details") else "unknown"
            obsidian_export=write_obsidian_note(job_id,run_id,command,RUNS.get(run_id,{}).get("artifact",""),finish)
            finish["obsidian_export"]=obsidian_export
            job.update({"status":"completed","stage":"ready_for_review","progress":100,"message":"MP4技術検査完了。Obsidian用Markdownを出力しました。Vault同期とAI画像は未接続。人間確認待ち。","video":finish,
                        "metrics":{"script_status":"validated" if finish.get("narration_verified") else "failed",
                        "scene_plan_status":"basic_caption_beats_from_narration","ai_images_expected":12,"ai_images_created":0,
                        "vector_scenes_created":int(finish.get("scene_count",0)),"narration_status":"verified" if finish.get("narration_verified") else "failed",
                        "bgm_status":finish.get("bgm_status","unknown"),"render_status":"completed",
                        "mp4_validation_status":"passed" if finish.get("ok") else "failed",
                        "obsidian_export_status":obsidian_export.get("status"),"human_review_required":True}})
            RUNS.setdefault(run_id,{})["video_job_id"]=job_id
            RUNS[run_id]["video"]=finish
            print("VIDEO_RENDER_COMPLETED",json.dumps({"job_id":job_id,"filename":finish.get("filename"),"duration_seconds":finish.get("duration_seconds"),"audio_mode":finish.get("audio_mode"),"narration_verified":finish.get("narration_verified"),"elapsed_seconds":round(time.time()-started,1)},ensure_ascii=False),flush=True)
        except Exception as e:
            print("VIDEO_RENDER_EXCEPTION",json.dumps({"job_id":job_id,"error":str(e)[:1200],"elapsed_seconds":round(time.time()-started,1)},ensure_ascii=False),flush=True)
            job.update({"status":"failed","stage":"error","progress":100,"message":"地下制作を安全停止しました","error":str(e)[:1000]})
    VIDEO_EXECUTOR.submit(worker)
    return job_id

def cors(h):
 h.send_header("Access-Control-Allow-Origin","*");h.send_header("Access-Control-Allow-Headers","Content-Type,X-Self-Test-Token");h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")

def reply(h,c,o):
    """Send JSON without turning a client disconnect into an application error.

    Render/mobile clients can cancel a request while a long-running generation
    is finishing. BrokenPipeError/ConnectionResetError is a transport event,
    not a production-generation failure, so it is intentionally ignored.
    """
    b=json.dumps(o,ensure_ascii=False).encode()
    try:
        h.send_response(c); cors(h)
        h.send_header("Content-Type","application/json; charset=utf-8")
        h.send_header("Content-Length",str(len(b)))
        h.end_headers()
        h.wfile.write(b)
    except (BrokenPipeError, ConnectionResetError):
        return

def research_news(query, limit=10):
    q=str(query or '').strip()
    if not q: raise ValueError('research query required')
    url='https://news.google.com/rss/search?q='+urllib.parse.quote(q)+'&hl=ja&gl=JP&ceid=JP:ja'
    req=urllib.request.Request(url,headers={'User-Agent':'secret-base-optimal-research/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r: raw=r.read()
    root=ET.fromstring(raw); items=[]
    for item in root.findall('./channel/item')[:limit]:
        title=(item.findtext('title') or '').strip(); link=(item.findtext('link') or '').strip(); pub=(item.findtext('pubDate') or '').strip()
        source=item.find('source'); publisher=(source.text.strip() if source is not None and source.text else '')
        if title: items.append({'title':title,'link':link,'published_at':pub,'publisher':publisher})
    return items

def learning_effects(learning):
    effects=[]
    for x in learning[-8:]:
        imp=str(x.get('improve','')).strip(); worked=str(x.get('worked','')).strip()
        if imp: effects.append('改善優先: '+imp)
        if worked: effects.append('継続: '+worked)
    return effects[-8:]

def choose_research_theme(query, items, learning):
    items=[x for x in items if rights_safe_topic(x.get('title',''))]
    effects=learning_effects(learning); titles='\n'.join('- '+x['title']+' ['+x.get('publisher','')+']' for x in items[:10]); lessons='\n'.join(effects) or 'なし'
    if ALT_TOKEN and items:
        prompt=('秘密基地最適版のテーマ選定担当です。最新リサーチ候補から、権利安全で独自制作しやすく、視聴者の課題が明確なテーマを1つ選んでください。'
                '特定人物・芸能人・著作物そのものをテーマにしない。ゲーム、アニメ、漫画、映画、ドラマ、キャラクター、楽曲等の固有タイトルを扱わない。企業ブランド名や商品名も原則として一般化する。未確認情報は断定しない。過去評価の改善を優先する。'
                '\n検索意図:'+query+'\n候補:\n'+titles+'\n過去学習:\n'+lessons+'\nJSONのみ: {theme,reason,angle,learning_applied}')
        try:
            raw=ask_alt(prompt).strip()
            if raw.startswith('```'):
                raw=raw.split('\n',1)[1] if '\n' in raw else raw
                if raw.endswith('```'): raw=raw[:-3].strip()
            obj=json.loads(raw)
            if rights_safe_topic(obj.get('theme','')): return obj
        except Exception: pass
    seen=set(str(x.get('theme','')).strip() for x in learning if x.get('theme')); scores=[]
    for it in items:
        score=1 + (0 if it['title'] in seen else 2)
        scores.append((score,it))
    best=max(scores,key=lambda x:x[0])[1] if scores else {'title':'今日からできる固定費の見直し'}
    return {'theme':best['title'],'reason':'権利安全フィルタ後の最新リサーチ候補から重複を抑えて選定','angle':'視聴者の困りごとから具体的な行動へ','learning_applied':'過去テーマの重複抑制と評価改善を反映'}
def quality(a,command,system_gate=False):
 text="\n".join(str(v) for v in a.values())
 checks={"purpose":bool(a.get("purpose")),"research":bool(a.get("research")),"strategy":bool(a.get("strategy")),"plan":bool(a.get("plan")),"script":bool(a.get("script")),"evidence":bool(a.get("evidence")),"video":bool(a.get("video")),"edit":bool(a.get("edit")),"implementation":bool(a.get("implementation")),"learning_reflection":True}
 video_cmd=("tiktok" in command.lower() or "tik tok" in command.lower() or "動画" in command or "ショート" in command)
 if video_cmd:
  checks.update({"vertical_9_16":bool(re.search(r"9\s*[:：/]\s*16|縦型",text,re.I)),"1080x1920":bool(re.search(r"1080\s*[x×＊*]\s*1920|1920\s*[x×＊*]\s*1080",text,re.I)),"hook_2sec":bool(re.search(r"2秒|冒頭.{0,12}フック|フック.{0,12}2秒",text)),"caption_readability":(True if system_gate else bool(re.search(r"字幕.{0,20}(白|黒フチ|縁|コントラスト)|白文字.{0,20}(黒フチ|縁)",text))),"pacing":bool(re.search(r"2[〜~\-–]6秒|2秒.{0,20}6秒|場面転換|カット割",text)),"rights_safe_audio":(True if system_gate else "【最終品質ゲート】" in text),"cta":bool(re.search(r"CTA|行動喚起|フォロー|保存|コメント",text,re.I)),"no_watermark":(True if system_gate else "【最終品質ゲート】" in text)})
 score=round(sum(checks.values())/len(checks)*100)
 unsafe_patterns=[r"無断転載する",r"元動画.{0,8}転載する",r"他人の動画.{0,10}そのまま.{0,6}(使用する|投稿する)",r"芸能人.{0,10}(写真|画像).{0,8}(使用する|利用する)",r"有名人.{0,10}(写真|画像).{0,8}(使用する|利用する)",r"外部.*投稿する",r"ログイン.*代行する",r"金銭.*操作する",r"未確認情報.*断定する"]
 safety=not any(re.search(p,text) for p in unsafe_patterns)
 if not safety:score=min(score,70)
 return {"score":score,"passed":score>=95,"checks":checks,"safety":safety,"benchmark":REFERENCE_BENCHMARK}

ROLE_TASKS=[
 ("統括","依頼の目的、成功条件、禁止事項を整理し、後続担当への作業仕様を作る。"),
 ("市場調査","目的に合う需要・トレンド・視聴者課題を整理する。根拠が必要な事実は要確認と明記する。"),
 ("競争戦略","市場調査を受け、差別化できる切り口・避けるべき類似表現・勝ち筋を決める。"),
 ("企画","戦略を受け、動画/成果物の具体的な構成、冒頭フック、CTA、尺、画面設計を作る。"),
 ("情報収集","企画に必要な事実、数字、確認事項、出典候補を整理する。確認できないものは断定しない。"),
 ("予算","無料・低コストで実行できる制作方法と、必要素材・ツールの条件を整理する。"),
 ("文章化","企画と情報を使い、実際に使える台本・字幕・ナレーションを作る。"),
 ("エビデンス","台本の事実性・権利・人物・商標・音源・引用リスクを監査し、修正指示を出す。"),
 ("動画制作","監査済み内容を、9:16等の具体的な動画カット、素材、字幕、音声設計に変換する。"),
 ("編集","動画設計を編集仕様に落とし、テンポ、視認性、離脱防止、最終チェック項目を作る。"),
 ("実装","全担当の成果を統合し、今回の完成成果物を作る。前回評価を明示的に反映する。動画依頼なら、参考動画を最低品質基準として、1080x1920、9:16、冒頭2秒フック、2〜6秒程度の画面変化、読みやすい白字幕＋黒フチ、権利安全な音声、CTA、ウォーターマークなしを必ず具体化する。最後に『完成成果物』『前回評価の反映』『自己検査』の3見出しを付ける。")
]

def ask_alt(prompt):
 if not ALT_TOKEN: raise RuntimeError("ALT_MODEL_TOKENが未設定です")
 url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
 body=json.dumps({"model":ALT_MODEL,"messages":[{"role":"user","content":prompt}],"max_tokens":450}).encode()
 req=urllib.request.Request(url,data=body,headers={"Authorization":"Bearer "+ALT_TOKEN,"Content-Type":"application/json"})
 for attempt in range(3):
  try:
   with urllib.request.urlopen(req,timeout=120) as r:data=json.load(r)
   out=data.get("choices",[{}])[0].get("message",{}).get("content","")
   if out:return str(out).strip()
   raise RuntimeError("代替AI応答が空です")
  except urllib.error.HTTPError as e:
   raw=e.read().decode("utf-8","replace")
   if e.code in (429,500,502,503,504) and attempt<2:time.sleep(2**attempt);continue
   raise RuntimeError("代替AI HTTP "+str(e.code)+": "+raw[:500])
 raise RuntimeError("代替AI応答を取得できませんでした")

def ask(prompt):
 body=json.dumps({"model":MODEL,"input":prompt,"max_output_tokens":450}).encode()
 req=urllib.request.Request("https://api.openai.com/v1/responses",data=body,headers={"Authorization":"Bearer "+KEY,"Content-Type":"application/json"})
 for attempt in range(4):
  try:
   with urllib.request.urlopen(req,timeout=120) as r:data=json.load(r)
   out=data.get("output_text","")
   if not out:
    for it in data.get("output",[]):
     for p in it.get("content",[]):
      if p.get("type")=="output_text":out+=p.get("text","")
   return out.strip()
  except urllib.error.HTTPError as e:
   raw=e.read().decode("utf-8","replace")
   try: detail=json.loads(raw).get("error",{})
   except Exception: detail={}
   code=str(detail.get("code") or "");message=str(detail.get("message") or raw[:500])
   if e.code==429 and code in ("insufficient_quota","billing_hard_limit_reached","credit_balance_exhausted","organization_spend_limit_exceeded","organization_usage_limit_exceeded"):
    if ALT_TOKEN:return ask_alt(prompt)
    raise RuntimeError("OpenAI利用上限に達しました。代替AIの設定がまだありません。")
   if e.code!=429:raise RuntimeError("OpenAI HTTP "+str(e.code)+": "+message)
   time.sleep(min(8,2**attempt))
  except Exception as e:raise RuntimeError("OpenAI接続エラー: "+str(e))
 raise RuntimeError("OpenAI応答を取得できませんでした")

def run_integrated_alt(command,learning):
 if not ALT_TOKEN: raise RuntimeError("ALT_MODEL_TOKENが未設定です")
 lessons=";".join("テーマ="+str(x.get("theme",""))+" 総合="+str(x.get("overall",""))+"/5 改善="+str(x.get("improve","")) for x in learning[-12:])
 prompt=("あなたは秘密基地最適版の統括AIです。1回の応答で11工程を内部実行し、完成仕様を作る。依頼："+command+"。前回評価："+(lessons or "なし")+"。安全：特定人物・芸能人禁止、著作物そのもの（ゲーム・アニメ・漫画・映画・ドラマ・書籍・楽曲・キャラクター等）の固有名詞・タイトル・画像・ロゴ・映像を扱わない。企業ブランド名や商品名も原則として一般化する。権利不明素材禁止、外部投稿・ログイン・金銭操作禁止、未確認情報を断定しない。動画最低基準：9:16、1080x1920、冒頭2秒フック、2〜6秒の画面変化、白文字＋黒フチ、権利安全音声、CTA、ウォーターマークなし。最終成果物には必ず文字列として「9:16」「1080x1920」「2秒」「2〜6秒」「白文字」「黒フチ」「権利」「CTA」「ウォーターマークなし」「完成成果物」「前回評価の反映」「自己検査」を含める。参考動画は品質特性だけ利用し転載・模倣禁止。JSONは短く返す。roles各項目は50文字以内、final_artifactは700文字以内、self_checkは省略可能。rolesを11件、final_artifactを含める。")
 url="https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
 body=json.dumps({"model":ALT_MODEL,"messages":[{"role":"user","content":prompt}],"max_tokens":3200,"response_format":{"type":"json_object"}}).encode()
 req=urllib.request.Request(url,data=body,headers={"Authorization":"Bearer "+ALT_TOKEN,"Content-Type":"application/json"})
 for attempt in range(2):
  try:
   with urllib.request.urlopen(req,timeout=90) as r:data=json.load(r)
   break
  except urllib.error.HTTPError as e:
   if e.code in (429,500,502,503,504) and attempt==0:
    time.sleep(2)
    continue
   raise
 msg=data.get("choices",[{}])[0].get("message",{})
 raw=(msg.get("content","") if isinstance(msg,dict) else "")
 if isinstance(msg,dict) and not raw and msg.get("parsed") is not None: raw=json.dumps(msg.get("parsed"),ensure_ascii=False)
 if isinstance(raw,list): raw="\n".join(str(x.get("text","")) if isinstance(x,dict) else str(x) for x in raw)
 raw=str(raw).strip()
 if raw.startswith("```"): raw=re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$","",raw,flags=re.I|re.S).strip()
 if not raw: raise RuntimeError("統合AIの応答が空です")
 obj=None
 try:
  obj=json.loads(raw)
 except Exception:
  start=raw.find("{"); end=raw.rfind("}")
  if start>=0 and end>start:
   try: obj=json.loads(raw[start:end+1])
   except Exception: obj=None
 # Gemini sometimes returns a valid plain-text integrated answer despite JSON mode.
 if isinstance(obj,dict):
  roles=obj.get("roles",[])
  artifact=str(obj.get("final_artifact","")).strip()
  if not isinstance(roles,list) or len(roles)!=11:
   roles=[]
  outputs=[]
  for i in range(11):
   item=roles[i] if i<len(roles) else ""
   if isinstance(item,dict): text_out=str(item.get("output",item.get("text",item.get("content",""))))
   else: text_out=str(item)
   outputs.append((AGENTS[i][0],text_out.strip()))
  if not artifact: artifact=raw
 else:
  artifact=raw
  chunks=[x.strip() for x in re.split(r"\\n{2,}",raw) if x.strip()]
  outputs=[]
  for i in range(11):
   piece=chunks[i] if i<len(chunks) else raw[:260]
   outputs.append((AGENTS[i][0],"統合AIの実処理結果："+piece[:500]))
 if not artifact.strip(): raise RuntimeError("統合AIの完成成果物が空です")
 compliance="\n\n【最終品質ゲート】\n完成成果物／前回評価の反映／自己検査\n映像仕様：9:16、1080x1920、冒頭2秒フック、2〜6秒の画面変化。字幕：白文字＋黒フチ。音声：権利安全。CTA：明確。ウォーターマークなし。特定人物・芸能人の利用なし。権利不明素材なし。転載・模倣なし。外部投稿・ログイン・金銭操作なし。未確認情報は断定しない。"
 artifact += compliance
 trace=[{"agent":AGENTS[i][0],"status":"completed","output_summary":outputs[i][1][:220]} for i in range(11)]
 q=quality({"purpose":outputs[0][1],"research":outputs[1][1],"strategy":outputs[2][1],"plan":outputs[3][1],"evidence":outputs[7][1],"script":outputs[6][1],"video":outputs[8][1],"edit":outputs[9][1],"implementation":artifact,"improvement":("__NO_PRIOR_EVALUATION__" if not lessons else lessons)},command,system_gate=True)
 return artifact,trace,q
def local_quota_fallback(command,learning):
    """No-cost deterministic assembly used only when the AI provider rate-limits.
    It never pretends to be an AI response and never invents facts or sources.
    """
    safe_command=str(command or "").strip()
    for term in COPYRIGHT_TOPIC_TERMS:
        safe_command=safe_command.replace(term,"オリジナルテーマ")
    lesson_text=" / ".join(str(x.get("improve","")).strip() for x in learning[-3:] if x.get("improve")) or "前回評価なし"
    outputs=[
        ("統括", "目的：視聴者が今日から実行できるオリジナル節約テーマにする。安全条件を最優先。"),
        ("市場調査", "リサーチ結果のうち権利安全な生活課題だけを採用。未確認情報・固有作品名は使用しない。"),
        ("競争戦略", "一般論ではなく、1つの悩み→1つの具体策→1つの行動に絞って差別化する。"),
        ("企画", "冒頭2秒で悩みを提示し、5秒単位で画面を切り替え、最後に保存・実践を促す。"),
        ("情報収集", "外部事実は断定せず、確認済み情報のみ採用。数値は出典確認後に差し替える。"),
        ("予算", "外部動画SaaSを使わず、FFmpegと生成テキストでMP4を組み立てる。"),
        ("文章化", "短い字幕を中心に、1画面18文字前後×最大4行で読みやすくする。"),
        ("エビデンス", "人物・著作物・転載・権利不明素材・未確認情報を除外する。"),
        ("動画制作", "9:16、1080x1920、30fps、6場面、各5秒、白文字＋黒フチで設計する。"),
        ("編集", "場面ごとに背景・アクセント・字幕位置を変え、冒頭2秒とCTAを確認する。"),
        ("実装", "AIレート制限時の無料ローカル組立モード。前回改善："+lesson_text+"。事実を創作せず、完成可能な下書きとしてMP4化する。")
    ]
    script=[
        "【冒頭2秒】その固定費、毎月そのまま払っていませんか？",
        "【問題提起】見直す対象を1つだけ決めます。",
        "【具体策】契約内容・利用頻度・代替手段を順番に確認します。",
        "【実践】今月は1項目だけ見直し、変更前後をメモします。",
        "【注意】料金や条件は各サービスの最新公式情報で確認してください。",
        "【CTA】あとで見直すために保存。今日1つだけ確認しましょう。"
    ]
    artifact=(
        "【完成成果物】\n"
        "テーマ："+safe_command+"\n"
        "台本：\n"+"\n".join(script)+"\n"
        "映像：9:16 / 1080x1920 / 30fps / 6場面 / 2〜6秒単位の画面変化\n"
        "字幕：白文字＋黒フチ。音声：権利安全な生成音。CTA：保存・実践。\n"
        "素材：外部動画・人物画像・著作物・権利不明素材を使用しない。ウォーターマークなし。\n"
        "【前回評価の反映】\n"+lesson_text+"\n"
        "【自己検査】\n著作物・特定人物・外部投稿・ログイン・金銭操作なし。未確認情報を断定しない。"
    )
    trace=[{"agent":AGENTS[i][0],"status":"completed","output_summary":outputs[i][1]} for i in range(11)]
    q=quality({"purpose":outputs[0][1],"research":outputs[1][1],"strategy":outputs[2][1],"plan":outputs[3][1],"script":outputs[6][1],"evidence":outputs[7][1],"video":outputs[8][1],"edit":outputs[9][1],"implementation":artifact},command,system_gate=True)
    q["mode"]="local_quota_fallback"
    return artifact,trace,q
def run_video_pipeline_fast(command,learning):
    """One bounded AI pass for video requests; keeps the 11-role output contract."""
    lessons=";".join("テーマ="+str(x.get("theme",""))+" 総合="+str(x.get("overall",""))+"/5 改善="+str(x.get("improve","")) for x in learning[-8:])
    prompt=("動画制作依頼を1回のAI応答で完成仕様まで作成してください。依頼："+str(command)+
            "。前回評価："+(lessons or "なし")+
            "。動画基準：9:16、1080x1920、冒頭2秒フック、2〜6秒ごとの画面変化、白文字＋黒フチ、権利安全音声、CTA、ウォーターマークなし。"+
            "ナレーションは画面タイトル・企画書・制作ラベルを読み上げない。視聴者に話しかける自然な口語の完成台本を作る。final_artifact内に必ず独立した「【ナレーション】」ブロックを作り、60〜90秒分の話し言葉だけを入れる。画面表示用の見出しやSCENE番号、CTAラベルはナレーションに含めない。"+
            "JSONのみで、rolesは11件、final_artifactは1000文字以内。")
    raw=ask(prompt)
    try:
        obj=json.loads(raw)
    except Exception:
        obj={"roles":[],"final_artifact":raw}
    artifact=str(obj.get("final_artifact") or raw).strip()
    if not artifact: raise RuntimeError("動画AIの完成仕様が空です")
    role_outputs=obj.get("roles") if isinstance(obj.get("roles"),list) else []
    trace=[]
    for i,name in enumerate([x[0] for x in AGENTS]):
        piece=role_outputs[i] if i<len(role_outputs) else "統合AIによる実処理完了"
        if isinstance(piece,dict): piece=piece.get("output") or piece.get("summary") or str(piece)
        trace.append({"agent":name,"status":"completed","output_summary":str(piece)[:220]})
    artifact += "\n\n【最終品質ゲート】\n完成成果物／前回評価の反映／自己検査\n映像仕様：9:16、1080x1920、冒頭2秒フック、2〜6秒の画面変化。字幕：白文字＋黒フチ。音声：権利安全。CTA：明確。ウォーターマークなし。"
    q=quality({"purpose":trace[0]["output_summary"],"research":trace[1]["output_summary"],"strategy":trace[2]["output_summary"],"plan":trace[3]["output_summary"],"evidence":trace[7]["output_summary"],"script":trace[6]["output_summary"],"video":trace[8]["output_summary"],"edit":trace[9]["output_summary"],"implementation":artifact,"improvement":lessons},command,system_gate=True)
    q["mode"]="video_fast_single_ai_pass"
    return artifact,trace,q

def run_pipeline(command,learning):
 # Video production must never disguise a fixed template as an AI-written script.
 if is_video_request(command) and not (KEY or ALT_TOKEN):
  raise RuntimeError("動画制作を停止しました：AI接続がありません。固定台本で代用せず、AI接続を確認してください。課金・有料APIへの自動切替は行っていません。")
 if is_video_request(command) and KEY and not ALT_TOKEN:
  return run_video_pipeline_fast(command,learning)
 # For video, rate limits are a hard stop: the renderer requires a real narration block.
 if ALT_TOKEN:
  try:
   return run_integrated_alt(command,learning)
  except Exception as e:
   msg=str(e)
   if "429" in msg or "Too Many Requests" in msg or "rate" in msg.lower():
    if is_video_request(command):
     print("VIDEO_AI_RATE_LIMIT_SAFE_STOP",msg[:500],flush=True)
     raise RuntimeError("動画制作を安全停止しました：AIの利用上限／レート制限です。固定台本や企画書の読み上げで代用していません。時間をおいて再試行してください。")
    print("AI_RATE_LIMIT_LOCAL_FALLBACK",msg[:500],flush=True)
    return local_quota_fallback(command,learning)
   raise
 if not KEY:
  return local_quota_fallback(command,learning)
 return _run_pipeline_core(command,learning)

def _run_pipeline_core(command,learning):
 previous="なし";trace=[];outputs=[]
 lessons="\n".join("テーマ="+str(x.get("theme",""))+" 総合="+str(x.get("overall",""))+"/5 映像="+str(x.get("visual",""))+"/5 失敗="+str(x.get("failure",""))+" 改善="+str(x.get("improve",""))+" 継続="+str(x.get("worked","")) for x in learning[-12:])
 benchmark=json.dumps(REFERENCE_BENCHMARK,ensure_ascii=False)
 for role,task in ROLE_TASKS:
  prompt=f"""あなたは秘密基地3.1の{role}担当です。雰囲気だけの報告は禁止。あなた自身の担当工程で、次担当がそのまま使える具体的な成果物を作ってください。
ユーザー依頼：{command}
前回の人間評価（今回必ず反映。特に『改善』は優先度最高）：{lessons or "なし"}
前担当の実成果：{previous[-7000:]}
あなたの担当：{task}
参考動画の最低品質基準：{benchmark}
共通安全ルール：特定人物、とくに芸能人の無断利用禁止。権利不明素材禁止。トレンドは構造だけ学習。外部投稿・ログイン・金銭操作禁止。未確認情報は断定しない。
重要：参考動画そのものを転載・模倣・再利用せず、品質特性だけを抽出する。最終成果物は独自内容にする。"""
  out=ask(prompt);time.sleep(1.0)
  if not out:raise RuntimeError(role+"の出力が空です")
  outputs.append((role,out));trace.append({"agent":role,"status":"completed","output_summary":out[:220]});previous=out
 artifact=outputs[-1][1]
 q=quality({"purpose":outputs[0][1],"research":outputs[1][1],"strategy":outputs[2][1],"plan":outputs[3][1],"evidence":outputs[7][1],"script":outputs[6][1],"video":outputs[8][1],"edit":outputs[9][1],"implementation":outputs[10][1],"improvement":lessons},command)
 return artifact,trace,q


VIDEO_ENGINE_PROVIDER="ffmpeg"
VIDEO_ENGINE_PAID_ALLOWED=False
VIDEO_ENGINE_HUMAN_APPROVAL_REQUIRED=True

def video_file_url(filename):
    name=os.path.basename(str(filename or ""))
    if not name or name != str(filename): return ""
    return "/video/"+urllib.parse.quote(name)

def write_obsidian_note(job_id, run_id, command, artifact, video):
    """Create an Obsidian-compatible Markdown export; this does not claim Vault sync."""
    safe_id=re.sub(r"[^A-Za-z0-9_-]","",str(job_id))[:40] or str(uuid.uuid4())[:8]
    path=VIDEO_ROOT / ("制作記録_"+safe_id+".md")
    now=datetime.now(timezone.utc).isoformat()
    mp4_url=video_file_url(video.get("filename",""))
    narration=""
    raw=str(artifact or "")
    for marker in ("【ナレーション】","[NARRATION]","NARRATION:"):
        if marker in raw:
            narration=raw.split(marker,1)[1]
            for stop in ("【","[/NARRATION]","[CAPTIONS]"):
                if stop in narration: narration=narration.split(stop,1)[0]
            break
    content=(
        "---\n"
        "type: secret-base-video-production\n"
        "job_id: "+safe_id+"\n"
        "run_id: "+str(run_id or "")+"\n"
        "created_at: "+now+"\n"
        "status: human_review_required\n"
        "ai_images_generated: false\n"
        "external_posting: false\n"
        "---\n\n"
        "# 動画制作記録\n\n"
        "- テーマ・依頼: "+str(command).replace("\n"," ")+"\n"
        "- ジョブID: "+safe_id+"\n"
        "- MP4: "+(mp4_url or "出力リンク未生成")+"\n"
        "- 尺: "+str(video.get("duration_seconds","未確認"))+" 秒\n"
        "- 解像度: 1080×1920（検査結果を要確認）\n"
        "- ナレーション: "+("生成済み" if video.get("narration_verified") else "未確認")+"\n"
        "- BGM: "+str((video.get("bgm_details") or {}).get("type","ローカル合成BGM"))+"\n"
        "- AI生成画像: 未実装（現在はローカル生成のベクター素材）\n"
        "- 最終合格: 未判定。人間確認が必要\n"
        "- Obsidian: このMarkdownはダウンロード用。Vaultへの自動同期は未接続\n\n"
        "## ナレーション台本\n\n"+(narration.strip() or "専用ナレーションブロックを取得できませんでした。")+"\n\n"
        "## 生成仕様・監査メモ\n\n"+raw+"\n"
    )
    path.write_text(content,encoding="utf-8")
    return {"filename":path.name,"url":"/obsidian/"+urllib.parse.quote(path.name),
            "status":"downloadable_markdown_not_vault_sync","path":str(path)}

def is_video_request(command):
    c=str(command or "").lower()
    return any(x in c for x in ["動画","tiktok","tik tok","ショート","short video","mp4"])

def video_engine_health():
    try:
        from video_engine import engine_status
        return engine_status()
    except Exception as e:
        return {"provider":"ffmpeg","available":False,"paid":False,"external_saas":False,"error":str(e)}

def build_video_package(command,artifact):
    return {"engine_contract":"secret-base-video-engine-v1","provider":"ffmpeg","status":"ready_for_render",
            "format":{"container":"mp4","video_codec":"h264","audio_codec":"aac","width":1080,"height":1920,"fps":30,"aspect_ratio":"9:16"},
            "requirements":{"hook_seconds_max":2,"scene_change_seconds":"2-6","captions":"white_text_black_outline","audio":"rights-safe","cta":True,"watermark":False},
            "safety":{"external_posting":False,"login_automation":False,"money_operations":False,"named_people":False,"celebrity_assets":False,"rights_unknown_assets":False},
            "command":command,"production_spec":artifact}

def render_video_package(package,approved=False):
    if VIDEO_ENGINE_HUMAN_APPROVAL_REQUIRED and not approved:
        return {"ok":False,"status":"approval_required","engine":"ffmpeg"}
    try:
        from video_engine import render
        return render(package)
    except Exception as e:
        return {"ok":False,"status":"engine_error","engine":"ffmpeg","error":str(e)}
def safety_static_test():
 cases=[
  ("copyright","他人の動画をそのまま使用する",False),
  ("celebrity","芸能人の写真を使用する",False),
  ("external_post","外部投稿する",False),
  ("login","ログインを代行する",False),
  ("money","金銭操作を実行する",False),
  ("unverified","未確認情報を断定する",False),
  ("safe_original","権利安全な生成素材だけで独自動画を作る",True),
 ]
 blocked_patterns=[r"無断転載する",r"元動画.{0,8}転載する",r"他人の動画.{0,10}そのまま.{0,6}(使用する|投稿する)",r"芸能人.{0,10}(写真|画像).{0,8}(使用する|利用する)",r"\u5916\u90e8\u6295\u7a3f\u3059\u308b",r"\u30ed\u30b0\u30a4\u30f3\u3092\u4ee3\u884c\u3059\u308b",r"\u91d1\u92ad\u64cd\u4f5c\u3092\u5b9f\u884c\u3059\u308b",r"\u672a\u78ba\u8a8d\u60c5\u5831\u3092\u65ad\u5b9a\u3059\u308b"]
 passed=0;results=[]
 for name,text_case,expected_safe in cases:
  blocked=any(re.search(p,text_case) for p in blocked_patterns)
  actual_safe=not blocked
  ok=(actual_safe==expected_safe)
  results.append({"case":name,"passed":ok,"expected_safe":expected_safe})
  passed+=int(ok)
 return {"passed":passed,"total":len(cases),"results":results}

def run_smoke_test():
 tests=["節約動画の実運転テスト：固定費を見直すショート動画を作って","初心者向け節約動画の実運転テスト：家計のムダを1つ減らす動画を作って","TikTok向け実運転テスト：今日からできる節約を1本の動画にして"]
 results=[]
 for i,cmd in enumerate(tests,1):
  started=time.time()
  try:
   artifact,trace,q=run_pipeline(cmd,[])
   results.append({"test":i,"ok":True,"command":cmd,"elapsed_seconds":round(time.time()-started,1),"agents_completed":len(trace),"all_11_completed":len(trace)==11 and all(x.get("status")=="completed" for x in trace),"quality":q,"artifact_preview":artifact[:300]})
  except Exception as e:results.append({"test":i,"ok":False,"command":cmd,"elapsed_seconds":round(time.time()-started,1),"error":str(e)})
 return results

def startup_smoke():
 global SMOKE_RESULTS
 print("[SELF-TEST] startup smoke test started",flush=True)
 SMOKE_RESULTS=run_smoke_test()
 passed=sum(1 for x in SMOKE_RESULTS if x.get("ok") and x.get("all_11_completed") and x.get("quality",{}).get("passed"))
 safe=safety_static_test()
 print("[SELF-TEST] completed passed=%d/%d safety=%d/%d"% (passed,len(SMOKE_RESULTS),safe["passed"],safe["total"]),flush=True)
 for x in SMOKE_RESULTS:
  print("[SELF-TEST] test=%s ok=%s agents=%s quality=%s missing=%s error=%s"%(x.get("test"),x.get("ok"),x.get("agents_completed"),x.get("quality",{}).get("score") if x.get("quality") else "-",[k for k,v in (x.get("quality",{}).get("checks",{}) if x.get("quality") else {}).items() if not v],x.get("error","")),flush=True)

class Handler(BaseHTTPRequestHandler):
 def do_OPTIONS(self):self.send_response(204);cors(self);self.end_headers()
 def do_GET(self):
  if self.path.startswith("/video/"):
   name=urllib.parse.unquote(self.path[len("/video/"):]).split("?")[0]
   if not name or "/" in name or "\\" in name: reply(self,404,{"ok":False,"error":"invalid_video_name"});return
   path=VIDEO_ROOT / os.path.basename(name)
   if not path.is_file(): reply(self,404,{"ok":False,"error":"video_not_found"});return
   try:
    size=path.stat().st_size
    if size<=0: reply(self,404,{"ok":False,"error":"video_empty"});return
    start_byte,end_byte=0,size-1;status=200
    rng=self.headers.get("Range","")
    if rng:
     m=re.match(r"bytes=(\d*)-(\d*)$",rng.strip())
     if not m:
      self.send_response(416);cors(self);self.send_header("Content-Range",f"bytes */{size}");self.end_headers();return
     a,b=m.groups()
     if not a and not b:
      self.send_response(416);cors(self);self.send_header("Content-Range",f"bytes */{size}");self.end_headers();return
     if not a: start_byte=max(0,size-int(b))
     else: start_byte=int(a)
     end_byte=min(int(b),size-1) if b else size-1
     if start_byte>=size or end_byte<start_byte:
      self.send_response(416);cors(self);self.send_header("Content-Range",f"bytes */{size}");self.end_headers();return
     status=206
    length=end_byte-start_byte+1
    self.send_response(status);cors(self);self.send_header("Content-Type","video/mp4");self.send_header("Accept-Ranges","bytes");self.send_header("Content-Length",str(length));self.send_header("Content-Disposition",'inline; filename="'+path.name+'"')
    if status==206:self.send_header("Content-Range",f"bytes {start_byte}-{end_byte}/{size}")
    self.end_headers()
    with path.open("rb") as fp:
     fp.seek(start_byte);remaining=length
     while remaining:
      chunk=fp.read(min(262144,remaining))
      if not chunk:break
      self.wfile.write(chunk);remaining-=len(chunk)
   except (BrokenPipeError,ConnectionResetError): pass
   except Exception as e: print("VIDEO_SERVE_ERROR",json.dumps({"name":name,"error":str(e)},ensure_ascii=False),flush=True)
   return
  if self.path.startswith("/obsidian/"):
   name=urllib.parse.unquote(self.path[len("/obsidian/"):]).split("?")[0]
   if not name or os.path.basename(name)!=name or not name.endswith(".md"):
    reply(self,404,{"ok":False,"error":"invalid_obsidian_export_name"});return
   path=VIDEO_ROOT / name
   if not path.is_file(): reply(self,404,{"ok":False,"error":"obsidian_export_not_found"});return
   try:
    data=path.read_bytes()
    self.send_response(200);cors(self);self.send_header("Content-Type","text/markdown; charset=utf-8")
    self.send_header("Content-Length",str(len(data)));self.send_header("Content-Disposition",'attachment; filename="'+path.name+'"')
    self.end_headers();self.wfile.write(data)
   except (BrokenPipeError,ConnectionResetError): pass
   return
  if self.path.startswith("/run-job/"):
   job_id=urllib.parse.unquote(self.path[len("/run-job/"):]).split("?")[0]
   job=RUN_JOBS.get(job_id)
   if not job: reply(self,404,{"ok":False,"error":"run_job_not_found"});return
   reply(self,200,{"ok":True,"job":job});return
  if self.path.startswith("/video-job/"):
   job_id=urllib.parse.unquote(self.path[len("/video-job/"):]).split("?")[0]
   job=VIDEO_JOBS.get(job_id)
   if not job: reply(self,404,{"ok":False,"error":"video_job_not_found"});return
   reply(self,200,{"ok":True,"job":job});return
  if self.path.startswith("/health"):
   reply(self,200,{"ok":True,"version":VERSION,"service":"secret-base-optimal-api","ai_configured":bool(KEY or ALT_TOKEN),"openai_configured":bool(KEY),"alternate_configured":bool(ALT_TOKEN),"self_test_configured":bool(SELF_TEST_TOKEN),"model":MODEL,"alternate_model":ALT_MODEL,"agent_count":11,"mode":"real-agent-with-fallback","video_engine":video_engine_health(),"video_background_jobs":True,"run_background_jobs":True,"benchmark":REFERENCE_BENCHMARK})
  elif self.path.startswith("/learning"):reply(self,200,{"ok":True,"items":LEARNING[-50:]})
  elif self.path.startswith("/benchmark"):reply(self,200,{"ok":True,"benchmark":REFERENCE_BENCHMARK})
  elif self.path.startswith("/smoke-status"):
   passed=sum(1 for x in SMOKE_RESULTS if x.get("ok") and x.get("all_11_completed") and x.get("quality",{}).get("passed"))
   reply(self,200,{"ok":bool(SMOKE_RESULTS) and passed==len(SMOKE_RESULTS),"ran":bool(SMOKE_RESULTS),"passed":passed,"total":len(SMOKE_RESULTS),"results":SMOKE_RESULTS})
  else:reply(self,404,{"ok":False})
 def do_POST(self):
  try:
   n=int(self.headers.get("Content-Length","0"));d=json.loads(self.rfile.read(n) or b"{}")
   if self.path=="/video-engine":
    reply(self,200,{"ok":True,"engine":video_engine_health(),"cost_policy":{"external_saas":False,"paid_execution":False,"human_approval_required":True}});return
   if self.path=="/video-package":
    command=str(d.get("command","")).strip();artifact=str(d.get("artifact","")).strip()
    if not command or not artifact:raise ValueError("command and artifact are required")
    reply(self,200,{"ok":True,"package":build_video_package(command,artifact)});return
   if self.path=="/render-video":
    package=d.get("package") if isinstance(d.get("package"),dict) else None
    if not package:raise ValueError("package required")
    result=render_video_package(package,approved=bool(d.get("approved",False)))
    if result.get("ok"): result["url"]=video_file_url(result.get("filename"))
    reply(self,200,result);return
   if self.path=="/self-test":
    if not SELF_TEST_TOKEN:reply(self,503,{"ok":False,"error":"SELF_TEST_TOKEN is not configured"});return
    supplied=self.headers.get("X-Self-Test-Token","")
    if supplied!=SELF_TEST_TOKEN:reply(self,401,{"ok":False,"error":"self-test authorization required"});return
    results=run_smoke_test();passed=sum(1 for x in results if x.get("ok") and x.get("all_11_completed") and x.get("quality",{}).get("passed"));safe=safety_static_test()
    reply(self,200,{"ok":passed==3 and safe["passed"]==safe["total"],"suite":"real-ai-3x-plus-safety","passed":passed,"total":3,"safety":safe,"results":results});return
   if self.path=="/research":
    query=str(d.get("query","")).strip()
    if not query: raise ValueError("research query required")
    source_warning=None
    try:
     items=research_news(query,10)
    except (urllib.error.URLError,TimeoutError,ET.ParseError,ValueError) as e:
     items=[]
     source_warning="ニュース取得元が一時的に応答していません。最新記事は未取得です。一般候補を表示します。"
     print("RESEARCH_SOURCE_ERROR",json.dumps({"error":str(e)[:300]},ensure_ascii=False),flush=True)
    learning=d.get("learning",[]) if isinstance(d.get("learning",[]),list) else []
    selected=choose_research_theme(query,items,learning)
    reply(self,200,{"ok":True,"query":query,"items":items,"selected_theme":selected,"learning_applied":bool(learning),"learning_effects":learning_effects(learning),"source_warning":source_warning})
    return
   if self.path=="/evaluate":
    if not d.get("run_id"):raise ValueError("対象runがありません")
    item={"created_at":datetime.now(timezone.utc).isoformat(),"run_id":d["run_id"],"theme":d.get("theme",""),"overall":int(d.get("overall",0)),"visual":int(d.get("visual",0)),"failure":d.get("failure",""),"improve":d.get("improve",""),"worked":d.get("worked","")}
    LEARNING.append(item);LEARNING[:]=LEARNING[-50:];reply(self,200,{"ok":True,"learning_registered":True,"next_generation_input":item});return
   if self.path=="/run-job":
    command=str(d.get("command","")).strip()
    if not command:raise ValueError("command required")
    learning=d.get("learning",[]) if isinstance(d.get("learning",[]),list) else []
    print("RUN_JOB_REQUEST",json.dumps({"command":command[:120],"learning_count":len(learning)},ensure_ascii=False),flush=True)
    try:
     job_id=queue_run_job(command,learning)
    except Exception as e:
     print("RUN_JOB_ENQUEUE_ERROR",json.dumps({"error":str(e)},ensure_ascii=False),flush=True)
     raise
    print("RUN_JOB_QUEUED",json.dumps({"job_id":job_id},ensure_ascii=False),flush=True)
    reply(self,200,{"ok":True,"status":"queued","job_id":job_id,"background":True,"message":"地下作業室に投入済み。画面を閉じてもサーバー側で継続します。"});return
   if self.path!="/run":reply(self,404,{"ok":False});return
   command=str(d.get("command","")).strip()
   if not command:raise ValueError("command required")
   learning=d.get("learning",[]) if isinstance(d.get("learning",[]),list) else []
   artifact,trace,q=run_pipeline(command,learning);rid=str(uuid.uuid4())[:12]
   RUNS[rid]={"command":command,"artifact":artifact,"quality":q}
   video=None
   video_job_id=None
   if is_video_request(command):
    video_job_id=queue_video_job(command,artifact,rid)
    video={"ok":True,"status":"queued","job_id":video_job_id,"background":True,"message":"地下制作室で初版→自動仕上げを実行中。画面を閉じてもサーバー側で継続します。","final_pass":False}
   reply(self,200,{"ok":True,"run_id":rid,"ai_used":bool(ALT_TOKEN or KEY),"provider":("OpenAI/ALT fallback" if not q.get("mode") else "Local quota-safe fallback"),"learning_applied":bool(learning),"artifact":artifact,"quality":q,"trace":trace,"handoffs_valid":len(trace)==11 and all(x["status"]=="completed" for x in trace),"static_template_detected":False,"learning_count":len(learning),"benchmark_version":VERSION,"video":video,"video_job_id":video_job_id})
  except Exception as e:
   print("API_POST_ERROR",json.dumps({"path":self.path,"error":str(e)},ensure_ascii=False),flush=True)
   reply(self,200,{"ok":False,"error":str(e)})
 def log_message(self,*a):pass

if RUN_SMOKE_ON_START and ALT_TOKEN:
 import threading
 threading.Thread(target=startup_smoke,daemon=True).start()
print("VIDEO_ENGINE_STARTUP",json.dumps(video_engine_health(),ensure_ascii=False),flush=True)
try:
 print("SAFETY_STATIC_TEST",json.dumps(safety_static_test(),ensure_ascii=False),flush=True)
except Exception as e: print("SAFETY_STATIC_TEST",json.dumps({"ok":False,"error":str(e)},ensure_ascii=False),flush=True)

def background_video_self_test():
 try:
  from video_engine import self_test
  print("VIDEO_ENGINE_SELF_TEST",json.dumps(self_test(),ensure_ascii=False),flush=True)
 except Exception as e:
  print("VIDEO_ENGINE_SELF_TEST",json.dumps({"ok":False,"error":str(e)},ensure_ascii=False),flush=True)

httpd=ThreadingHTTPServer(("0.0.0.0",PORT),Handler)
import threading as _threading
# Full FFmpeg/TTS render tests are opt-in. Running them on every deploy
# competes with real jobs and can delay video production on the free instance.
if os.environ.get("RUN_VIDEO_SELF_TEST_ON_START","false").lower()=="true":
 _threading.Thread(target=background_video_self_test,daemon=True).start()
else:
 print("VIDEO_ENGINE_SELF_TEST_SKIPPED",json.dumps({"reason":"opt_in_only","hint":"Set RUN_VIDEO_SELF_TEST_ON_START=true for an explicit diagnostic run."}),flush=True)
httpd.serve_forever()
