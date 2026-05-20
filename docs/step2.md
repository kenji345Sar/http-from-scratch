# step2: リクエストをパースする

> 前提知識（HTTP / curl / socket の役割分担、curl がどう組み立てているか）は
> `docs/概念.md` を参照。

## ゴール

- step1 で「届いたバイト列をそのまま print する」だけだったサーバに、
  **HTTP リクエストとしての構造**を持たせる。
- 受け取った文字列を「リクエスト行」「ヘッダ辞書」「ボディ」に分解し、
  辞書として扱えるようにする。
- ルーティングやレスポンス組み立てはまだ触らない（step3 / step4）。

## やること

1. `parse_request(raw: bytes) -> dict` を作る。
2. `\r\n\r\n` でヘッダ部とボディを分割する。
3. ヘッダ部の 1 行目（リクエスト行）から `method` `path` `version` を取り出す。
4. 残りの行を `: ` で割って `headers` 辞書にする（キーは lower-case）。
5. パースした結果を見やすく表示する。レスポンスは step1 と同じ固定文字列のまま。

## HTTP リクエストの構造（パースの対象）

curl から届く文字列はこういう形をしている。

```
GET /hello?name=tsk HTTP/1.1\r\n   ← リクエスト行
Host: 127.0.0.1:8080\r\n            ← ヘッダ
User-Agent: curl/7.68.0\r\n
Accept: */*\r\n
\r\n                                 ← 空行（ヘッダの終わり）
（ボディ: GET の場合は空）
```

POST の場合は最後にボディが付く。

```
POST /submit HTTP/1.1\r\n
Host: 127.0.0.1:8080\r\n
Content-Type: application/x-www-form-urlencoded\r\n
Content-Length: 7\r\n
\r\n
a=1&b=2
```

つまりパースの基本ロジックは:

- まず `\r\n\r\n` で **ヘッダ部** と **ボディ部** に分ける
- ヘッダ部を `\r\n` で行分割
- 1 行目はスペース 2 個で `method / path / version` に分ける
- 2 行目以降は最初の `:` で `name / value` に分ける

## なぜ step1 のテキストをそのまま扱わないのか

step1 では `print(raw.decode(...))` で生のテキストを目で見ていた。
人間は読めるが、プログラムは「`GET` の場所」「`Host:` の値」を直接参照できない。

辞書になっていれば、

- `req["method"] == "GET"` でメソッド分岐
- `req["headers"]["host"]` で Host を取り出す
- `req["path"]` で `/hello?name=tsk` を取り出す（クエリ分割は step5）

ができるようになり、step3（ルーティング）と step4（レスポンス組み立て）の
材料になる。

## 実行手順

サーバ起動：

```
cd /Users/apple/Desktop/Site/http-from-scratch
python3 server.py
```

別ターミナルから curl で叩く：

```
curl -v 'http://127.0.0.1:8080/'
curl -v 'http://127.0.0.1:8080/hello?name=tsk'
curl -v -X POST -d 'a=1&b=2' 'http://127.0.0.1:8080/submit'
```

URL は **必ずシングルクォート `' '` で囲む**（step1 と同じ理由）。

## 確認すること

サーバ側に、こういう出力が出るはず。

```
--- request from 127.0.0.1:50868 ---
method:  GET
path:    /hello?name=tsk
version: HTTP/1.1
headers:
  host: 127.0.0.1:8080
  user-agent: curl/7.68.0
  accept: */*
body:    (empty)
--- 90 bytes ---
```

POST の場合はボディが空でなくなる。

```
--- request from 127.0.0.1:50870 ---
method:  POST
path:    /submit
version: HTTP/1.1
headers:
  host: 127.0.0.1:8080
  user-agent: curl/7.68.0
  accept: */*
  content-length: 7
  content-type: application/x-www-form-urlencoded
body:    'a=1&b=2'
--- 159 bytes ---
```

「目で見ていた生テキスト」が、**プログラムから扱える辞書**に変わったことを確認する。

## ここまでで割り切っていること（step1 と同じく）

- `recv(4096)` 1 回で読み切れる前提。
  大きな POST ボディや、ヘッダだけ先に届く分割受信は扱わない。
  `Content-Length` を見てボディを読み足す処理は、本格的には step5 以降の話。
- ヘッダ値の RFC 準拠なパース（折り返し行、複数値の同名ヘッダ、引用文字列）は
  やらない。`Host: 127.0.0.1:8080` のような単純な行だけを想定。
- 不正なリクエスト（リクエスト行が壊れている、ヘッダに `:` がない 等）への
  エラーレスポンスは返さない。Python が例外を投げて落ちる動きにしておく。

これらは「`Flask` や `http.server` が裏でやってくれていること」のうち、
step2 ではまだ自分の手で触らない部分。step3 以降で必要になったときに、
**「Python が肩代わりしていない範囲」を一段ずつ広げる**形で進める。

## 次の step へ

step3 では、この辞書から `method` と `path` を取り出して、
「`GET /` なら関数 A を呼ぶ、`POST /submit` なら関数 B を呼ぶ」という
**ルーティング**を自分で書く。
