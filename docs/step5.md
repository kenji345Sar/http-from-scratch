# step5: クエリ・フォーム・静的ファイル配信

> 前提知識（HTTP / curl / socket の役割分担）は `docs/概念.md` を参照。

## ゴール

- step4 までは「method と path だけで分岐」していた。
- step5 では:
  1. URL のクエリ文字列（`?name=tsk`）を辞書として取り出す
  2. POST のフォームデータ（`a=1&b=2`）を辞書として取り出す
  3. `static/` 配下の実ファイルを `/static/*` で配信する
- URL デコード (`hello%20world` → `"hello world"`) と MIME 推定
  (`.css` → `text/css`) は、標準ライブラリの `urllib.parse` / `mimetypes` に
  任せる。

## やること

1. `parse_qs_simple(query)` を作る。`a=1&b=2` を `{"a": "1", "b": "2"}` にする。
   パーセントエンコーディング (`%20` → スペース等) は `unquote_plus` に丸投げ。
2. `parse_request` で:
   - リクエストラインから `?` で `pure_path` と `query_string` を分割
   - `query_string` を辞書化して `req["query"]` に入れる
   - `Content-Type: application/x-www-form-urlencoded` のときだけ
     body も辞書化して `req["form"]` に入れる
3. ハンドラを書き換える:
   - `handle_hello(req)` は `req["query"].get("name", "stranger")` を使う
   - `handle_submit(req)` は `req["form"]` を表示する
4. 静的ファイル配信:
   - `static/` ディレクトリを作る
   - `/static/foo.css` のような GET を、`static/foo.css` の中身で返す
   - Content-Type は `mimetypes.guess_type` で拡張子から決める
   - `../` で `static/` の外を読まれないようガード

## クエリ・フォームの構造

両者は **同じフォーマット** (`a=1&b=2&...`) で、置き場所だけが違う。

| | 置き場所 | 例 |
|---|---|---|
| クエリ | URL の `?` 以降 | `GET /hello?name=tsk` |
| フォーム | POST body | `POST /submit\n\na=1&b=2` |

なので、パース関数は 1 つでよい (`parse_qs_simple`)。

```python
parse_qs_simple("name=tsk&age=10")
# → {"name": "tsk", "age": "10"}

parse_qs_simple("name=hello%20world")
# → {"name": "hello world"}  # unquote_plus が %20 → スペースに変換
```

## 静的ファイルの組み立て

```python
def handle_static(req):
    rel = req["path"][len("/static/"):]
    target = (STATIC_DIR / rel).resolve()
    # ../ で外に出ようとしたら 403
    try:
        target.relative_to(STATIC_DIR)
    except ValueError:
        return text("forbidden\n", status=403)
    if not target.is_file():
        return text("not found\n", status=404)
    content_type, _ = mimetypes.guess_type(target.name)
    return 200, {"Content-Type": content_type or "application/octet-stream"}, target.read_bytes()
```

- ファイルは **バイト列でそのまま** 返す (HTML / CSS / 画像 / バイナリ問わず)
- Content-Type は拡張子から決まる (`.css` → `text/css`、`.png` → `image/png`)
- セキュリティ最低限: `relative_to` で `static/` 外を弾く

## 実行手順

```
cd /Users/apple/Desktop/Site/http-from-scratch
python3 server.py
```

別ターミナル:

```
# クエリ
curl 'http://127.0.0.1:8080/hello'                       # → hi, stranger!
curl 'http://127.0.0.1:8080/hello?name=tsk'              # → hi, tsk!
curl 'http://127.0.0.1:8080/hello?name=hello%20world'    # → hi, hello world!

# フォーム
curl -X POST -d 'a=1&b=2&name=apple' 'http://127.0.0.1:8080/submit'
# → received form: {'a': '1', 'b': '2', 'name': 'apple'}

# 静的ファイル
curl -i 'http://127.0.0.1:8080/static/index.html'   # text/html
curl -i 'http://127.0.0.1:8080/static/style.css'    # text/css
curl -i 'http://127.0.0.1:8080/static/hello.txt'    # text/plain
curl -i 'http://127.0.0.1:8080/static/nope.png'     # 404
```

URL は **必ずシングルクォート `' '` で囲む**（step1 と同じ理由）。
ブラウザで `http://127.0.0.1:8080/static/index.html` を開くと、
CSS まで自動で読み込まれて見た目が付くのが分かる。

## 確認すること

- `/hello?name=tsk` の `name=tsk` が **`req["query"]` に辞書として入る**
- `%20` などのパーセントエンコーディングが **デコードされる**
- `POST /submit` の body が **`req["form"]` に辞書として入る**
- `/static/*.css` の Content-Type が `text/css` になる（拡張子で MIME が変わる）
- `static/` の外を読もうとしても 403 / 404 で弾かれる

## ここまでで割り切っていること

- multipart/form-data (ファイルアップロード) は扱わない
- JSON body の自動パースもしない (`json.loads` を handler で呼べばよい話)
- ファイルは丸ごとメモリに読んで返している。大きなファイルのストリーミングは扱わない
- 静的配信に Last-Modified / ETag / If-Modified-Since などのキャッシュ制御はない

これらも Flask / Django なら裏でやってくれているが、今回の手作りでは触らない。

## ここで Flask に近づいた点

Flask の view 関数で同じことを書くと:

```python
@app.route("/hello")
def hello():
    name = request.args.get("name", "stranger")     # ← req["query"]
    return f"hi, {name}!"

@app.route("/submit", methods=["POST"])
def submit():
    form = request.form                              # ← req["form"]
    return f"received form: {dict(form)}"

# 静的ファイルは Flask が自動で static/ から配信する
```

つまり Flask の `request.args` / `request.form` がやっていることは、
step5 で書いた `parse_qs_simple` + `parse_request` の流れと同じこと。
Flask がやってくれているのを、自分の手で組み立て直しただけ。

## 次の step へ

step6 では、ここまで作った
「parse → dispatch → ハンドラ → build_response」のうち、
**「parse と build_response」だけをサーバ側に残し、「ハンドラと dispatch」を
WSGI アプリとして外に切り出す**。
これで自分の server.py の上に Flask アプリを乗せられる形になる。
