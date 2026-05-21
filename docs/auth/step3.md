# auth step3: JWT 認証

## ゴール

step2 のセッション認証は **サーバ側に `SESSIONS` 表** を持っていた。
step3 では「**サーバが状態を持たない**」モデルに切り替え、
トークン自体に「誰か / いつまで有効か」を **HMAC 署名つき** で埋め込む。

追加するルート (API 風):

| メソッド | パス | 動き |
|---|---|---|
| POST | `/api/token` | user/password を受け取って **JWT を発行** |
| GET  | `/api/me`    | `Authorization: Bearer <JWT>` を検証して中身を返す |

step1 (Basic) / step2 (Session) のルートは **そのまま残す**。
3 種類の認証が同じアプリ内で並んで動く。

## セッションとの違い

| 観点 | セッション (step2) | JWT (step3) |
|---|---|---|
| サーバ側の状態 | あり (`SESSIONS` dict) | **なし** (鍵 `JWT_SECRET` だけ) |
| 検証コスト | dict ルックアップ | HMAC 計算 |
| 取り消し | 簡単 (dict から消す) | **難しい** (発行済みトークンは止められない) |
| スケール | セッションストアの共有が必要 | サーバを増やしても鍵を配るだけ |
| 主な用途 | 同一ドメインの Web アプリ | SPA / モバイル / マイクロサービス |

## JWT の構造

JWT は **3 つの部分を `.` でつないだ文字列**:

```
<header_b64url>.<payload_b64url>.<signature_b64url>
```

例:

```
eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhbGljZSIsImV4cCI6MTcwMDAwMzYwMH0.abc...
└──────────── header ────────────┘ └────────── payload ──────────┘ └ sig ┘
```

### header (どう署名したか)

```json
{"alg": "HS256", "typ": "JWT"}
```

### payload (誰か・いつまで有効か)

```json
{"sub": "alice", "iat": 1700000000, "exp": 1700003600}
```

代表的なクレーム:

| キー | 意味 |
|---|---|
| `sub` | 主体 (subject)。誰のトークンか |
| `iat` | 発行時刻 (issued at) |
| `exp` | 有効期限 (expiration)。これを過ぎたら無効 |
| `iss` | 発行者 (issuer)。Auth0 など |
| `aud` | 対象者 (audience)。どの API 向けか |

### signature (改ざん検知)

```
HMAC-SHA256(base64url(header) + "." + base64url(payload), JWT_SECRET)
```

→ `JWT_SECRET` を知っているサーバだけが、この署名を計算できる。
→ payload を 1 文字でも書き換えると、署名が一致しなくなる。

ポイント: **JWT は暗号化ではない**。base64url を戻せば中身は平文で読める。
だから **パスワードや個人情報を入れてはいけない**。隠したいなら HTTPS + 暗号化が別途必要。

## 実装手順

### 1. 鍵を置く

```python
JWT_SECRET = b"dev-secret-only-not-for-prod-CHANGE-ME"
JWT_ALG = "HS256"
JWT_TTL_SEC = 3600  # 1 時間
```

> **本番**: `os.environ["JWT_SECRET"]` で外から渡す。コードに書かない。
> 鍵が漏れたら **すべてのトークンを偽造できる**。

### 2. base64url ヘルパー

JWT は **base64url** (`+/` → `-_` / パディング `=` を取る) を使う。

```python
def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")

def _b64url_decode(data: bytes) -> bytes:
    pad = b"=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)
```

### 3. エンコード / デコード

```python
def jwt_encode(payload: dict) -> str:
    header = {"alg": JWT_ALG, "typ": "JWT"}
    header_b = _b64url(json.dumps(header, separators=(",", ":")).encode())
    payload_b = _b64url(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = header_b + b"." + payload_b
    sig = hmac.new(JWT_SECRET, signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + _b64url(sig)).decode("ascii")

def jwt_decode(token: str) -> dict | None:
    try:
        header_b, payload_b, sig_b = token.encode("ascii").split(b".")
    except ValueError:
        return None
    expected = hmac.new(JWT_SECRET, header_b + b"." + payload_b, hashlib.sha256).digest()
    given = _b64url_decode(sig_b)
    if not hmac.compare_digest(expected, given):  # 定数時間比較
        return None
    payload = json.loads(_b64url_decode(payload_b))
    if "exp" in payload and time.time() > payload["exp"]:
        return None
    return payload
```

ポイント:

- **`hmac.compare_digest`** で署名を比較 (タイミング攻撃対策)
- **`exp` チェックを必ず入れる** (期限切れトークンを通さない)
- 学習用にアルゴリズムを `HS256` 固定にしている。本番ライブラリは
  ヘッダの `alg` を検証して、想定外のアルゴリズムを拒否する必要がある (後述の "alg=none 攻撃")

### 4. トークン発行 (POST /api/token)

```python
def view_token(environ):
    form = parse_qs_simple(read_body(environ).decode("iso-8859-1"))
    user = form.get("user", "")
    password = form.get("password", "")
    record = USERS.get(user)
    if record is None or not verify_password(password, *record):
        return "401 Unauthorized", PLAIN, b"login failed\n"
    now = int(time.time())
    token = jwt_encode({"sub": user, "iat": now, "exp": now + JWT_TTL_SEC})
    body = json.dumps({
        "access_token": token,
        "token_type": "Bearer",
        "expires_in": JWT_TTL_SEC,
    }).encode() + b"\n"
    return "200 OK", [("Content-Type", "application/json")], body
```

OAuth 2.0 のトークンエンドポイントと同じ JSON フォーマットに合わせている。

### 5. 保護された API (GET /api/me)

