# step6: WSGI 互換にして、サーバとアプリを分離する

> 前提知識（HTTP / curl / socket の役割分担）は `docs/概念.md` を参照。
> WSGI / PEP 3333 / Werkzeug / environ / gunicorn / waitress などの用語が
> 分からなくなったら `docs/用語集.md` を参照。

## ゴール

- step5 まで、`server.py` の中に「parse → dispatch → ハンドラ → build_response」が
  全部入っていた。
- step6 では、その内側を **WSGI アプリ（`app.py`）** として外に切り出し、
  `server.py` は「TCP と WSGI のあいだの橋渡し」だけにする。
- これで自分の `server.py` の上に、**Flask など他の WSGI アプリも乗せられる** 形になる。

## WSGI とは

PEP 3333 で定義された、**Python の Web サーバとアプリの取り決め**。
ほぼ一言で言うと:

> アプリは `app(environ, start_response)` という関数。
> environ はリクエスト情報の辞書、start_response はレスポンスのステータスとヘッダを
> 返す関数。アプリの戻り値はボディのバイト列イテラブル。

これだけ。Flask / Django / Bottle / FastAPI (の WSGI 互換ラッパー) はみんなこの
取り決めに合わせて動いている。逆に **WSGI さえ守れば、サーバとアプリは独立して
入れ替え可能**。

## やること

1. `server.py` から、ルーティングとハンドラを **すべて消す**。
2. 代わりに次の 3 つだけを残す:
   - `parse_request` （step2 と同じ）
   - `build_environ` （parsed request → WSGI environ 辞書）
   - `call_app` （`app(environ, start_response)` を呼んで `(status, headers, body)` を取り出す）
   - `build_response` （WSGI 流の `(status, headers, body)` を HTTP/1.1 バイト列に）
3. 新規 `app.py` を作り、step5 までのハンドラを WSGI 形式に書き直す。
4. `server.py` は `from app import app` してそれを `serve_forever(app)` に渡す。

## environ 辞書のキー（PEP 3333 抜粋）

`server.py` の `build_environ` が組み立てている辞書はこういう中身:

| キー | 例 | 意味 |
|---|---|---|
| `REQUEST_METHOD` | `"GET"` | HTTP メソッド |
| `PATH_INFO` | `"/hello"` | クエリを除いたパス |
| `QUERY_STRING` | `"name=tsk"` | クエリ部分（`?` は含まない） |
| `CONTENT_TYPE` | `"application/x-www-form-urlencoded"` | リクエストヘッダ `Content-Type`（あれば） |
| `CONTENT_LENGTH` | `"7"` | リクエストヘッダ `Content-Length`（あれば） |
| `SERVER_NAME` / `SERVER_PORT` | `"127.0.0.1"` / `"8080"` | サーバの宛先 |
| `SERVER_PROTOCOL` | `"HTTP/1.1"` | プロトコル |
| `REMOTE_ADDR` / `REMOTE_PORT` | クライアント情報 | |
| `HTTP_*` | `HTTP_USER_AGENT` など | リクエストヘッダ全般（名前は大文字 + アンダースコア） |
| `wsgi.input` | `BytesIO` | リクエストボディを読むファイルライク |
| `wsgi.errors` | `sys.stderr` | エラーログ先 |
| `wsgi.url_scheme` | `"http"` | スキーム |

WSGI アプリは **この辞書からほしい情報を取り出す**だけ。
リクエストのパースは、サーバ側ですでに終わっている。

## start_response の動き

WSGI アプリは「ステータスとヘッダを返す」ためにこんな呼び方をする:

```python
def app(environ, start_response):
    body = b"hello\n"
    start_response("200 OK", [("Content-Type", "text/plain; charset=utf-8")])
    return [body]
```

サーバ側 (`server.py` の `call_app`) はこれを次の流れで処理する:

1. `app(environ, start_response)` を呼ぶ
2. `start_response` がサーバ側に status と headers を「告げ知らせる」
3. `app` の戻り値（バイト列のイテラブル）を順に読んで body を組み立てる
4. status + headers + body を HTTP/1.1 として送り返す

## server.py に残ったもの / app.py に出ていったもの

