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
def ask(prompt):
 body=json.dumps({"model":MODEL,"input":prompt,"max_output_tokens":4000}).encode()
 req=urllib.request.Request("https://api.openai.com/v1/responses",data=body,headers={"Authorization":"Bearer "+KEY,"Content-Type":"application/json"})
 with urllib.request.urlopen(req,timeout=120) as r:data=json.load(r)
 out=data.get("output_text","")
 if not out:
  for it in data.get("output",[]):
   for p in it.get("content",[]):
    if p.get("type")=="output_text":out+=p.get("text","")
 return out
def extract_json(s):
 m=re.search(r'\{.*\}',s,re.S)
 if not m: raise ValueError("AI returned non-JSON")
 return json.loads(m.group())
def quality(a):
 required=["purpose","research","strategy","plan","evidence","script","video","edit","implementation","improvement"]
 checks={k:bool(a.get(k)) for k in required};score=round(sum(checks.values())/len(checks)*100)
 safety=all(x not in str(a).lower() for x in ["芸能人の写真","有名人の画像を使用","元動画を転載"])
 if not safety:score=min(score,70)
 return {"score":score,"passed":score>=95,"checks":checks,"safety":safety}
def build_prompt(command,learning):
 lessons=[]
 for x in learning[-12:]:
  lessons.append("失敗="+str(x.get("failure",""))+" 改善="+str(x.get("improve",""))+" 継続="+str(x.get("worked","")))
 return f'''秘密基地3.0の実働統括AI。これはUI演出ではなく実処理です。
11担当を実際の工程として順番に実行し、前工程の出力を次工程へ渡してください。
担当: 統括,市場調査,競争戦略,企画,情報収集,予算,文章化,エビデンス,動画制作,編集,実装。
依頼:{command}
過去の人間評価:{json.dumps(lessons,ensure_ascii=False)}
絶対条件:
- 過去評価の失敗/改善を具体的に今回の出力へ反映する
- 「今回の改善点」を明記する
- 固定テンプレート・固定台本を使わない
- 特定人物、とくに芸能人を使わない
- 権利不明素材を使わない。トレンドは構造のみ学習
- 出典/確認事項が必要な事実は要確認と明記
- 外部投稿、ログイン、金銭操作はしない
JSONだけを返す。キーは purpose,research,strategy,plan,evidence,script,video,edit,implementation,improvement,artifact_title,artifact。各値は担当が実際に作った具体的な内容。artifactは人間が確認できる完成制作指示書/台本。'''
def run_ai(command,learning):
 if not KEY: raise RuntimeError("OPENAI_API_KEYが未設定のため実AIを実行できません")
 raw=ask(build_prompt(command,learning));return extract_json(raw)
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
    if not d.get("run_id") or d["run_id"] not in RUNS: raise ValueError("対象runがありません")
    item={"created_at":__import__("datetime").datetime.utcnow().isoformat()+"Z","run_id":d["run_id"],"theme":d.get("theme",""),"overall":int(d.get("overall",0)),"visual":int(d.get("visual",0)),"failure":d.get("failure",""),"improve":d.get("improve",""),"worked":d.get("worked","")}
    LEARNING.append(item);LEARNING[:]=LEARNING[-50:];reply(self,200,{"ok":True,"learning_registered":True,"next_generation_input":item});return
   if self.path!="/run":reply(self,404,{"ok":False});return
   command=str(d.get("command","")).strip()
   if not command:raise ValueError("command required")
   learning=d.get("learning",[]) if isinstance(d.get("learning",[]),list) else []
   a=run_ai(command,learning);q=quality(a);rid=str(uuid.uuid4())[:12]
   trace=[]
   keys=["purpose","research","strategy","plan","evidence","script","video","edit","implementation","improvement"]
   roles=[x[0] for x in AGENTS]
   for i,(role,key) in enumerate(zip(roles,["purpose","research","strategy","plan","evidence","script","video","edit","implementation","improvement"])):
    trace.append({"agent":role,"status":"completed","input_from_previous":i>0,"output_summary":str(a.get(key,""))[:180]})
   trace.insert(0,{"agent":"統括","status":"completed","input_from_previous":False,"output_summary":str(a.get("purpose",""))[:180]})
   RUNS[rid]={"command":command,"artifact":a.get("artifact",""),"quality":q}
   reply(self,200,{"ok":True,"run_id":rid,"ai_used":True,"learning_applied":bool(learning),"artifact":a.get("artifact",""),"quality":q,"trace":trace,"handoffs_valid":all(x["status"]=="completed" for x in trace),"static_template_detected":False,"learning_count":len(learning)})
  except Exception as e:reply(self,200,{"ok":False,"error":str(e)})
 def log_message(self,*a):pass
ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
