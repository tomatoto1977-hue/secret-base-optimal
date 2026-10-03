import os, json, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT=int(os.environ.get("PORT","10000"))
MODEL=os.environ.get("OPENAI_MODEL","gpt-5.6-luna")
API_KEY=os.environ.get("OPENAI_API_KEY","").strip()

# 正本：11担当（統括AI＋専門10担当）
AGENTS=[
    ("統括","さとる"),("市場調査","りょう"),("競争戦略","たくや"),("企画","まいか"),
    ("情報収集","はると"),("予算","りの"),("文章化","れん"),("エビデンス","あかり"),
    ("動画制作","かい"),("編集","なな"),("実装","ゆい")
]

def cors(h):
    h.send_header("Access-Control-Allow-Origin","*")
    h.send_header("Access-Control-Allow-Headers","Content-Type")
    h.send_header("Access-Control-Allow-Methods","GET,POST,OPTIONS")

def reply(h,code,obj):
    b=json.dumps(obj,ensure_ascii=False).encode()
    h.send_response(code); cors(h); h.send_header("Content-Type","application/json; charset=utf-8")
    h.send_header("Content-Length",str(len(b))); h.end_headers(); h.wfile.write(b)

def safety_rules():
    return [
        "テーマは節約に限定せず、毎日の情報収集から役立つ題材を選ぶ",
        "特定人物、とくに芸能人への依存・無断利用を避ける",
        "著作権・商標・肖像・音源等の権利不明素材は使用しない",
        "トレンドは構造だけ学習し、元動画・音源・人物素材をコピーしない",
        "未確認情報は断定せず、出典と確認日時を残す",
        "外部投稿・ログイン・金銭操作は行わず、人間承認で停止する"
    ]

def gate(text):
    items={
        "事実性":(25,any(x in text for x in ["出典","一次情報","公式","確認日","要確認"])),
        "目的適合":(20,any(x in text for x in ["目的","テーマ","視聴者","企画"])),
        "具体性":(20,any(x in text for x in ["具体","手順","行動","カット","字幕"])),
        "伝達性":(15,any(x in text for x in ["結論","冒頭","CTA","フック"])),
        "実装可能性":(10,any(x in text for x in ["Canva","CapCut","受け渡し","素材","編集"])),
        "安全性":(10,any(x in text for x in ["著作権","権利","人物","人間承認","外部投稿なし"]))
    }
    breakdown={k:(v if ok else 0) for k,(v,ok) in items.items()}
    score=sum(breakdown.values())
    return {"score":score,"max":100,"target":95,"passed":score>=95,"breakdown":breakdown}

def simulation(command):
    return {
        "mode":"simulation_backend","model":None,
        "title":"安全シミュレーション制作計画",
        "summary":"費用を発生させない安全なバックエンド動作です。",
        "deliverable":"人間承認前の制作計画",
        "text":(
            "【統括AI】11担当を統括し、95点品質ゲートを実施。\n"
            "【市場調査AI】節約固定なし。毎日の情報から視聴者に役立つテーマを検討。\n"
            "【競争戦略AI】人物依存・炎上依存を避け、独自の切り口を設計。\n"
            "【企画AI】短時間で価値が伝わる企画を設計。\n"
            "【情報収集AI】一次情報・公式情報・確認日を記録。\n"
            "【予算AI】無料・低コスト中心で設計。\n"
            "【文章化AI】結論→具体策→行動の台本を作成。\n"
            "【エビデンスAI】事実・数字・引用・権利・人物利用を点検。\n"
            "【動画制作AI】縦9:16、字幕・カット・素材を設計。\n"
            "【編集AI】1画面1メッセージ、権利確認済み素材のみ使用。\n"
            "【実装AI】次工程への受け渡しを整理。\n"
            "安全ルール：著作権・商標・肖像・音源等の権利不明素材は使用せず、公開は人間承認後のみ。\n"
            f"指示：{command}"
        )
    }

def ai_plan(command):
    if not API_KEY: return simulation(command)
    prompt=f"""あなたは秘密基地・最適版の統括AIです。
11担当（統括、市場調査、競争戦略、企画、情報収集、予算、文章化、エビデンス、動画制作、編集、実装）を統括してください。
テーマは節約に限定せず、毎日の情報から有用な題材を選びます。
特定人物、とくに芸能人への依存や無断利用は禁止。権利不明の画像・動画・音源・文章・キャラクターは使用禁止。
トレンドは構造のみ学習し、元コンテンツをコピーしません。
出典・確認日時を残し、公開・外部操作は人間承認で停止します。
95点品質ゲート：事実性25、目的適合20、具体性20、伝達性15、実装可能性10、安全性10。95点未満なら改善案を出してください。
指示：{command}"""
    body=json.dumps({"model":MODEL,"input":prompt,"max_output_tokens":1800}).encode()
    req=urllib.request.Request("https://api.openai.com/v1/responses",data=body,headers={"Authorization":"Bearer "+API_KEY,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=90) as r: data=json.load(r)
        out=data.get("output_text","")
        if not out:
            for item in data.get("output",[]):
                for part in item.get("content",[]):
                    if part.get("type")=="output_text": out+=part.get("text","")
        return {"mode":"openai_responses","model":MODEL,"title":"AI制作計画","summary":"11担当による制作計画を生成しました。","deliverable":"人間承認前の成果物案","text":out}
    except Exception as e:
        return {"mode":"error","model":MODEL,"title":"AI接続エラー","summary":"実AI呼び出しに失敗したため安全に停止しました。","deliverable":"未公開","text":"外部投稿・送信は行っていません。","error":str(e)[:240]}

class Handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self): self.send_response(204); cors(self); self.end_headers()
    def do_GET(self):
        if self.path.startswith("/health"):
            reply(self,200,{"ok":True,"service":"secret-base-optimal-api","version":"2.0.0","ai_configured":bool(API_KEY),"model":MODEL,"external_actions":False,"agent_count":11,"quality_gate":"95/100"})
        else: reply(self,404,{"ok":False})
    def do_POST(self):
        if self.path!="/run": reply(self,404,{"ok":False}); return
        try:
            n=int(self.headers.get("Content-Length","0")); data=json.loads(self.rfile.read(n) or b"{}")
            command=str(data.get("command","")).strip() or "新しい成果物を企画・制作してください"
            result=ai_plan(command)
            q=gate(result.get("text",""))
            result.update({"ok":True,"command":command,"human_approval_required":True,"external_posting":False,"agents":[{"role":a,"name":n} for a,n in AGENTS],"agent_count":11,"quality_gate":q,"safety_rules":safety_rules()})
            reply(self,200,result)
        except Exception as e: reply(self,400,{"ok":False,"error":str(e)})
    def log_message(self,*args): return

ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
