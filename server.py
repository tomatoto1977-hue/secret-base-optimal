import os,json,urllib.request,uuid,re
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
PORT=int(os.environ.get("PORT","10000"));MODEL=os.environ.get("OPENAI_MODEL","gpt-5.6-luna");KEY=os.environ.get("OPENAI_API_KEY","").strip()
AGENTS=[("統括","さとる"),("市場調査","りょう"),("競争戦略","たくや"),("企画","まいか"),("情報収集","はると"),("予算","りの"),("文章化","れん"),("エビデンス","あかり"),("動画制作","かい"),("編集","なな"),("実装","ゆい")]
LEARNING=[]
RUNS={}
def cors(h):
 h.send_header("Access-Control-Allow-Origin","*");h.send_header("Access-Control-Allow-Headers","Content-Type");h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")
def reply(h,c,o):
 b=json.dumps(o,ensure_ascii=False).encode();h.send_response(c);cors(h);h.send_header("Content-Type","application/json; charset=utf-8");h.send_header("Content-Length",str(len(b)));h.end_headers();h.wfile.write(b)
def quality(a):
 required=["purpose","research","strategy","plan","evidence","script","video","edit","implementation","improvement"]
 checks={k:bool(a.get(k)) for k in required}
 score=round(sum(checks.values())/len(checks)*100)
 text=" ".join(str(v) for v in a.values()).lower()
 safety=not any(x in text for x in ["芸能人の写真を使用","有名人の画像を使用","元動画を転載","無断転載"])
 if not safety:score=min(score,70)
 return {"score":score,"passed":score>=95,"checks":checks,"safety":safety}
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
("実装","全担当の成果を統合し、今回の完成成果物を作る。前回評価があれば改善点を明示的に反映する。")
]
def ask(prompt):
 body=json.dumps({"model":MODEL,"input":prompt,"max_output_tokens":700}).encode()
 req=urllib.request.Request("https://api.openai.com/v1/responses",data=body,headers={"Authorization":"Bearer "+KEY,"Content-Type":"application/json"})
 with urllib.request.urlopen(req,timeout=120) as r:data=json.load(r)
 out=data.get("output_text","")
 if not out:
  for it in data.get("output",[]):
   for p in it.get("content",[]):
    if p.get("type")=="output_text":out+=p.get("text","")
 return out.strip()
def run_pipeline(command,learning):
 if not KEY: raise RuntimeError("OPENAI_API_KEYが未設定のため実AIを実行できません")
 previous="なし";trace=[];outputs=[]
 lessons="\n".join("失敗="+str(x.get("failure",""))+" 改善="+str(x.get("improve",""))+" 継続="+str(x.get("worked","")) for x in learning[-12:])
 for role,task in ROLE_TASKS:
  prompt=f"""あなたは秘密基地3.0の{role}担当です。雰囲気だけの報告は禁止。あなた自身の担当工程で具体的な成果物を作ってください。
ユーザー依頼：{command}
前回の人間評価（今回必ず反映）：{lessons or "なし"}
前担当の実成果：{previous[-7000:]}
あなたの担当：{task}
共通安全ルール：特定人物、とくに芸能人の無断利用禁止。権利不明素材禁止。トレンドは構造だけ学習。外部投稿・ログイン・金銭操作禁止。未確認情報は断定しない。
出力は次担当がそのまま使える具体的な作業成果だけ。"""
  out=ask(prompt)
  if not out: raise RuntimeError(role+"の出力が空です")
  outputs.append((role,out));trace.append({"agent":role,"status":"completed","output_summary":out[:220]});previous=out
 artifact=outputs[-1][1]
 alltext="\n".join(x[1] for x in outputs)
 q=quality({"purpose":outputs[0][1],"research":outputs[1][1],"strategy":outputs[2][1],"plan":outputs[3][1],"evidence":outputs[7][1],"script":outputs[6][1],"video":outputs[8][1],"edit":outputs[9][1],"implementation":outputs[10][1],"improvement":lessons})
 return artifact,trace,q,alltext
class Handler(BaseHTTPRequestHandler):
 def do_OPTIONS(self):self.send_response(204);cors(self);self.end_headers()
 def do_GET(self):
  if self.path.startswith("/health"):reply(self,200,{"ok":True,"version":"3.0.0","service":"secret-base-optimal-api","ai_configured":bool(KEY),"model":MODEL,"agent_count":11,"mode":"real-agent-only"})
  elif self.path.startswith("/learning"):reply(self,200,{"ok":True,"items":LEARNING[-50:]})
  else:reply(self,404,{"ok":False})
 def do_POST(self):
  try:
   n=int(self.headers.get("Content-Length","0"));d=json.loads(self.rfile.read(n) or b"{}")
   if self.path=="/evaluate":
    if not d.get("run_id"): raise ValueError("対象runがありません")
    item={"created_at":__import__("datetime").datetime.utcnow().isoformat()+"Z","run_id":d["run_id"],"theme":d.get("theme",""),"overall":int(d.get("overall",0)),"visual":int(d.get("visual",0)),"failure":d.get("failure",""),"improve":d.get("improve",""),"worked":d.get("worked","")}
    LEARNING.append(item);LEARNING[:]=LEARNING[-50:];reply(self,200,{"ok":True,"learning_registered":True,"next_generation_input":item});return
   if self.path!="/run":reply(self,404,{"ok":False});return
   command=str(d.get("command","")).strip()
   if not command:raise ValueError("command required")
   learning=d.get("learning",[]) if isinstance(d.get("learning",[]),list) else []
   artifact,trace,q,alltext=run_pipeline(command,learning);rid=str(uuid.uuid4())[:12]
   RUNS[rid]={"command":command,"artifact":artifact,"quality":q}
   reply(self,200,{"ok":True,"run_id":rid,"ai_used":True,"learning_applied":bool(learning),"artifact":artifact,"quality":q,"trace":trace,"handoffs_valid":len(trace)==11 and all(x["status"]=="completed" for x in trace),"static_template_detected":False,"learning_count":len(learning)})
  except Exception as e:reply(self,200,{"ok":False,"error":str(e)})
 def log_message(self,*a):pass
ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
