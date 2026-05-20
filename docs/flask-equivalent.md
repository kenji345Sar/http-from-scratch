# Flask で書くとどうなるか / 何が内包されているか

step1〜6 で自分の手で組み上げたものと、同じ振る舞いを Flask で書くと
どれだけ短くなるか、そして「短く書ける」とは Flask が裏で何をやってくれて
いるかを並べて見るためのドキュメント。

## 同じアプリを Flask で書くと

リポジトリ直下に [`flask_equivalent.py`](../flask_equivalent.py) として
実行できるコードを置いてある。中身はこれだけ:

```python
from flask import Flask, redirect, request

app = Flask(__name__, static_folder="static", static_url_path="/static")

@app.route("/")
def root():
    return "hello from Flask\n"

@app.route("/hello")
def hello():
    name = request.args.get("name", "stranger")
    return f"hi, {name}! (via Flask)\n"

@app.route("/html")
def html():
    return ("<h1>HTML response</h1>\n", 200,
            {"Content-Type": "text/html; charset=utf-8"})

@app.route("/old")
def old():
    return redirect("/hello")

@app.route("/submit", methods=["POST"])
def submit():
    return f"received form: {dict(request.form)}\n"

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080)
```

これだけで step1〜6 と同じ機能が揃う。
静的ファイル配信 (`/static/...`) は書いていないが、Flask 側が自動で
`static_folder` から配信する。

## 実行手順

自前 `server.py` と同じポート 8080 を使うので、片方を起動するときは
もう片方を止めること。

```
cd /Users/apple/Desktop/Site/http-from-scratch
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python flask_equivalent.py
```

別ターミナルから curl で叩く（URL はシングルクォート必須）:

```
curl 'http://127.0.0.1:8080/'                       # hello from Flask
curl 'http://127.0.0.1:8080/hello?name=tsk'         # hi, tsk! (via Flask)
curl -i 'http://127.0.0.1:8080/html'                # 200 text/html
curl -i 'http://127.0.0.1:8080/old'                 # 302 → /hello
curl -X POST -d 'a=1&b=2' 'http://127.0.0.1:8080/submit'
curl -i 'http://127.0.0.1:8080/static/style.css'    # 200 text/css
curl -i 'http://127.0.0.1:8080/unknown'             # 404
```

止めるときは `Ctrl+C`。

## 自前 server.py と比べた振る舞いの違い（細部）

機能は同じだが、Flask は自前よりリッチなレスポンスを返す。
これも「Flask が裏で勝手にやってくれていること」の一部:

| 違い | 自前 server.py | Flask |
|---|---|---|
| `Server` ヘッダ | 付けていない | `Server: Werkzeug/x.x Python/x.x` を自動付与 |
| `Date` ヘッダ | 付けていない | 現在時刻を RFC 1123 形式で自動付与 |
| 404 のボディ | プレーンテキスト | `<!doctype html><html>...</html>` の HTML エラーページ |
| 302 のボディ | 空 | 「ここを開いてください」リンク入り HTML |
| `Content-Disposition`（静的ファイル） | 付けていない | `inline; filename=style.css` を自動付与 |
| reason 文字列 | `302 Found` | `302 FOUND`（大文字）— 振る舞いとして等価 |

つまり Flask は同じ機能を「より丁寧に」返している。
このプロジェクトの目的は機能の最小集合を理解することなので、自前側は素朴な
レスポンスのままにしてある。

## 何が「内包されている」か

Flask で書いた行数（コメント抜きで 20 行ほど）と、自前の `server.py` + `app.py`
（300 行強）の差は、Flask が import の裏で次の機能を全部やっているから。

| 機能 | このプロジェクトのどこ | Flask（+ Werkzeug）の担当 |
|---|---|---|
| TCP の listen / accept / recv / send | step1 `socket` まわり | Werkzeug `serving.py`（dev 用）、本番は gunicorn / waitress |
| HTTP テキストのパース（リクエスト行・ヘッダ・ボディの分解） | step2 `parse_request` | Werkzeug `Request` クラス（`werkzeug.wrappers.Request`） |
| ルーティング（method + path → ハンドラ） | step3 `ROUTES` + `dispatch` | `@app.route` デコレータ + Werkzeug の Routing |
| ステータス・ヘッダ・ボディ組み立て | step4 `build_response` + `text`/`html`/`redirect` | Werkzeug `Response` / Flask `make_response` |
| クエリ文字列の辞書化 | step5 `parse_qs_simple` → `req["query"]` | `request.args` |
| POST フォームの辞書化 | step5 `parse_qs_simple` → `req["form"]` | `request.form` |
| URL デコード（`%20` → ' '） | step5 `urllib.parse.unquote_plus` | Werkzeug 側で同じことをしている |
| 静的ファイル配信 | step5 `handle_static` | `static_folder` / `static_url_path` で自動 |
| MIME 推定（拡張子 → Content-Type） | step5 `mimetypes.guess_type` | Werkzeug 側で同じことをしている |
| WSGI 境界（environ / start_response） | step6 `build_environ` + `call_app` | Flask の `wsgi_app` メソッドが満たしている |
| Content-Length の自動付与 | step4/6 `build_response` | Werkzeug `Response` が自動で付ける |

