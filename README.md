# http-from-scratch

HTTPリクエストが Web アプリの処理になるまでを、自分の手で組み上げて、
普段 Flask / Django / FastAPI が当たり前として隠している層を一度ぜんぶ
表に出す学習プロジェクト。

実装言語は Python（標準ライブラリのみ）。フレームワークは使わない。

## 目的

「リクエストが来てレスポンスが返るまで」のあいだに、
普段は意識せずに済んでいる処理を、段階的に自分で書いて確かめる。

- Web フレームワークがやっていることを、自分の手で再現できるようになる
- HTTP が「TCP の上を流れるテキスト」だという感覚を取り戻す
- WSGI まで辿り着くことで、Flask が乗っかっている層を露出させる

## 全体ステップ

| step | テーマ | 何が出てくるか |
|------|-------|--------------|
| step1 | 生 TCP で HTTP リクエストを受け取る | socket、リクエストはただのテキスト |
| step2 | リクエストをパースする | リクエスト行・ヘッダ・ボディの構造 |
| step3 | パス + メソッドでハンドラを呼ぶ | ルーティング |
| step4 | ステータス行・ヘッダ・ボディを組み立てる | レスポンス生成、Content-Length |
| step5 | 静的ファイル配信 / クエリ・フォームの取り出し | MIME、URL デコード、`application/x-www-form-urlencoded` |
| step6 | WSGI 互換のアプリにする | Flask が乗っている層 |

各 step の手順は `docs/stepN.md` に書く。
過去 step の状態は `snapshots/stepN/` に凍結して保存する
（現在のコードは常にリポジトリ直下の `server.py` などにある）。

step1〜6 で自分の手で書いたものを、Flask だとどう書くか / Flask が何を
内包しているかは [`docs/flask-equivalent.md`](docs/flask-equivalent.md) を参照。

## 実行方法（step6 時点）

```
python3 server.py
```

別ターミナルから：

```
curl -v http://127.0.0.1:8080/
```

またはブラウザで `http://127.0.0.1:8080/` を開く。

## ディレクトリ構成

```
http-from-scratch/
├── README.md          # このファイル
├── server.py          # 現時点（最新 step）のサーバ
├── app.py             # step6 で分離した WSGI アプリ
├── static/            # step5 で追加した静的ファイル配信用
├── docs/
│   ├── 概念.md         # HTTP / curl / socket の役割分担（全 step の前提）
│   ├── step1.md       # step1 の手順
│   └── ...            # step2.md 〜 step6.md
└── snapshots/
    ├── step1/         # step1 完了時点のコードを凍結
    └── ...            # step2/ 〜 step6/
```