| | step5 までの server.py | step6 の server.py | step6 の app.py |
|---|---|---|---|
| TCP socket | ✅ | ✅ | |
| parse_request | ✅ | ✅ | |
| build_environ | | ✅（新規） | |
| call_app | | ✅（新規） | |
| build_response | ✅ | ✅（WSGI 流に） | |
| ハンドラ（view 関数） | ✅ | | ✅ |
| dispatch（ルーティング） | ✅ | | ✅ |
| クエリ・フォームのパース | server 内 | | ✅（必要な view が呼ぶ） |
| 静的ファイル配信 | server 内 | | ✅ |

「サーバ」と「アプリ」の境界がはっきり分かれた状態。

## 実行手順

```
cd /Users/apple/Desktop/Site/http-from-scratch
python3 server.py
```

curl での確認（step5 と同じ URL でだいたい同じ振る舞い）:

```
curl 'http://127.0.0.1:8080/'              # hello from WSGI app
curl 'http://127.0.0.1:8080/hello?name=tsk'  # hi, tsk! (via WSGI)
curl -i 'http://127.0.0.1:8080/html'
curl -i 'http://127.0.0.1:8080/old'        # 302 → /hello
curl -X POST -d 'a=1&b=2' 'http://127.0.0.1:8080/submit'
curl -i 'http://127.0.0.1:8080/static/style.css'
curl -i 'http://127.0.0.1:8080/unknown'    # 404
```

URL は **必ずシングルクォート `' '` で囲む**（step1 と同じ理由）。

## 確認すること

- `server.py` の中に **ルーティングコード（`ROUTES`）が一切ない**
- `app.py` の中に **socket / recv / sendall が一切ない**
- 両者は `environ` 辞書と `start_response` の取り決めだけで繋がっている
- それでも step5 と同じレスポンスが返る

## Flask アプリを乗せてみる（オプション）

WSGI 互換にした最大の恩恵は、**自分の `server.py` の上に Flask アプリを
そのまま乗せられる**こと。

```
pip install flask
```

`server.py` の `from app import app` を消して、こう書き換えれば動く:

```python
from flask import Flask

flask_app = Flask(__name__)

@flask_app.route("/")
def root():
    return "hello from Flask, running on my own server.py\n"

@flask_app.route("/hello")
def hello():
    from flask import request
    name = request.args.get("name", "stranger")
    return f"hi, {name}! (via Flask)\n"

if __name__ == "__main__":
    serve_forever(flask_app)
```

Flask が「自分で書いた小さな server.py」の上で動く。
裏で gunicorn や waitress がやっているのは、ほぼ今の `server.py` と同じこと
（接続多重化やプロセス管理の規模が違うだけ）。

## ここまでで分かったこと

step1〜6 で書いた `server.py` と `app.py` は、ふだん `pip install flask` で
import の裏に隠れていた次の層を、ぜんぶ自分の手で展開したもの:

| 隠されていた層 | このプロジェクトのどこ |
|---|---|
| TCP の listen / accept / recv / send | step1: `socket` まわり |
| HTTP テキストのパース | step2: `parse_request` |
| ルーティング (`@app.route`) | step3: `ROUTES` + `dispatch` |
| レスポンス組み立て | step4: `build_response` + `text` / `html` / `redirect` |
| クエリ・フォーム・MIME | step5: `parse_qs_simple` + `mimetypes` |
| サーバとアプリの境界（WSGI） | step6: `build_environ` + `start_response` |

Flask / Django を使うと、上の表のすべてが import の裏に隠れる。
このプロジェクトのコードを読み返すと、フレームワークが何を引き受けているかが
見える形になっているはず。

## おまけ: 改善余地（今回は触らない）

- 並行接続: 今は accept → 処理 → close の直列 1 本だけ。
  実運用では threading / asyncio / プロセスプールが入る（gunicorn 等の役目）。
- Keep-Alive: 今は `Connection: close` 固定。HTTP/1.1 の本来は 1 接続で複数
  リクエストを処理できる。
- HTTPS: TLS 終端は今回扱わず、平文 HTTP のみ。
- HTTP/2 や HTTP/3 は別物の仕組みで、WSGI ではなく ASGI 系の世界。
