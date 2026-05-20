# step4: ステータス + ヘッダ + ボディでレスポンスを組み立てる

> 前提知識（HTTP / curl / socket の役割分担）は `docs/概念.md` を参照。

## ゴール

- step3 では handler は「ボディ文字列」しか返せなかった。
  ステータスは 200/404 固定、Content-Type も text/plain 固定。
- step4 では handler が **`(status, headers, body)` の三つ組**を返せるようにする。
- 任意ステータス（200 / 302 / 404 / 500 …）、任意 Content-Type、追加ヘッダ
  （Location など）を扱えるようにする。
- Content-Length を body のバイト数から自動算出する。

## やること

1. レスポンス用ヘルパーを用意する。
   - `text(body, status=200)`: text/plain
   - `html(body, status=200)`: text/html
   - `redirect(location, status=302)`: Location ヘッダ付き、ボディ空
2. ハンドラの返り値を `(status, headers, body)` に統一する。
3. `build_response(status, headers, body)` を、任意ステータス・任意ヘッダ・
   バイト列ボディ対応に拡張する。Content-Length は body 長から自動算出。

## 変更前後の比較

**step3 まで:**

```python
def handle_hello(req):
    return "hi there!\n"          # ボディ文字列だけ

# build_response: ステータスは 200/404 のみ、Content-Type は固定
```

**step4:**

```python
def handle_hello(req):
    return text("hi there!\n")    # (200, {"Content-Type": "..."}, b"...")

def handle_html_demo(req):
    return html("<h1>...</h1>")   # Content-Type を text/html に切り替え

def handle_old(req):
    return redirect("/hello")     # 302 + Location: /hello
```

ヘッダ・ステータスを **ハンドラ側で決められる**ようになる。
ここでようやく「レスポンスを組み立てる」と呼べる状態になる。

## レスポンス組み立てルール（build_response）

| 項目 | やっていること |
|---|---|
| ステータス行 | `HTTP/1.1 {status} {REASON[status]}\r\n` |
| ヘッダ | 与えられた dict をそのまま `name: value\r\n` で並べる |
| Content-Length | 渡されていなければ `len(body)` から自動算出 |
| Connection | 渡されていなければ `close` を入れる |
| 終わり | 空行 `\r\n` のあとに body を連結 |

`REASON` 辞書には 200 / 302 / 400 / 404 / 500 を入れている。必要に応じて拡張。

## 実行手順

サーバ起動:

```
cd /Users/apple/Desktop/Site/http-from-scratch
python3 server.py
```

別ターミナル:

```
curl -i 'http://127.0.0.1:8080/'         # 200 text/plain
curl -i 'http://127.0.0.1:8080/hello'    # 200 text/plain
curl -i 'http://127.0.0.1:8080/html'     # 200 text/html
curl -i 'http://127.0.0.1:8080/old'      # 302 Found + Location: /hello
curl -iL 'http://127.0.0.1:8080/old'     # -L でリダイレクト先まで自動追跡
curl -i -X POST -d 'a=1' 'http://127.0.0.1:8080/submit'
curl -i 'http://127.0.0.1:8080/unknown'  # 404 Not Found
```

URL は **必ずシングルクォート `' '` で囲む**（step1 と同じ理由）。

## 確認すること

- `/html` のレスポンスヘッダに `Content-Type: text/html; charset=utf-8` が
  出ること（**ハンドラ側で Content-Type を切り替えられる**）
- `/old` が `302 Found` + `Location: /hello` を返すこと
- `-L` を付けると curl が自動で `/hello` を取りに行くこと（リダイレクト動作）
- ボディの長さに関わらず `Content-Length` が自動で正しく付くこと

## ここまでで割り切っていること

- クエリ文字列・フォームデータの取り出しはまだ（step5）
- 静的ファイル配信はまだ（step5）
- WSGI 互換にはなっていない（step6）
- Cookie・セッションは扱わない（このプロジェクトの範囲外）

## ここで Flask に近づいた点

Flask のハンドラはこういう形:

```python
@app.route("/old")
def old():
    return redirect("/hello")    # (302, headers, b"") 相当を返している

@app.route("/html")
def html_view():
    return "<h1>...</h1>", 200, {"Content-Type": "text/html"}
```

step4 の自前 handler の返り値 `(status, headers, body)` は、Flask の
view 関数の戻り値とほぼ同じ構造をしている。レスポンス組み立ては
ここまでで Flask の view 層に近づいている。

## 次の step へ

step5 では、URL のクエリ文字列・POST のフォームデータを辞書化する処理と、
`/static/*` のような静的ファイル配信を追加する。