```python
def view_api_me(environ):
    header = environ.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return "401 Unauthorized", PLAIN, b"missing bearer token\n"
    payload = jwt_decode(header[len("Bearer "):])
    if payload is None:
        return "401 Unauthorized", PLAIN, b"invalid or expired token\n"
    return "200 OK", PLAIN, f"you are {payload['sub']} (via JWT)\n".encode()
```

ポイント:

- セッションと違い、**サーバ側で何も引かない**。鍵さえあれば検証できる。
- Cookie ではなく `Authorization: Bearer ...` ヘッダで渡す (API 用)。

### 6. ルート登録

```python
ROUTES = {
    ...
    ("POST", "/api/token"): view_token,
    ("GET",  "/api/me"):    view_api_me,
}
```

## 動作確認

```bash
# 1) トークン発行
curl -s -X POST -d 'user=alice&password=wonderland' \
  http://127.0.0.1:8080/api/token

# {"access_token": "eyJhbGc...", "token_type": "Bearer", "expires_in": 3600}

# 2) トークンを変数に入れる
TOKEN=$(curl -s -X POST -d 'user=alice&password=wonderland' \
  http://127.0.0.1:8080/api/token | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

# 3) Bearer で /api/me を呼ぶ → 200
curl -i -H "Authorization: Bearer $TOKEN" http://127.0.0.1:8080/api/me

# 4) トークンなし → 401
curl -i http://127.0.0.1:8080/api/me

# 5) 改ざんトークン → 401 (末尾を 1 文字書き換える)
curl -i -H "Authorization: Bearer ${TOKEN}X" http://127.0.0.1:8080/api/me

# 6) 中身を見る (base64url を戻すだけで読める)
echo "$TOKEN" | cut -d. -f2 | python3 -c \
  'import sys,base64,json; s=sys.stdin.read().strip(); s+="="*(-len(s)%4); print(json.loads(base64.urlsafe_b64decode(s)))'
```

(6) で **payload が平文で読める** ことを目で見ておく。これが「JWT は暗号化ではない」の意味。

## セキュリティ上の注意

| 落とし穴 | 対策 |
|---|---|
| `alg=none` 攻撃 (署名なしを通してしまう) | 受信側で `alg` を許可リストで固定する。**ヘッダの値を信用しない** |
| 鍵の漏洩 | `JWT_SECRET` を env から渡す / KMS 経由 / 定期ローテーション |
| トークンの取り消しができない | TTL を短く (15 分など) + **refresh token** で再発行 |
| トークン盗難 | HTTPS 必須 / 保存先は Cookie (`HttpOnly`) または短命メモリ |
| 機密情報を payload に入れる | **入れない**。JWT は base64url で誰でも読める |
| key confusion (RS256 を HS256 として検証してしまう) | アルゴリズムを固定。汎用 verify を使わない |

## HS256 と RS256

| | HS256 (今回) | RS256 |
|---|---|---|
| 鍵 | 共有秘密 1 つ | 秘密鍵 (発行用) / 公開鍵 (検証用) |
| 適している場面 | 同一組織が発行も検証もする | **発行者と検証者が別** (Auth0 が発行、自分のアプリが検証) |
| 鍵配布 | 全サーバに同じ鍵 | 公開鍵だけ配ればよい |

OIDC / Auth0 / Cognito の access token は基本 **RS256**。
公開鍵は JWKS (`/.well-known/jwks.json`) から取れる。

## 製品はここをどうやっているか

| 仕事 | 自作 (今回) | 製品 |
|---|---|---|
| トークン発行 | `view_token` | Auth0 / Cognito / Keycloak / Clerk |
| トークン検証 | `jwt_decode` | `PyJWT`, `jose`, Flask の `flask-jwt-extended` |
| 鍵管理 | コード直書き (学習用) | KMS / Vault / env var |
| 公開鍵配布 | しない (HS256 なので) | JWKS エンドポイント (`/.well-known/jwks.json`) |
| 取り消し | 不可 | "revocation list" or 短命 access + refresh |

**「JWT を自作するな」** はよく言われる教訓。署名は `hmac` で書けるが、
`alg` 検証、`exp/nbf/iss/aud` のクレーム検証、key confusion 対策などを
正しく実装するのは難しい。本番では `PyJWT` などを使う。
今回は「ライブラリの中で何が起きているか」を見るための学習実装。

## auth step2 からの追加箇所

### `server.py`

**変更なし**。

### `app.py`

| 場所 | 追加・変更内容 |
|---|---|
| import | `import json`, `import time` を追加 |
| 定数 | `JWT_SECRET`, `JWT_ALG`, `JWT_TTL_SEC` を新設 |
| ヘルパー関数 | `_b64url()`, `_b64url_decode()`, `jwt_encode()`, `jwt_decode()` を追加 |
| ビュー関数 | `view_token` (POST /api/token), `view_api_me` (GET /api/me) を追加 |
| `ROUTES` | 2 ルート追加: `/api/token` (POST), `/api/me` (GET) |

step1 (Basic) / step2 (Session) のコードは **全部残っている**。

差分を直接見たい場合:

```bash
diff snapshots/auth-step2/app.py snapshots/auth-step3/app.py
```

## 完了条件

- [ ] `/api/token` で正しい認証情報を送ると JWT が返る
- [ ] その JWT を `Authorization: Bearer ...` で送ると `/api/me` が 200
- [ ] トークンを 1 文字改ざんすると 401
- [ ] 期限切れトークンは 401 (TTL を 5 秒に下げて確認するなど)
- [ ] step1 / step2 のルート (`/private`, `/login`, `/me`, `/logout`) は壊れていない
- [ ] `snapshots/auth-step3/` にコードを凍結する
