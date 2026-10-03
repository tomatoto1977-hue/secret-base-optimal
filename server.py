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

def simulation(command, learning_context="", evaluation_history=None, must_improve=None):
    evaluation_history=evaluation_history or []
    must_improve=must_improve or []
    candidates=[
        "知らないうちに増えるスマホの設定・通知を整理する方法",
        "買い物前30秒で無駄買いを減らすチェック法",
        "冷蔵庫の食材ロスを減らす3分ルール",
        "電気代を下げるために最初に確認したい3項目",
        "時間を奪う小さな習慣を1つ減らす方法",
        "サブスク以外の固定費を見直す意外なポイント",
        "毎月の出費を回数で見える化する方法",
        "知らないと損する無料サービスの安全な使い分け"
    ]
    prior=" ".join(str(x.get("theme","")) for x in evaluation_history if isinstance(x,dict))
    idx=(len(evaluation_history)*3 + len(command)) % len(candidates)
    theme=next((candidates[(idx+i)%len(candidates)] for i in range(len(candidates)) if candidates[(idx+i)%len(candidates)] not in prior), candidates[idx])
    improvements=" / ".join(str(x) for x in must_improve[-5:]) or "前回評価なし"
    text=(
        "【統括AI】前回評価を読み込み、同じテーマ・同じ構成を避けて制作。\n"
        f"【今回テーマ】{theme}\n"
        "【市場調査AI】需要・普遍性・独自性・安全性を確認。\n"
        "【企画AI】0-2秒フック→具体例→実行手順→保存CTA。\n"
        "【動画制作AI】9:16、1画面1メッセージ、画面変化を明確化。\n"
        "【編集AI】前回の低評価項目を優先改善し、固定テンプレートを回避。\n"
        f"【前回からの必須改善】{improvements}\n"
        "【権利ゲート】人物・音源・画像等の権利不明素材は使用しない。\n"
        f"【ユーザー指示】{command}\n"
        f"【学習コンテキスト】{learning_context[-5000:]}"
    )
    return {"mode":"simulation_backend","model":None,"title":theme,"summary":"成果物評価を反映した次世代制作計画","deliverable":"人間承認前の制作計画","text":text}

def ai_plan(command, learning_context="", evaluation_history=None, must_improve=None):
    evaluation_history=evaluation_history or []
    must_improve=must_improve or []
    if not API_KEY: return simulation(command, learning_context, evaluation_history, must_improve)
    prompt=f"""あなたは秘密基地・最適版の統括AIです。
11担当（統括、市場調査、競争戦略、企画、情報収集、予算、文章化、エビデンス、動画制作、編集、実装）を統括してください。
テーマは節約に限定せず、毎日の情報から有用な題材を選びます。
特定人物、とくに芸能人への依存や無断利用は禁止。権利不明の画像・動画・音源・文章・キャラクターは使用禁止。
トレンドは構造のみ学習し、元コンテンツをコピーしません。
出典・確認日時を残し、公開・外部操作は人間承認で停止します。
95点品質ゲート：事実性25、目的適合20、具体性20、伝達性15、実装可能性10、安全性10。95点未満なら改善案を出してください。
今回の生成では、以下の成果物評価・失敗学習を最優先で反映してください。
学習コンテキスト：{learning_context[-6000:]}
過去評価：{json.dumps(evaluation_history[-10:],ensure_ascii=False)}
次回必須改善：{json.dumps(must_improve[-15:],ensure_ascii=False)}
ルール：
1. 過去評価の失敗点を明示的に改善すること。
2. 過去に作ったテーマ・切り口・構成を可能な限り避けること。
3. 前回と何が変わったかを「今回の改善点」として成果物内に明記すること。
4. 低評価項目を優先順位付きで改善すること。
5. 学習したと言うだけでなく、具体的な出力差として反映すること。
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
            reply(self,200,{"ok":True,"service":"secret-base-optimal-api","version":"2.1.0","ai_configured":bool(API_KEY),"model":MODEL,"external_actions":False,"agent_count":11,"quality_gate":"95/100"})
        else: reply(self,404,{"ok":False})
    def do_POST(self):
        if self.path!="/run": reply(self,404,{"ok":False}); return
        try:
            n=int(self.headers.get("Content-Length","0")); data=json.loads(self.rfile.read(n) or b"{}")
            command=str(data.get("command","")).strip() or "新しい成果物を企画・制作してください"
            learning_context=str(data.get("learning_context",""))
            evaluation_history=data.get("evaluation_history",[]) if isinstance(data.get("evaluation_history",[]),list) else []
            must_improve=data.get("must_improve",[]) if isinstance(data.get("must_improve",[]),list) else []
            result=ai_plan(command,learning_context,evaluation_history,must_improve)
            q=gate(result.get("text",""))
            result.update({"ok":True,"command":command,"human_approval_required":True,"external_posting":False,"agents":[{"role":a,"name":n} for a,n in AGENTS],"agent_count":11,"quality_gate":q,"safety_rules":safety_rules(),"learning_applied":bool(learning_context or evaluation_history or must_improve),"learning_feedback_count":len(evaluation_history),"mandatory_improvements":must_improve[-10:]})
            reply(self,200,result)
        except Exception as e: reply(self,400,{"ok":False,"error":str(e)})
    def log_message(self,*args): return

ThreadingHTTPServer(("0.0.0.0",PORT),Handler).serve_forever()
