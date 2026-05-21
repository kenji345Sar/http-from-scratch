# auth step5: OAuth 2.0 / OIDC を 1 本通す（モック IdP）

## ゴール

実 Provider（Google / GitHub / Auth0）に登録せず、**`app.py` の中に IdP も
クライアントも両方立てて** OAuth 2.0 の **Authorization Code Flow** を
端から端まで通す。

学習目的なので簡略化する:

- **PKCE は省略**（本番では必須。後述）
- **同意画面は省略**（自動承認）
- **ユーザー DB / セッションは既存のもの** をそのまま使う
- **クライアントは 1 つだけ事前登録**

このフローに登場する役割を全部 1 プロセスで演じる、いわば学習用の
「**ひとり OIDC**」。

## このステップの位置づけ (step3 との関係)

一言でいうと:

> **step5 は「自分のアプリが、ユーザーのパスワードを一切受け取らずに
> JWT を手に入れる」仕組み**。step3 と最終的に JWT を持つことは同じだが、
> **取り方が違う**。

### step3 と step5 の比較

| | step3 (JWT 直発行) | step5 (OAuth/OIDC) |
|---|---|---|
| 自分のアプリは何を見る | **パスワードを直接受け取る** | パスワードは見ない |
| パスワードを検証するのは | 自分のアプリ | **IdP (= 別サービス)** |
| 最終的に持つもの | access_token (JWT) | access_token + id_token (JWT) |
| 流れ | `POST /api/token (user, pw)` → JWT | `/oidc/start` → IdP にログイン → code → `/oauth/token` で code を JWT に交換 |

### なぜ遠回りをするのか (= step5 の値打ち)

「**パスワードに触らない**」こと自体が価値。これで次が成立する:

1. **自分のアプリが侵害されても、ユーザーのパスワードは漏れない**
   (そもそも保存していないし、受け取ってもいない)
2. **「Google でログイン」「GitHub でログイン」が実現する**
   IdP を Google にすれば、ユーザーは Google にパスワードを入れるだけ。
   自分のアプリはトークンしか見ない
3. **SSO が成り立つ** (詳細は次節)
4. **MFA / パスキー / リスクベース認証** など、認証の進化を
   **IdP が一手に引き受ける**。自分のアプリはトークン検証だけしていればよい

### 「JWT を自前で取得しない」とはどういう意味か

正確には:

- **自前で JWT を発行しない** (= IdP に発行を任せる)
- **JWT を受け取って検証はする** (= 受信側の仕事は残る)

→ step3 で書いた `jwt_decode()` 相当のコードは step5 でも生きており、
`/api/me` がそのまま使えている。

### 学習用 vs 実運用の役割分担

今回の `app.py` は **IdP と RP を同じプロセスにまとめて演じている**。
本来は別ホスト・別ベンダーに分かれる。

| URL | 役 | 本来は誰が運用するか |
|---|---|---|
| `/oauth/authorize` `/oauth/token` `/login` `USERS` `ROLES` | **IdP** | Google / Microsoft / Auth0 / Okta / Keycloak など |
| `/oidc/start` `/oidc/callback` `/api/me` | **RP (= 自分のアプリ)** | 自分 |

つまり実運用で「step5 をやる」と言うとき、**自分が書くのは RP 側だけ**。
IdP 側は製品 (Google / Auth0 / Keycloak) に任せる。

## SSO との関係

「SSO したい」というニーズは、ほぼ step5 (の RP 側) を実装することに帰着する。

### SSO とは

> **1 回どこかでログインしたら、同じ IdP を信頼する複数のアプリに、
> ログイン無しで入れる**

### なぜ「RP を書くだけ」で SSO になるか

`/oauth/authorize` には次の挙動がある:

> **ユーザーが IdP に既にログインしている (= IdP 側に session cookie がある) なら、
> ログイン画面を出さずに、その場で code を返す**

これが SSO の本質。

```
App1 を初めて開く:
  ブラウザ → App1 → /oauth/authorize → (IdP がログイン画面を出す) → ログイン → code → App1

その直後に App2 を初めて開く:
  ブラウザ → App2 → /oauth/authorize → (IdP は既ログインを認識) → 即 code → App2
                                          ★ ここでログイン画面を出さない
```

ユーザー視点では「App1 でログインしたら App2 もパス無しで入れた」 = SSO。

### 今回の step5 で SSO を見るには

