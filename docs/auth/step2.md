# auth step2: セッション認証

## ゴール

step1 の Basic 認証は「**毎リクエストに ID/PW を載せる**」方式だった。
step2 では「**1 回ログインしたら、サーバ側のセッション表に記録して、
ブラウザは引換券 (sid) だけを Cookie で持ち回る**」方式に置き換える。

追加するルート:

| メソッド | パス | 動き |
|---|---|---|
| GET  | `/login`  | ログインフォーム (HTML) を返す |
| POST | `/login`  | フォームを受け取り、検証成功なら `Set-Cookie: sid=...` を返す |
| GET  | `/me`     | セッションを引いて「あなたは誰か」を返す。未ログインなら 401 |
| POST | `/logout` | サーバ側のセッションを破棄し、Cookie を消す |

step1 の `/private` (Basic) は **残したまま** にする。
両方の方式が並んで動くので、違いが見える。

## Basic 認証との違い

| 観点 | Basic (step1) | セッション (step2) |
|---|---|---|
| 認証情報をどこに持つ | 毎リクエストの `Authorization` ヘッダ | サーバ側のセッション表 |
| ブラウザが持つもの | (ブラウザがキャッシュした) ID/PW | `sid=...` という Cookie |
| ステートフルか | ステートレス | **ステートフル** (サーバが状態を持つ) |
| ログアウト | できない (ブラウザを閉じるしかない) | できる (セッションを消せばよい) |
| パスワードの露出回数 | 毎リクエスト | ログインの 1 回だけ |

## HTTP の仕様おさらい

### サーバ → クライアント: Set-Cookie

```
HTTP/1.1 200 OK
Set-Cookie: sid=abc123; Path=/; HttpOnly; SameSite=Lax
```

属性の意味:

| 属性 | 役割 |
|---|---|
| `Path=/` | この Cookie を送るパスの範囲 |
| `HttpOnly` | JS (`document.cookie`) から読めなくする → XSS で盗まれにくい |
| `SameSite=Lax` | 別ドメインからの POST に Cookie を載せない → CSRF 対策 |
| `Secure` | HTTPS の通信でしか送らせない (今回は http なので外す) |
| `Max-Age=...` | 有効期限 (秒)。省略するとブラウザを閉じるまで |

### クライアント → サーバ: Cookie

```
GET /me HTTP/1.1
Cookie: sid=abc123
```

ブラウザは `Set-Cookie` で受け取った値を覚えて、同じドメインのリクエストに
自動で載せる。これも **ブラウザの仕事** で、サーバ側 JS は要らない。

## 実装手順

### 1. セッションストアを置く

`app.py` にメモリ上の dict を置く。

```python
SESSIONS: dict[str, str] = {}  # sid → user
```

> **本来の置き場所**: Redis / DB / Memcached。
> Python プロセスを再起動するとログイン状態が全部消えるが、
> 今は「プロセスが生きている時間 = セッションの寿命」でよい。

### 2. パスワードをハッシュ化する (step1 の宿題)

step1 では `USERS = {"alice": "wonderland"}` と生パスワードを保存していた。
step2 では PBKDF2-HMAC-SHA256 (stdlib) でハッシュ化する。

```python
import hashlib, hmac, os, secrets

def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)
    return salt, digest

def verify_password(password: str, salt: bytes, digest: bytes) -> bool:
    _, calc = hash_password(password, salt)
    return hmac.compare_digest(calc, digest)  # 定数時間比較
```

ポイント:

- `os.urandom(16)` で **salt** をユーザごとに別にする → 同じパスワードでも別ハッシュになる
- `hmac.compare_digest` で **定数時間比較** → タイミング攻撃を防ぐ
- 本番では bcrypt / argon2 / scrypt が推奨。stdlib で学習する都合で PBKDF2 にする

USERS は `(salt, digest)` を持つ:

```python
USERS = {
    user: hash_password(pw) for user, pw in {
        "alice": "wonderland",
        "bob":   "builder",
    }.items()
}
```

### 3. Cookie をパースするヘルパー

WSGI では Cookie は `HTTP_COOKIE` に入る (例: `sid=abc; theme=dark`)。

```python
def parse_cookies(environ) -> dict[str, str]:
    raw = environ.get("HTTP_COOKIE", "")
    result: dict[str, str] = {}
    for pair in raw.split(";"):
        name, _, value = pair.strip().partition("=")
        if name:
            result[name] = value
    return result
```

### 4. ログインフォーム (GET /login)

```python
LOGIN_HTML = b"""<!doctype html>
<form method="post" action="/login">
  <label>user <input name="user"></label>
  <label>password <input name="password" type="password"></label>
  <button>login</button>
</form>
"""

def view_login_form(environ):
    return "200 OK", HTML, LOGIN_HTML
```

### 5. ログイン処理 (POST /login)

```python
def view_login(environ):
    form = parse_qs_simple(read_body(environ).decode("iso-8859-1"))
    user = form.get("user", "")
    password = form.get("password", "")
    record = USERS.get(user)
    if record is None or not verify_password(password, *record):
        return "401 Unauthorized", PLAIN, b"login failed\n"
    sid = secrets.token_urlsafe(32)
    SESSIONS[sid] = user
    cookie = f"sid={sid}; Path=/; HttpOnly; SameSite=Lax"
    return "200 OK", PLAIN + [("Set-Cookie", cookie)], f"ok, logged in as {user}\n".encode()
```

ポイント:

- `secrets.token_urlsafe(32)` で **暗号論的に安全な乱数** を sid にする
- `random.random()` は **絶対に使わない** (予測可能)
- 既存ユーザのログインで sid を作り直す → **セッション固定攻撃** 対策

### 6. 認証必須ビュー (GET /me)

