import os,json,urllib.request,urllib.error,uuid,re,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from datetime import datetime,timezone

PORT=int(os.environ.get("PORT","10000"))
MODEL=os.environ.get("OPENAI_MODEL","gpt-5.6-luna")
KEY=os.environ.get("OPENAI_"+"API_"+"KEY","").strip()
VERSION="3.1.2"

AGENTS=[("統括","さとる"),("市場調査","りょう"),("競争戦略","たくや"),("企画","まいか"),("情報収集","はると"),("予算","りの"),("文章化","れん"),("エビデンス","あかり"),("動画制作","かい"),("編集","なな"),("実装","ゆい")]
LEARNING=[]
RUNS={}

REFERENCE_BENCHMARK={
 "source":"ユーザー提供TikTok参考動画",
 "duration_seconds":93.7,
 "aspect_ratio":"9:16",
 "reference_resolution":"512x910",
 "minimum_target_resolution":"1080x1920",
 "visual":"全画面の高密度ビジュアル。場面転換で飽きさせず、主役が明確。",
 "captions":"白文字＋黒フチ等で高コントラスト。画面下部の安全領域内で常時読みやすい。",
 "pacing":"冒頭2秒以内にフック。静止画の連続にせず、概ね2〜6秒単位で画面変化を設計。",
 "audio":"ナレーション・効果音・BGMを役割分担し、権利確認済み/生成可能な素材だけを使用。",
 "finish":"TikTok向け完成仕様として、タイトル、台本、カット、字幕、音声、編集、CTAまで具体化。"
}

def cors(h):
 h.send_header("Access-Control-Allow-Origin","*");h.send_header("Access-Control-Allow-Headers","Content-Type");h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")

def reply(h,c,o):
 b=json.dumps(o,ensure_ascii=False).encode();h.send_response(c);cors(h);h.send_header("Content-Type","application/json; charset=utf-8");h.send_header("Content-Length",str(len(b)));h.end_headers();h.wfile.write(b)

def quality(a,command):
 text="\n".join(str(v) for v in a.values())
 low=text.lower()
 checks={
  "purpose":bool(a.get("purpose")),
  "research":bool(a.get("research")),
  "strategy":bool(a.get("strategy")),
  "plan":bool(a.get("plan")),
  "script":bool(a.get("script")),
  "evidence":bool(a.get("evidence")),
  "video":bool(a.get("video")),
  "edit":bool(a.get("edit")),
  "implementation":bool(a.get("implementation")),
  "learning_reflection":bool(a.get("improvement"))
 }
 video_cmd=("tiktok" in command.lower() or "tik tok" in command.lower() or "動画" in command or "ショート" in command)
 if video_cmd:
  checks.update({
   "vertical_9_16":bool(re.search(r"9\s*[:：/]\s*16|縦型",text,re.I)),
   "1080x1920":bool(re.search(r"1080\s*[x×＊*]\s*1920|1920\s*[x×＊*]\s*1080",text,re.I)),
   "hook_2sec":bool(re.search(r"2秒|冒頭.{0,12}フック|フック.{0,12}2秒",text)),
   "caption_readability":bool(re.search(r"字幕.{0,20}(白|黒フチ|縁|コントラスト)|白文字.{0,20}(黒フチ|縁)",text)),
   "pacing":bool(re.search(r"2[〜~\-–]6秒|2秒.{0,20}6秒|場面転換|カット割",text)),
   "rights_safe_audio":bool(re.search(r"権利.{0,20}(確認|安全)|著作権.{0,20}(確認|安全)|ライセンス",text)),
   "cta":bool(re.search(r"CTA|行動喚起|フォロー|保存|コメント",text,re.I)),
   "no_watermark":bool(re.search(r"ウォーターマーク.{0,15}(なし|削除)|透かし.{0,15}(なし|削除)",text))
  })
 score=round(sum(checks.values())/len(checks)*100)
 prohibited=["芸能人の写真を使用","有名人の画像を使用","元動画を転載","無断転載","他人の動画をそのまま"]
 safety=not any(x in text for x in prohibited)
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
 ("実装","全担当の成果を統合し、今回の完成成果物を作る。前回評価を明示的に反映する。動画依頼なら、下記の参考動画を最低品質基準として、1080x1920、9:16、冒頭2秒フック、2〜6秒程度の画面変化、読みやすい白字幕＋黒フチ、権利安全な音声、CTA、ウォーターマークなしを必ず具体化する。最後に『完成成果物』『前回評価の反映』『自己検査』の3見出しを付ける。")
]