つまり Flask の `from flask import Flask` 1 行の裏には、上の表全部が入っている。

## Flask と自前 server.py の境界

step6 で `server.py` を WSGI 互換にしたので、Flask アプリは自前 `server.py` の
上にそのまま乗る。境界線はここ：

```
                           ┌──────────────────────────────────────┐
                           │  app.py (もしくは Flask アプリ)        │
                           │  ・ルーティング                        │
                           │  ・ハンドラ（view 関数）               │
                           │  ・レスポンス組み立て                  │
                           └──────────────────────────────────────┘
                                       ▲         ▲
                          environ 辞書 │         │ start_response(status, headers)
                                       │         │ + return [body]
                           ┌──────────────────────────────────────┐
                           │  server.py（WSGI ゲートウェイ）        │
                           │  ・TCP socket                        │
                           │  ・HTTP テキストのパース              │
                           │  ・environ 組み立て                   │
                           │  ・HTTP/1.1 レスポンス組み立て        │
                           └──────────────────────────────────────┘
```

- 上の枠が Flask に置き換え可能（同じ WSGI 規約を満たすから）
- 下の枠が gunicorn / waitress に置き換え可能（同じく WSGI ゲートウェイだから）

実運用では、下の枠が **gunicorn**、上の枠が **Flask**、というのが定番構成。
このプロジェクトでは両方の枠を自分の手で書いた。

## おまけ: 自前 server.py の上に Flask アプリを乗せる

`flask_equivalent.py` は Flask の dev サーバ（Werkzeug）で動かしているが、
**自前の `server.py` の上でも同じ Flask アプリは動く**（step6 で WSGI 互換にしたから）。

`server.py` のインポート行と最後だけ書き換える:

```python
# 元: from app import app
# 変更後:
from flask import Flask, request, redirect

app = Flask(__name__, static_folder="static", static_url_path="/static")

@app.route("/")
def root(): return "hello from Flask on my own server.py\n"

@app.route("/hello")
def hello():
    return f"hi, {request.args.get('name', 'stranger')}! (Flask)\n"

# あとは既存の serve_forever(app) がそのまま使える
```

`python3 server.py` で起動して `curl http://127.0.0.1:8080/` を叩くと、
自分が書いた TCP 受け付け → environ 組み立てを経由して、Flask の view 関数が呼ばれる。
**Flask は乗せ換え可能なアプリ層、`server.py` は乗せ換え可能なサーバ層**。

## Flask の中身を読みたくなったら

Flask は薄く、実体の大部分は **Werkzeug**（同じく Pallets が出している HTTP ライブラリ）。
このプロジェクトで自分の手で書いた処理は、Werkzeug のソースを開くと「規模の大きい
実運用版」として並んでいる。

| 自分で書いた処理 | Werkzeug / Flask 側で読むと良い場所 |
|---|---|
| `parse_request` | `werkzeug/wrappers/request.py` の `Request` |
| `build_response` | `werkzeug/wrappers/response.py` の `Response` |
| `ROUTES` / `dispatch` | `werkzeug/routing/` 配下、Flask の `app.py` の `dispatch_request` |
| `build_environ` | `werkzeug/serving.py` の `WSGIRequestHandler` |
| `serve_forever` の socket まわり | `werkzeug/serving.py`、本番は gunicorn 側 |
| WSGI 規約そのもの | PEP 3333 |

リポジトリの入口:

- Flask: <https://github.com/pallets/flask>
- Werkzeug: <https://github.com/pallets/werkzeug>
- PEP 3333（WSGI 仕様）: <https://peps.python.org/pep-3333/>

## まとめ

- **Flask = アプリ層** （ハンドラ + ルーティング + レスポンス補助）
- **Werkzeug = 下回り** （Request / Response / Routing / dev server）
- **gunicorn / waitress = サーバ層** （TCP 受け付け、プロセス管理、WSGI ゲートウェイ）
- このプロジェクトの `app.py` がアプリ層、`server.py` がサーバ層に対応する

step1〜6 で書いたすべては、上の 3 つのどこかに対応していて、Flask を使うと
`import` の裏に隠れる、という関係。