step5 の実装は 1 アプリ (RP と IdP を同居) しかないので、SSO そのものは
観察できていない。SSO を実機で見るには **同じ IdP を信頼する RP が 2 つ**
あればよく、たとえば:

```
App1 (RP)   port 9001  → IdP (port 8080) の /oauth/authorize を叩く
App2 (RP)   port 9002  → 同じ IdP の /oauth/authorize を叩く
```

両方とも `/oidc/start` `/oidc/callback` を書けば、IdP 側で同じ `sid`
(step2 のセッション) が生きている限り、2 番目のアプリではログイン画面が
出ない。

### 実務での「SSO したい」の意味

| ケース | やること |
|---|---|
| 自社の複数アプリで SSO したい | 共通 IdP (Keycloak / Auth0 / Okta / Azure AD) を立てる、各アプリは RP として step5 を書く |
| 既存の Google アカウントで入りたい (Sign in with Google) | Google を IdP として、自分のアプリに step5 (RP 側) だけ書く |
| 社員の Microsoft 365 アカウントで入りたい | Microsoft Entra ID (旧 Azure AD) を IdP に、step5 (RP 側) を書く |
| 取引先と自社で SSO したい | SAML or OIDC で連携、自分のアプリは RP |

→ 共通して **「自分が書くのは step5 の RP 側」「IdP は他人 (or 専用ツール)」**
がセオリー。

## OAuth の 4 役

OAuth 2.0 を理解するには **誰が誰なのか** を最初に固定する必要がある。

| 役 | 英語 | 今回はだれが演じるか |
|---|---|---|
| **リソース所有者** | Resource Owner | ブラウザの前に座っている人 (alice / bob) |
| **クライアント** | Client (Relying Party) | 自分のアプリ。今回は `/oidc/start` `/oidc/callback` |
| **認可サーバ (IdP)** | Authorization Server | Google などに相当。今回は `/oauth/authorize` `/oauth/token` |
| **リソースサーバ (API)** | Resource Server | 既存の `/api/me` `/api/admin` |

普段これらは別ホストに分かれている。今回は 1 プロセスにまとめているので
**URL の前半 (`/oidc/...` vs `/oauth/...`) で役を見分ける** ようにする。

## Authorization Code Flow

```
[ブラウザ]          [クライアント (RP)]          [認可サーバ (IdP)]          [リソースサーバ]
   │
   │ GET /oidc/start
   ├──────────────►│
   │               │ state="xyz" を生成・保存
   │  302 →  /oauth/authorize?client_id=webapp&redirect_uri=...&state=xyz
   │◄──────────────┤
   │
   │ GET /oauth/authorize?...                                  ★ ここから IdP の世界
   ├──────────────────────────────────────►│
   │                                       │ セッション (step2 の sid) を確認
   │                                       │ 未ログインなら /login にリダイレクト
   │                                       │ ログイン済みなら code="abc" を生成・保存
   │  302 →  /oidc/callback?code=abc&state=xyz                ★ クライアントに戻る
   │◄──────────────────────────────────────┤
   │
   │ GET /oidc/callback?code=abc&state=xyz
   ├──────────────►│
   │               │ state を検証 (CSRF 対策)
   │               │
   │               │ POST /oauth/token (server-to-server, ブラウザを介さない)
   │               │   grant_type=authorization_code
   │               │   code=abc
   │               │   client_id=webapp
   │               │   client_secret=...
   │               │   redirect_uri=...
   │               ├──────────────────────►│
   │               │                       │ code を検証 (使用済み・期限切れ・不一致)
   │               │                       │ client_secret を検証
   │               │                       │ access_token + id_token を発行
   │               │◄──────────────────────┤  200 { access_token, id_token }
   │               │ id_token をデコード → "alice"
   │  200 HTML "logged in as alice via OIDC"
   │◄──────────────┤
   │
   │ (以後) GET /api/me  Authorization: Bearer <access_token>
   ├──────────────────────────────────────────────────────────────►│
   │                                                               │ JWT 検証
   │                                                               │ 200 "you are alice"
   │◄──────────────────────────────────────────────────────────────┤
```

### 各ステップで何を確認しているか

1. **`/oidc/start`**: クライアントが **state** を生成する。これが
   `/oidc/callback` まで往復してくるはずなので、戻ってきたときに比較する。
   別タブで仕込まれた CSRF を弾く仕組み (= `SameSite` Cookie だけでは
   足りない領域)。
