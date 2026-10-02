import os, json, urllib.request, urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("PORT", "10000"))
MODEL = os.environ.get("OPENAI_MODEL", "gpt-6-luna")
API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()

AGENTS = [
    ("企画","まいか"),("市場調査","りょう"),("収益設計","たくや"),("情報整理","はると"),
    ("予算管理","りの"),("文章制作","れん"),("根拠確認","あかり"),("動画制作","かい"),
    ("編集","なな"),("実装","ゆい"),("保存","司書(仮)"),("統括補佐","さとる")
]

def cors(h):
    h.send_header("Access-Control-Allow-Origin","*")
    h.send_header("Access-Control-Allow-Headers","Content-Type")
    h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")

def reply(h, code, obj):
    b=json.dumps(obj,ensure_ascii=False).encode()
    h.send_response(code); cors(h); h.send_header("Content-Type","application/json; charset=utf-8")
    h.send_header("Content-Length",str(len(b))); h.end_headers(); h.wfile.write(b)

def ai_plan(command):
    if not API_KEY:
        return {
            "mode":"simulation_backend",
            "model":None,
            "title":"実AI接続待ちの安全版",
            "summary":"バックエンド接続は正常です。OPENAI_API_KEYが設定されるとResponses APIで実AI制作へ切り替わります。",
            "deliverable":"指示内容を保存した制作計画",
            "text":"現在は費用を発生させない安全なバックエンド動作です。外部投稿・送信は行いません。"
        }
    prompt = """あなたは秘密基地・最適版の統括AIです。
ユーザー指示をもとに、12担当が協働する制作計画を日本語で作成してください。
外部投稿・送信・金銭操作は絶対に行わず、人間承認待ちで止めます。
簡潔に、目的、成果物、各担当の役割、品質確認項目、完成物の本文案を含めてください。
指示:""" + command
    body=json.dumps({
        "model":MODEL,
        "input":[
            {"role":"system","content":"秘密基地・最適版の安全な統括AI。外部操作は禁止。"},
            {"role":"user","content":prompt}
        ],
        "max_output_tokens":1800
    }).encode()
    req=urllib.request.Request("https://api.openai.com/v1/responses",data=body,
        headers={"Authorization":"Bearer "+API_KEY,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=90) as r:
            data=json.load(r)
        text=data.get("output_text","")
        if not text:
            for item in data.get("output",[]):
                for part in item.get("content",[]):
                    if part.get("type")=="output_text": text += part.get("text","")
        return {"mode":"openai_responses","model":MODEL,"title":"AI制作計画","summary":"実AIによる制作計画を生成しました。","deliverable":"人間承認待ちの成果物案","text":text}
    except Exception as e:
        return {"mode":"error","model":MODEL,"title":"AI接続エラー","summary":"実AI呼び出しに失敗したため安全に停止しました。","deliverable":"未公開","text":"外部投稿・送信は行っていません。再実行してください。","error":str(e)[:240]}

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self): self.send_response(204); cors(self); self.end_headers()
    def do_GET(self):
        if self.path.startswith("/health"):
            reply(self,200,{"ok":True,"service":"secret-base-optimal-api","ai_configured":bool(API_KEY),"model":MODEL,"external_actions":False})
        else: reply(self,404,{"ok":False})
    def do_POST(self):
        if self.path != "/run": reply(self,404,{"ok":False}); return
        try:
            n=int(self.headers.get("Content-Length","0")); data=json.loads(self.rfile.read(n) or b"{}")
            command=str(data.get("command","")).strip() or "新しい成果物を企画・制作してください"
            result=ai_plan(command)
            result.update({"ok":True,"command":command,"human_approval_required":True,"external_posting":False,"agents":[{"role":a,"name":n} for a,n in AGENTS]})
            reply(self,200,result)
        except Exception as e: reply(self,400,{"ok":False,"error":str(e)})
    def log_message(self,*args): return

ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