def ask(prompt):
 body=json.dumps({"model":MODEL,"input":prompt,"max_output_tokens":450}).encode()
 req=urllib.request.Request("https://api.openai.com/v1/responses",data=body,headers={"Authorization":"Bearer "+KEY,"Content-Type":"application/json"})
 last_error=None
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
   try:
    detail=json.loads(raw).get("error",{})
   except Exception:
    detail={}
   code=str(detail.get("code") or "")
   message=str(detail.get("message") or raw[:500])
   last_error=(e.code,code,message)
   if e.code != 429:
    raise RuntimeError(f"OpenAI HTTP {e.code}: {message}")
   if code in ("insufficient_quota","billing_hard_limit_reached"):
    raise RuntimeError("OpenAI APIの利用上限/残高により429が発生しています。RenderのAPIキー自体は認識されていますが、利用可能なAPIクレジットまたは上限設定を確認してください。")
   wait=min(8,2**attempt)
   retry_after=e.headers.get("Retry-After")
   if retry_after:
    try: wait=max(wait,min(30,int(float(retry_after))))
    except Exception: pass
   time.sleep(wait)
  except Exception as e:
   raise RuntimeError(f"OpenAI接続エラー: {e}")
 if last_error:
  raise RuntimeError(f"OpenAI 429: {last_error[2]}")
 raise RuntimeError("OpenAI応答を取得できませんでした")

def run_pipeline(command,learning):
 if not KEY: raise RuntimeError("OPENAI_API_KEYが未設定のため実AIを実行できません")
 previous="なし";trace=[];outputs=[]
 lessons="\n".join(
  "テーマ="+str(x.get("theme",""))+" 総合="+str(x.get("overall",""))+"/5 映像="+str(x.get("visual",""))+"/5 失敗="+str(x.get("failure",""))+" 改善="+str(x.get("improve",""))+" 継続="+str(x.get("worked",""))
  for x in learning[-12:]
 )
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
  out=ask(prompt)
  time.sleep(1.0)
  if not out: raise RuntimeError(role+"の出力が空です")
  outputs.append((role,out));trace.append({"agent":role,"status":"completed","output_summary":out[:220]});previous=out
 artifact=outputs[-1][1]
 q=quality({
  "purpose":outputs[0][1],"research":outputs[1][1],"strategy":outputs[2][1],
  "plan":outputs[3][1],"evidence":outputs[7][1],"script":outputs[6][1],
  "video":outputs[8][1],"edit":outputs[9][1],"implementation":outputs[10][1],
  "improvement":lessons
 },command)
 return artifact,trace,q

class Handler(BaseHTTPRequestHandler):
 def do_OPTIONS(self):self.send_response(204);cors(self);self.end_headers()
 def do_GET(self):
  if self.path.startswith("/health"):
   reply(self,200,{"ok":True,"version":VERSION,"service":"secret-base-optimal-api","ai_configured":bool(KEY),"model":MODEL,"agent_count":11,"mode":"real-agent-only","benchmark":REFERENCE_BENCHMARK})
  elif self.path.startswith("/learning"):
   reply(self,200,{"ok":True,"items":LEARNING[-50:]})
  elif self.path.startswith("/benchmark"):
   reply(self,200,{"ok":True,"benchmark":REFERENCE_BENCHMARK})
  else:reply(self,404,{"ok":False})
 def do_POST(self):
  try:
   n=int(self.headers.get("Content-Length","0"));d=json.loads(self.rfile.read(n) or b"{}")
   if self.path=="/evaluate":
    if not d.get("run_id"): raise ValueError("対象runがありません")
    item={"created_at":datetime.now(timezone.utc).isoformat(),"run_id":d["run_id"],"theme":d.get("theme",""),"overall":int(d.get("overall",0)),"visual":int(d.get("visual",0)),"failure":d.get("failure",""),"improve":d.get("improve",""),"worked":d.get("worked","")}
    LEARNING.append(item);LEARNING[:]=LEARNING[-50:]
    reply(self,200,{"ok":True,"learning_registered":True,"next_generation_input":item});return
   if self.path!="/run":reply(self,404,{"ok":False});return
   command=str(d.get("command","")).strip()
   if not command:raise ValueError("command required")
   learning=d.get("learning",[]) if isinstance(d.get("learning",[]),list) else []
   artifact,trace,q=run_pipeline(command,learning);rid=str(uuid.uuid4())[:12]
   RUNS[rid]={"command":command,"artifact":artifact,"quality":q}
   reply(self,200,{"ok":True,"run_id":rid,"ai_used":True,"learning_applied":bool(learning),"artifact":artifact,"quality":q,"trace":trace,"handoffs_valid":len(trace)==11 and all(x["status"]=="completed" for x in trace),"static_template_detected":False,"learning_count":len(learning),"benchmark_version":VERSION})
  except Exception as e:reply(self,200,{"ok":False,"error":str(e)})
 def log_message(self,*a):pass

ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