2. **`/oauth/authorize`**: IdP は **ユーザ自身がログインしていること** を
   確認する (今回はセッション = `sid` Cookie で見る)。未ログインなら
   `/login` に飛ばし、戻ってきたら続きを実行する。
3. **`/oauth/token`**: code は **1 回限り** で **短命** (60 秒)。
   `client_secret` でクライアントの正体も確認する (なりすまし防止)。
4. **id_token**: 「**誰がログインしたか**」を表す JWT。クライアントは
   これをデコードしてユーザを特定する。
5. **access_token**: 「**この API を叩いてよい**」を表す JWT。
   そのまま `/api/me` などに `Bearer` で送れる。

## id_token と access_token の違い

| | id_token | access_token |
|---|---|---|
| 目的 | **誰がログインしたか** をクライアントに伝える | **API を叩く権限** |
| 受け取る人 | クライアント (RP) | リソースサーバ (API) |
| 中身の代表的なクレーム | `iss / sub / aud / iat / exp / email` | `sub / scope / role / exp` |
| 送る方法 | 受け取ったらすぐデコードしてセッション作成に使う | `Authorization: Bearer ...` |
| 出典 | OpenID Connect (OIDC) | OAuth 2.0 |

`access_token` だけでも認証 (= 誰か) はできるが、それは "OAuth で認証" という
歴史的な誤用パターン。OIDC は **「OAuth で認証もしたい」を正式仕様化** したもの
で、`id_token` がその答え。

## クライアント登録

OAuth では事前にクライアントを IdP に登録する (Google Console、Auth0 ダッシュボード、など)。
今回はコードに直書き:

```python
CLIENTS = {
    "webapp": {
        "secret": "webapp-secret",
        "redirect_uri": "http://127.0.0.1:8080/oidc/callback",
    },
}
```

`client_secret` はクライアント (= サーバサイドの RP) が **秘密に持つ** もの。
SPA / モバイルアプリでは秘密にできないので、その場合は PKCE で代用する。

## 実装手順

### 1. 保存領域

```python
CLIENTS = {"webapp": {"secret": "webapp-secret", "redirect_uri": "http://127.0.0.1:8080/oidc/callback"}}
AUTH_CODES: dict[str, dict] = {}   # code -> {sub, client_id, redirect_uri, exp}
OIDC_STATES: dict[str, bool] = {}  # state -> True (使い捨て)
```

### 2. discovery (`/.well-known/openid-configuration`)

OIDC では、クライアントが IdP の URL を **1 箇所からまとめて取れる** のが
規約。Auth0 などはこれを公開しているので、クライアントは URL を直書きせず
ここを読みに行く。

```python
def view_discovery(environ):
    base = f"http://{HOST}:{PORT}"  # 本来は HTTPS の発行者 URL
    body = json.dumps({
        "issuer": base,
        "authorization_endpoint": f"{base}/oauth/authorize",
        "token_endpoint": f"{base}/oauth/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["HS256"],
    }).encode()
    return "200 OK", [("Content-Type", "application/json")], body
```

### 3. `/oauth/authorize` (認可エンドポイント)

```python
def view_authorize(environ):
    q = parse_qs_simple(environ.get("QUERY_STRING", ""))
    client_id = q.get("client_id", "")
    redirect_uri = q.get("redirect_uri", "")
    state = q.get("state", "")
    client = CLIENTS.get(client_id)
    if client is None or client["redirect_uri"] != redirect_uri:
        return "400 Bad Request", PLAIN, b"invalid client_id or redirect_uri\n"

    user = get_logged_in_user(environ)
    if user is None:
        # 未ログインなら /login に誘導する (元 URL を next クエリで持ち回るのが普通)
        return "302 Found", [("Location", "/login")], b""

    code = secrets.token_urlsafe(24)
    AUTH_CODES[code] = {
        "sub": user,
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "exp": time.time() + 60,
    }
    location = f"{redirect_uri}?code={code}&state={state}"
    return "302 Found", [("Location", location)], b""
```

ポイント:

- **`client_id` と `redirect_uri` の組** を必ず検証する。これを抜くと
  攻撃者が任意のサイトに code を流せる
- code は **短命** (60 秒)、**1 回限り**
- 未ログインは `/login` に飛ばすだけ。本番ではログイン後に
  `/oauth/authorize` に戻す `next=` パラメータが必要

### 4. `/oauth/token` (トークンエンドポイント)

