# auth step4: 認可 (RBAC)

## ゴール

ここまでの step1〜3 は **認証 (誰か？)** だけを扱ってきた。
step4 で初めて **認可 (何を許すか？)** を導入する。

- ユーザに **ロール** を持たせる (`alice = admin`, `bob = editor`)
- 「ログインは OK でも、ロール不足なら拒否」を実装する
- `401 Unauthorized` (誰だか分からない) と `403 Forbidden` (権限がない) を
  実機で打ち分ける

追加するルート:

| メソッド | パス | 認可ルール |
|---|---|---|
| GET | `/admin`     | セッション必須 + `role == "admin"` |
| GET | `/api/admin` | JWT 必須 + `role == "admin"` |

step1〜3 のルートはすべて残す。

## 401 と 403 の打ち分け

| 状況 | 何が分からないか | 返すべきステータス |
|---|---|---|
| Cookie / トークンが無い、壊れている | 「あなたは誰か」が分からない | **401 Unauthorized** |
| 認証は通っているが、ロールが足りない | 「誰か」は分かる。でも許可しない | **403 Forbidden** |

英語名が紛らわしいが、HTTP 規約では **401 = 認証不足** で固定。
「権限がない」は `403`。step1 でも触れたとおり。

## ロールの置き場所

`USERS` は **パスワードの責務**、`ROLES` は **認可の責務** で分ける。
1 つの dict に押し込むと、後で OIDC など外部認証に切り替えたときに
パスワード列だけ消すのが面倒になる。

```python
# ユーザ名 -> ロール
ROLES = {
    "alice": "admin",
    "bob":   "editor",
}
```

> **本番**: ユーザ ↔ ロール ↔ 権限 を DB のテーブルで持つ。
> 多くのアプリが `users` / `roles` / `user_roles` の 3 テーブル構成。

## セッションと JWT で「ロールの所在」が違う

これが step4 の見どころ。

| | セッション認証 | JWT 認証 |
|---|---|---|
| 認証時に何を保存 | サーバ側 `SESSIONS[sid] = user` | クライアントが持つ JWT |
| ロールはどこから引く | リクエストごとに **`ROLES` 表を引く** | **JWT の `role` クレーム** に埋め込まれている |
| ロールを変えると | **即座に反映** (次のリクエストから新ロール) | **次回トークン発行まで古いまま** |
| 例 | DB を `UPDATE users SET role='viewer'` → すぐ効く | 既発行のトークンは `exp` まで `role: admin` のまま |

→ JWT は「**発行時点のロールのスナップショット**」を持ち歩く。
これがメリット (DB ヒットなし) でありデメリット (取り消しにくい) でもある。

## 実装手順

### 1. ロール表を足す

```python
ROLES = {
    "alice": "admin",
    "bob":   "editor",
}
```

### 2. 共通ヘルパー: ロールチェックを 1 つの関数に

```python
def forbidden():
    return "403 Forbidden", PLAIN, b"forbidden: insufficient role\n"

def require_session_role(role: str, environ):
    """セッションでログインしている前提でロールを確認。
    エラー時は (status, headers, body)、OK なら None を返す。"""
    user = get_logged_in_user(environ)
    if user is None:
        return "401 Unauthorized", PLAIN, b"not logged in\n"
    if ROLES.get(user) != role:
        return forbidden()
    return None

def require_jwt_role(role: str, environ):
    """JWT を検証し、ロールを確認する。OK なら (payload,) を含む形で返してもよいが
    今回は単純に None / エラータプル に統一する。"""
    header = environ.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return "401 Unauthorized", PLAIN, b"missing bearer token\n"
    payload = jwt_decode(header[len("Bearer "):])
    if payload is None:
        return "401 Unauthorized", PLAIN, b"invalid or expired token\n"
    if payload.get("role") != role:
        return forbidden()
    return None
```

ポイント:

- **`401` を先に判定し、その後 `403` を判定する** (順序が逆だと「ログイン無しでも `403` を返す」変なサーバになる)
- セッション側は **毎回 `ROLES` を引く** → ロール変更が即反映
- JWT 側は **`payload['role']` を見る** → トークン発行時に固定される

### 3. JWT に role を埋め込む

`view_token` を改修し、発行時にロールも payload に入れる:

```python
def view_token(environ):
    ...
    token = jwt_encode({
        "sub": user,
        "role": ROLES.get(user, "viewer"),
        "iat": now,
        "exp": now + JWT_TTL_SEC,
    })
    ...
```

### 4. 保護ビューを足す

```python
def view_admin(environ):
    err = require_session_role("admin", environ)
    if err:
        return err
    user = get_logged_in_user(environ)
    return "200 OK", PLAIN, f"hi admin {user} (session)\n".encode("utf-8")

def view_api_admin(environ):
    err = require_jwt_role("admin", environ)
    if err:
        return err
    return "200 OK", PLAIN, b"admin api ok (jwt)\n"
```

