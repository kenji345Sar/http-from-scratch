# step3: パス + メソッドでハンドラを呼ぶ（ルーティング）

> 前提知識（HTTP / curl / socket の役割分担）は `docs/概念.md` を参照。

## ゴール

- step2 でパースして取り出した `method` と `path` を使って、
  「リクエストごとに呼ぶ関数を切り替える」しくみを作る。
- これが Flask / Django の `@app.route('/...')` がやっていることの本体。
- 一致するルートがないリクエストには 404 を返す。

## やること

1. ハンドラ関数を `req -> body文字列` の形で書く。
2. `ROUTES` 辞書に `(method, path) → handler` を登録する。
3. `dispatch(req)` がリクエストから handler を選び、`(status, body, handler名)` を返す。
4. 一致するルートがなければ 404 を返す。
5. クエリ文字列（`?name=tsk`）はルーティングに使わない（取り出しは step5）。

## なぜ「method + path」のペアでルーティングするか

HTTP では「同じ path でも method が違えば別の意味」。

| method + path | 一般的な意味 |
|---|---|
| `GET /posts` | 投稿一覧を取得 |
| `POST /posts` | 投稿を作成 |
| `GET /posts/1` | 投稿を 1 件取得 |
| `DELETE /posts/1` | 投稿を削除 |

なので「パスだけで分岐」では足りない。`(method, path)` のペアで分岐するのが
HTTP らしいルーティング。

## 実装パターン

```python
ROUTES = {
    ("GET", "/"):        handle_root,
    ("GET", "/hello"):   handle_hello,
    ("POST", "/submit"): handle_submit,
}

def dispatch(req):
    method = req["method"]
    path = req["path"].split("?", 1)[0]   # クエリは無視
    key = (method, path)
    if key in ROUTES:
        return 200, ROUTES[key](req), ROUTES[key].__name__
    return 404, handle_not_found(req), "handle_not_found"
```

これだけ。Flask の `@app.route` がやっていることの骨格はここに収まっている。

## レスポンス組み立てについて（step4 で本格化）

step3 では、ルーティングを動かすために最小限の `build_response(status, body)` を
作るが、ステータスコードは 200 / 404 だけ、ヘッダも固定。
**この crude な版を step4 で拡張する。**

| 段階 | レスポンスの作り方 |
|---|---|
| step3 | `build_response(status, body)` だけ。ステータスは 200/404、Content-Type は固定 |
| step4 | ハンドラがヘッダや任意ステータスを返せるよう一段拡張、Content-Length をきちんと意識 |

## 実行手順

サーバ起動：

```
cd /Users/apple/Desktop/Site/http-from-scratch
python3 server.py
```

別ターミナルから curl で叩く：

```
curl -i 'http://127.0.0.1:8080/'
curl -i 'http://127.0.0.1:8080/hello'
curl -i 'http://127.0.0.1:8080/hello?name=tsk'
curl -i -X POST -d 'a=1&b=2' 'http://127.0.0.1:8080/submit'
curl -i 'http://127.0.0.1:8080/unknown'
```

URL は **必ずシングルクォート `' '` で囲む**（step1 と同じ理由）。
`-i` を付けるとレスポンスヘッダも見える。

## 確認すること

クライアント側 (`curl -i` の出力):

| リクエスト | 期待されるレスポンス |
|---|---|
| `GET /` | `200 OK` / `hello from http-from-scratch` |
| `GET /hello` | `200 OK` / `hi there!` |
| `GET /hello?name=tsk` | `200 OK` / `hi there!`（クエリは無視） |
| `POST /submit -d 'a=1&b=2'` | `200 OK` / `received: a=1&b=2` |
| `GET /unknown` | `404 Not Found` / `not found: GET /unknown` |

サーバ側ログには、ルーティングの結果が並ぶはず：

```
--- request from 127.0.0.1:51877 ---
GET /hello?name=tsk HTTP/1.1
→ matched: ('GET', '/hello') → handle_hello → 200 OK
--- request 92 bytes ---
```

404 の場合:

```
--- request from 127.0.0.1:51880 ---
GET /unknown HTTP/1.1
→ no route: ('GET', '/unknown') → handle_not_found → 404 Not Found
--- request 80 bytes ---
```

## ここまでで割り切っていること

- 動的なパス（`/posts/:id` の `:id` 部分）はまだ。完全一致のみ。
- 同一 path に複数 method を持たせる構成（Flask の `methods=['GET', 'POST']`）も
  まだ。1 ルート 1 method の素直な辞書。
- ハンドラはまだ「ボディ文字列を返す」だけ。ヘッダや任意ステータスを返したい
  ときは step4 で拡張する。
- パスのクエリ部分は無視。`/hello?name=tsk` の `name=tsk` を取り出す処理は step5。
- 不正なリクエストへのエラー応答（400 など）は返さず、例外で落ちる。これも step5 以降。

これらは「Flask / Django が裏でやってくれていること」のうち、step3 ではまだ
自分の手で触らない部分。

## 次の step へ

step4 では、ハンドラが「ボディだけ」ではなく「ステータス + ヘッダ + ボディ」を
返せるよう拡張し、レスポンス組み立て側を一段ちゃんと作る。
任意の Content-Type、任意の Content-Length、リダイレクト相当などを
扱えるようにする。