```python
def _exchange_code(code, client_id, client_secret, redirect_uri):
    """code 交換のロジックを関数に切り出す。view と内部呼び出しの両方で使う。"""
    record = AUTH_CODES.pop(code, None)  # ★ pop で 1 回限り
    if record is None:
        return None
    if time.time() > record["exp"]:
        return None
    if record["client_id"] != client_id or record["redirect_uri"] != redirect_uri:
        return None
    client = CLIENTS.get(client_id)
    if client is None or not hmac.compare_digest(client["secret"].encode(), client_secret.encode()):
        return None
    sub = record["sub"]
    now = int(time.time())
    base = f"http://{HOST}:{PORT}"  # 本来は HTTPS の issuer
    access_token = jwt_encode({
        "sub": sub, "role": ROLES.get(sub, "viewer"),
        "iat": now, "exp": now + JWT_TTL_SEC,
    })
    id_token = jwt_encode({
        "iss": base, "sub": sub, "aud": client_id,
        "iat": now, "exp": now + JWT_TTL_SEC,
        "email": f"{sub}@example.com",  # 学習用に固定で生やす
    })
    return {"access_token": access_token, "id_token": id_token,
            "token_type": "Bearer", "expires_in": JWT_TTL_SEC}

def view_oauth_token(environ):
    form = parse_qs_simple(read_body(environ).decode("iso-8859-1"))
    if form.get("grant_type") != "authorization_code":
        return "400 Bad Request", PLAIN, b"unsupported grant_type\n"
    result = _exchange_code(
        form.get("code", ""),
        form.get("client_id", ""),
        form.get("client_secret", ""),
        form.get("redirect_uri", ""),
    )
    if result is None:
        return "400 Bad Request", PLAIN, b"invalid grant\n"
    return "200 OK", [("Content-Type", "application/json")], json.dumps(result).encode() + b"\n"
```

### 5. RP 側: `/oidc/start` と `/oidc/callback`

```python
def view_oidc_start(environ):
    state = secrets.token_urlsafe(16)
    OIDC_STATES[state] = True
    params = (f"response_type=code&client_id=webapp&"
              f"redirect_uri=http%3A%2F%2F127.0.0.1%3A8080%2Foidc%2Fcallback&"
              f"scope=openid%20profile&state={state}")
    return "302 Found", [("Location", f"/oauth/authorize?{params}")], b""

def view_oidc_callback(environ):
    q = parse_qs_simple(environ.get("QUERY_STRING", ""))
    state = q.get("state", "")
    code = q.get("code", "")
    if not OIDC_STATES.pop(state, False):
        return "400 Bad Request", PLAIN, b"invalid state (possible CSRF)\n"

    # 本来は HTTP POST。今回は単一プロセスなので関数を直接呼ぶ。
    tokens = _exchange_code(
        code,
        client_id="webapp",
        client_secret="webapp-secret",
        redirect_uri="http://127.0.0.1:8080/oidc/callback",
    )
    if tokens is None:
        return "400 Bad Request", PLAIN, b"token exchange failed\n"

    id_payload = jwt_decode(tokens["id_token"])
    html = (
        b"<!doctype html><meta charset=utf-8><title>OIDC callback</title>"
        b"<h1>OIDC callback received</h1>"
        + f"<p>logged in as <b>{id_payload['sub']}</b> ({id_payload['email']})</p>".encode()
        + b"<h2>id_token payload</h2><pre>"
        + json.dumps(id_payload, indent=2).encode()
        + b"</pre><h2>access_token (raw)</h2><pre>"
        + tokens["access_token"].encode()
        + b"</pre>"
    )
    return "200 OK", HTML, html
```

### 6. ルート登録

```python
ROUTES = {
    ...
    ("GET",  "/.well-known/openid-configuration"): view_discovery,
    ("GET",  "/oauth/authorize"):                  view_authorize,
    ("POST", "/oauth/token"):                      view_oauth_token,
    ("GET",  "/oidc/start"):                       view_oidc_start,
    ("GET",  "/oidc/callback"):                    view_oidc_callback,
}
```

## 動作確認

### ブラウザ (フル体験)

1. `http://127.0.0.1:8080/login` を開いて `alice` / `wonderland` でログイン
2. `http://127.0.0.1:8080/oidc/start` を開く
3. (内部で) `/oauth/authorize` → `/oidc/callback` にリダイレクト
4. ページに **「logged in as alice (alice@example.com)」** + id_token / access_token が表示される