### 5. ルート登録

```python
ROUTES = {
    ...
    ("GET", "/admin"):     view_admin,
    ("GET", "/api/admin"): view_api_admin,
}
```

## 動作確認

### セッション系 (`/admin`)

```bash
# 1) 未ログインで /admin → 401
curl -i http://127.0.0.1:8080/admin

# 2) bob (editor) でログインして /admin → 403
rm -f /tmp/c.txt
curl -s -c /tmp/c.txt -X POST -d 'user=bob&password=builder' http://127.0.0.1:8080/login >/dev/null
curl -i -b /tmp/c.txt http://127.0.0.1:8080/admin

# 3) alice (admin) でログインして /admin → 200
rm -f /tmp/c.txt
curl -s -c /tmp/c.txt -X POST -d 'user=alice&password=wonderland' http://127.0.0.1:8080/login >/dev/null
curl -i -b /tmp/c.txt http://127.0.0.1:8080/admin
```

### JWT 系 (`/api/admin`)

```bash
# 4) トークン無し → 401
curl -i http://127.0.0.1:8080/api/admin

# 5) bob (editor) のトークン → 403
BOB=$(curl -s -X POST -d 'user=bob&password=builder' http://127.0.0.1:8080/api/token \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -i -H "Authorization: Bearer $BOB" http://127.0.0.1:8080/api/admin

# 6) alice (admin) のトークン → 200
ALICE=$(curl -s -X POST -d 'user=alice&password=wonderland' http://127.0.0.1:8080/api/token \
  | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')
curl -i -H "Authorization: Bearer $ALICE" http://127.0.0.1:8080/api/admin

# 7) 改ざんトークン → 401 (認可より先に認証で落ちる)
curl -i -H "Authorization: Bearer ${ALICE}X" http://127.0.0.1:8080/api/admin
```

### JWT に role が埋まっていることを確認

```bash
echo "$ALICE" | cut -d. -f2 | python3 -c \
  'import sys,base64,json; s=sys.stdin.read().strip(); s+="="*(-len(s)%4); print(json.loads(base64.urlsafe_b64decode(s)))'
# → {'sub': 'alice', 'role': 'admin', 'iat': ..., 'exp': ...}
```

## RBAC を超えた認可モデル (概要だけ)

RBAC は「**ロール = 役職** で許可を決める」のが基本。一方:

| モデル | 例 | 使いどころ |
|---|---|---|
| **RBAC** | `role == "admin"` | 役職で権限が決まる業務アプリ |
| **ABAC** | `user.department == doc.department && action == "read"` | 属性が組み合わさるエンタープライズ |
| **ACL** | 「このファイルは user_42 / user_77 が読める」 | 文書共有 (Google Drive 的なもの) |
| **ReBAC** | 「user は document の owner だから書ける」 | グラフ的な権限 (Notion / GitHub) |

step4 では一番素朴な RBAC だけを扱う。ABAC 以上は OPA / Cedar / SpiceDB
などのポリシーエンジンに寄せるのが現代的。

## 製品はここをどうやっているか

| 仕事 | 自作 (今回) | 製品 |
|---|---|---|
| ロールの保存 | `ROLES` dict | DB の `users.role` / `user_roles` 表 |
| ロールチェック | `require_*_role()` 関数 | デコレータ (`@login_required(role='admin')`) / ミドルウェア |
| JWT に role を埋める | `payload["role"]` | Auth0/Cognito の "rules"/"custom claims" |
| 複雑な認可 | しない | OPA (Rego)、AWS Cedar、Casbin、SpiceDB |
| 監査ログ | しない | 認可結果を別途ログに残す（許可・拒否を全記録） |

## auth step3 からの追加箇所

### `server.py`

**変更なし**。

### `app.py`

| 場所 | 追加・変更内容 |
|---|---|
| 定数 | `ROLES = {"alice": "admin", "bob": "editor"}` を新設 |
| ヘルパー関数 | `forbidden()`、`require_session_role()`、`require_jwt_role()` を追加 |
| 既存変更 | `view_token` の JWT payload に `"role"` クレームを追加 |
| ビュー関数 | `view_admin` (GET /admin)、`view_api_admin` (GET /api/admin) を追加 |
| `ROUTES` | 2 ルート追加: `/admin` (GET)、`/api/admin` (GET) |

step1〜3 のルートはすべて残っている。

差分を直接見たい場合:

```bash
diff snapshots/auth-step3/app.py snapshots/auth-step4/app.py
```

## 完了条件

- [ ] `/admin` が「未ログイン → 401、editor → 403、admin → 200」を返す
- [ ] `/api/admin` が「トークン無し → 401、editor → 403、admin → 200、改ざん → 401」
- [ ] 既発行 JWT の payload を base64url で開くと `"role": "admin"` が見える
- [ ] step1〜3 のルートは壊れていない
- [ ] `snapshots/auth-step4/` にコードを凍結する
