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

## 認証・認可シリーズ（続編）

step6 まで終わった `server.py` の上に、認証 (authentication) と
認可 (authorization) を段階的に足していく。
各 step で「自作 → 同じことを現状の製品 (Auth0 / Cognito / Keycloak など)
はどうやっているか」を併記する。

| step | テーマ | 対応する製品・仕様 |
|------|-------|--------------------|
| 概念 | 認証・認可の用語と全体像 | — |
| step1 | Basic 認証 | HTTP 標準 |
| step2 | セッション認証 (Cookie + サーバ側ストア) | Rails/Django/Laravel デフォルト |
| step3 | JWT 認証 (HMAC で署名・検証) | Auth0 / Cognito の access token |
| step4 | 認可 (RBAC) | Auth0 Roles、Cognito Groups、Casbin |
| step5 | OAuth 2.0 / OIDC を 1 本通す | Sign in with Google、Auth0 |
| step6 | パスキー / WebAuthn（**自作なし・概念整理 + ライブラリ利用**） | `py_webauthn`、Auth0 Passkeys、Clerk、Hanko |

ドキュメントは `docs/auth/` 配下に置く。
最初に読むのは [`docs/auth/概念.md`](docs/auth/概念.md)。

## 関連プロジェクト: TLS / 証明書 (隣の層)

本プロジェクトは **HTTP（と TCP）** を自分の手で組む。一方、その下の **TLS / 証明書 / mTLS** は扱わない。同じ curl で観察できる隣接層を触りたい場合は、`../infra-lessons/01-package-delivery/` を参照。

- http-from-scratch: HTTP を **中から** 見る（socket からテキストを読む）
- infra-lessons step-04〜06: TLS を **外から** 組み立てる（nginx を設定し、`ca.crt` / クライアント証明書を配る）

両者は curl の `-v` 出力で同時に見える「同じスタックの隣り合った層」。詳細な対応関係は [`../infra-lessons/01-package-delivery/README.md`](../infra-lessons/01-package-delivery/README.md) の「http-from-scratch との関係」節を参照。

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
├── README.md              # このファイル
├── server.py              # 現時点（最新 step）のサーバ
├── app.py                 # step6 で分離した WSGI アプリ
├── flask_equivalent.py    # 同じ機能を Flask で書いた比較用（要 pip install -r requirements.txt）
├── requirements.txt       # flask 依存
├── static/                # step5 で追加した静的ファイル配信用
├── docs/
│   ├── 概念.md              # HTTP / curl / socket の役割分担（全 step の前提）
│   ├── サーバ起動.md        # php artisan serve / dotnet run などの裏で起きていること
│   ├── 用語集.md            # WSGI / Werkzeug / gunicorn など Python Web の用語
│   ├── 言語別役割対応.md     # gunicorn ≒ Tomcat ≒ Kestrel など PHP/Java/C# との対応表
│   ├── python-メモ.md       # 他言語から来て「Python ここ独特」と感じる箇所
│   ├── flask-equivalent.md  # Flask 版との対応表・実行手順
│   ├── step1.md            # step1 の手順
│   ├── ...                 # step2.md 〜 step6.md
│   └── auth/               # 認証・認可シリーズ（続編）
│       ├── 概念.md          # 用語と全体像（最初に読む）
│       └── stepN.md        # 各 step の手順（順次追加）
└── snapshots/
    ├── step1/             # step1 完了時点のコードを凍結
    └── ...                # step2/ 〜 step6/
```