### curl (リダイレクトを手でたどる)

```bash
# 1) discovery
curl -s http://127.0.0.1:8080/.well-known/openid-configuration | python3 -m json.tool

# 2) ログインしてセッションを持つ
rm -f /tmp/c.txt
curl -s -c /tmp/c.txt -X POST -d 'user=alice&password=wonderland' http://127.0.0.1:8080/login

# 3) /oidc/start でリダイレクトされる先を確認
curl -s -i -b /tmp/c.txt http://127.0.0.1:8080/oidc/start | head -5

# 4) -L でリダイレクトを最後まで追う
curl -s -L -b /tmp/c.txt -c /tmp/c.txt http://127.0.0.1:8080/oidc/start | head -30
```

### state 検証を実機で見る

`/oidc/callback?code=...&state=DEADBEEF` のように **嘘の state** を直接叩くと
`400 invalid state (possible CSRF)` が返ることを確認できる。

## セキュリティ上の注意

| 落とし穴 | 対策 (今回入れたもの / 不足) |
|---|---|
| code の使い回し | `AUTH_CODES.pop()` で 1 回限り |
| code の長寿命化 | 60 秒の `exp` で短命 |
| redirect_uri 不一致 | 登録値と照合 |
| クライアント偽装 | `client_secret` を定数時間比較 |
| 認可リダイレクトの CSRF | `state` で検証 |
| (省略) PKCE | 今回は入れていない。SPA / モバイルでは **必須** |
| (省略) nonce | id_token のリプレイ対策。今回は省略 |
| ID プロバイダ確認 (`iss`/`aud`) | id_token に入れたが、検証は省略 (本来は必ず) |

## PKCE (Proof Key for Code Exchange) について

`client_secret` を秘密にできない (= SPA / モバイル) 場合に必須:

1. クライアントは `code_verifier` (ランダム文字列) を作る
2. その SHA256 を `code_challenge` として `/oauth/authorize` に送る
3. `/oauth/token` 呼び出し時に `code_verifier` を送る
4. IdP は `SHA256(code_verifier) == code_challenge` を確認する

→ 横取りした code は `code_verifier` を持っていないので使えない。
**OAuth 2.1 では全クライアントに PKCE 必須**。

## 製品はここをどうやっているか

| 仕事 | 自作 (今回) | 製品 |
|---|---|---|
| `/oauth/authorize` `/oauth/token` の実装 | 手書き | Auth0 / Cognito / Keycloak / Clerk |
| クライアント登録 | dict | 管理画面で登録 |
| ID プロバイダ間連携 (Google ログインなど) | しない | IdP が間に立つ (社外 SSO) |
| 鍵管理・ローテーション | しない | JWKS で公開鍵を回せる |
| MFA / リスクベース認証 | しない | IdP が提供 |
| 監査ログ | しない | IdP の標準機能 |

OAuth/OIDC 自体は **「コードを書くより設定するもの」** になっている。
今回のように自作するのは学習目的だけ。本番では **必ずライブラリ**
(`authlib`, `oauthlib`) **または IdP の SDK** を使う。

## auth step4 からの追加箇所

### `server.py`

**変更なし**。

### `app.py`

| 場所 | 追加・変更内容 |
|---|---|
| 定数 | `CLIENTS`、`AUTH_CODES`、`OIDC_STATES` を新設 |
| ヘルパー関数 | `_exchange_code()` (内部用、code 交換ロジック) を追加 |
| ビュー関数 | `view_discovery`、`view_authorize`、`view_oauth_token`、`view_oidc_start`、`view_oidc_callback` を追加 |
| `ROUTES` | 5 ルート追加: `/.well-known/openid-configuration`、`/oauth/authorize`、`/oauth/token`、`/oidc/start`、`/oidc/callback` |

差分を直接見たい場合:

```bash
diff snapshots/auth-step4/app.py snapshots/auth-step5/app.py
```

## 完了条件

- [ ] ブラウザで `/login` → `/oidc/start` を踏むと、`/oidc/callback` に
      `code` + `state` が付いて戻ってきて、id_token と access_token が表示される
- [ ] state を改ざんすると 400
- [ ] code を 2 回使うと 400 (1 回目で `pop` される)
- [ ] `client_secret` を間違えると 400
- [ ] `/oidc/callback` で受け取った access_token を `/api/me` に Bearer で送ると 200
- [ ] `snapshots/auth-step5/` にコードを凍結する