```python
def get_logged_in_user(environ) -> str | None:
    sid = parse_cookies(environ).get("sid")
    if not sid:
        return None
    return SESSIONS.get(sid)

def view_me(environ):
    user = get_logged_in_user(environ)
    if user is None:
        return "401 Unauthorized", PLAIN, b"not logged in\n"
    return "200 OK", PLAIN, f"you are {user}\n".encode("utf-8")
```

### 7. ログアウト (POST /logout)

```python
def view_logout(environ):
    sid = parse_cookies(environ).get("sid")
    if sid:
        SESSIONS.pop(sid, None)
    expired = "sid=; Path=/; Max-Age=0"
    return "200 OK", PLAIN + [("Set-Cookie", expired)], b"logged out\n"
```

- サーバ側でも `SESSIONS` から消す (サーバ側の真実)
- クライアント側でも `Max-Age=0` で消す (ブラウザの表示)
- どちらか片方だけだと「片方は残ってる」状態になる

### 8. ルート登録

```python
ROUTES = {
    ...
    ("GET",  "/login"):  view_login_form,
    ("POST", "/login"):  view_login,
    ("GET",  "/me"):     view_me,
    ("POST", "/logout"): view_logout,
}
```

## 動作確認

### curl の場合

`-c cookies.txt` で受け取り、`-b cookies.txt` で送る。

```bash
# 1) 未ログインで /me → 401
curl -i http://127.0.0.1:8080/me

# 2) ログイン → Set-Cookie が返る
curl -i -c cookies.txt -X POST \
  -d 'user=alice&password=wonderland' \
  http://127.0.0.1:8080/login

# 3) Cookie 付きで /me → 200
curl -i -b cookies.txt http://127.0.0.1:8080/me

# 4) ログアウト
curl -i -b cookies.txt -c cookies.txt -X POST http://127.0.0.1:8080/logout

# 5) 再度 /me → 401
curl -i -b cookies.txt http://127.0.0.1:8080/me

# 6) 間違ったパスワード → 401
curl -i -X POST -d 'user=alice&password=wrong' http://127.0.0.1:8080/login
```

### ブラウザの場合

1. `http://127.0.0.1:8080/login` でフォームを開く
2. `alice` / `wonderland` で送信
3. `http://127.0.0.1:8080/me` で `you are alice` が表示される
4. DevTools → Application → Cookies で `sid` の値が確認できる

## セキュリティ上の注意 (一覧だけ。深追いは別 step)

| 攻撃 | 対策 (今回入れたもの) |
|---|---|
| パスワード漏洩 (DB 流出) | PBKDF2 でハッシュ化 + salt |
| タイミング攻撃 | `hmac.compare_digest` |
| セッション ID 予測 | `secrets.token_urlsafe` |
| セッション固定 | ログインのたびに新しい sid |
| XSS で Cookie 盗難 | `HttpOnly` |
| CSRF (別ドメインからの POST) | `SameSite=Lax` (完全ではない。本来は CSRF トークンも併用) |
| 中間者攻撃 | `Secure` 属性 + HTTPS (今回は localhost なので省略) |

## 製品はここをどうやっているか

| 仕事 | 自作 (今回) | 製品・フレームワーク |
|---|---|---|
| セッション ID 発行 | `secrets.token_urlsafe` | フレームワークが自動 |
| セッションストア | プロセス内の dict | Redis / Memcached / DB / 署名付き Cookie |
| Cookie 属性 | 自分で組み立て | `flask.session` などが自動 |
| パスワードハッシュ | PBKDF2 (stdlib) | bcrypt / argon2 (`passlib`, `django.contrib.auth`) |
| CSRF | 入れていない | `flask-wtf`, Rails の `protect_from_forgery` |
| IdP に委ねる | しない | Auth0, Cognito, Clerk が肩代わり |

セッション認証はフレームワークが一番手厚く面倒を見る領域。
「自分で書くと地味に面倒くさい」ことが体感できれば step2 のねらいは達成。

## auth step1 からの追加箇所

step1 (Basic 認証) と比べて、auth step2 で **追加・変更した箇所だけ** を抜き出すと:

### `server.py`

**変更なし**。

### `app.py`

| 場所 | 追加・変更内容 |
|---|---|
| import | `hashlib`, `hmac`, `os`, `secrets` を追加 |
| 定数 | `USERS` を **平文 dict → `{user: (salt, digest)}`** に変更<br>`SESSIONS: dict[str, str] = {}` を新設 (sid → user) |
| ヘルパー関数 | `hash_password()`、`verify_password()`、`parse_cookies()`、`get_logged_in_user()` を追加 |
| ビュー関数 | `view_login_form` (GET /login)、`view_login` (POST /login)、`view_me` (GET /me)、`view_logout` (POST /logout) を追加 |
| 既存変更 | `view_private` (Basic) を、`USERS` のハッシュ化に追随して `verify_password` を呼ぶ形に更新 |
| `ROUTES` | 4 ルート追加: `/login` (GET/POST)、`/me` (GET)、`/logout` (POST) |
| HTML | `LOGIN_HTML` (ログインフォームのバイト列) を新設 |

step1 のコード (`parse_basic_auth`、`unauthorized`、`view_private` の骨格) は残っている。
**Basic 認証とセッション認証が同じアプリの中で並んで動く** 状態。

差分を直接見たい場合:

```bash
diff snapshots/auth-step1/app.py snapshots/auth-step2/app.py
```

## 完了条件

- [ ] 上の curl シナリオが 1〜6 まで期待どおりに動く
- [ ] ブラウザでログイン → `/me` → ログアウトが動く
- [ ] `snapshots/auth-step2/` にコードを凍結する
- [ ] step1 の `/private` (Basic) は壊れていない
