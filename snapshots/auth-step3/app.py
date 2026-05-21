"""step6 の WSGI アプリ。

step5 までの dispatch + ハンドラ + レスポンスヘルパーを、
WSGI 仕様（PEP 3333）にあわせて 1 つの callable にまとめた。

WSGI の規約:
  - 関数のシグネチャは `app(environ, start_response)`
  - environ は CGI 互換の辞書（REQUEST_METHOD / PATH_INFO / QUERY_STRING など）
  - start_response(status, headers) でステータス（"200 OK"）と
    ヘッダ（[(name, value), ...]）を返す
  - 関数の戻り値は「バイト列のイテラブル」（`[body]` でよい）

server.py（WSGI ゲートウェイ）はこの規約だけ知っていればよい。
ここを満たすかぎり、Flask など他の WSGI フレームワークも同じ server.py で動く。
"""

import base64
import hashlib
import hmac
import json
import mimetypes
import os
import secrets
import time
from pathlib import Path
from urllib.parse import unquote_plus

STATIC_DIR = (Path(__file__).parent / "static").resolve()

PLAIN = [("Content-Type", "text/plain; charset=utf-8")]
HTML = [("Content-Type", "text/html; charset=utf-8")]

UNAUTHORIZED_HEADERS = PLAIN + [
    ("WWW-Authenticate", 'Basic realm="http-from-scratch"'),
]


# --- auth step2: パスワードハッシュ + セッションストア ---

def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    """PBKDF2-HMAC-SHA256 で (salt, digest) を返す。学習用の単純実装。"""
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200_000)
    return salt, digest


def verify_password(password: str, salt: bytes, digest: bytes) -> bool:
    """定数時間比較でパスワードを検証する（タイミング攻撃対策）。"""
    _, calc = hash_password(password, salt)
    return hmac.compare_digest(calc, digest)


# 学習用の仮ユーザー DB。プロセス起動時にハッシュ化する。
USERS: dict[str, tuple[bytes, bytes]] = {
    user: hash_password(pw) for user, pw in {
        "alice": "wonderland",
        "bob":   "builder",
    }.items()
}

# sid -> user。実運用なら Redis / DB。再起動で全消える前提。
SESSIONS: dict[str, str] = {}


# --- auth step3: JWT 用の鍵とヘルパー ---

JWT_SECRET = b"dev-secret-only-not-for-prod-CHANGE-ME"  # 学習用。本番は env から渡す
JWT_ALG = "HS256"
JWT_TTL_SEC = 3600


def _b64url(data: bytes) -> bytes:
    return base64.urlsafe_b64encode(data).rstrip(b"=")


def _b64url_decode(data: bytes) -> bytes:
    pad = b"=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + pad)


def jwt_encode(payload: dict) -> str:
    """HS256 で payload を署名し、`header.payload.sig` 形式の文字列を返す。"""
    header = {"alg": JWT_ALG, "typ": "JWT"}
    header_b = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b = _b64url(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = header_b + b"." + payload_b
    sig = hmac.new(JWT_SECRET, signing_input, hashlib.sha256).digest()
    return (signing_input + b"." + _b64url(sig)).decode("ascii")


def jwt_decode(token: str) -> dict | None:
    """署名と `exp` を検証し、payload を返す。失敗時は None。"""
    try:
        header_b, payload_b, sig_b = token.encode("ascii").split(b".")
    except ValueError:
        return None
    expected = hmac.new(JWT_SECRET, header_b + b"." + payload_b, hashlib.sha256).digest()
    try:
        given = _b64url_decode(sig_b)
    except (ValueError, base64.binascii.Error):
        return None
    if not hmac.compare_digest(expected, given):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b))
    except (ValueError, json.JSONDecodeError):
        return None
    if "exp" in payload and time.time() > payload["exp"]:
        return None
    return payload


def parse_basic_auth(environ) -> tuple[str, str] | None:
    """Authorization: Basic ... を (user, password) に分解する。失敗時は None。"""
    header = environ.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(header[len("Basic "):]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    user, sep, password = decoded.partition(":")
    if not sep:
        return None
    return user, password


def parse_cookies(environ) -> dict[str, str]:
    """`HTTP_COOKIE: sid=abc; theme=dark` → {"sid": "abc", "theme": "dark"}"""
    raw = environ.get("HTTP_COOKIE", "")
    result: dict[str, str] = {}
    for pair in raw.split(";"):
        name, _, value = pair.strip().partition("=")
        if name:
            result[name] = value
    return result


def get_logged_in_user(environ) -> str | None:
    sid = parse_cookies(environ).get("sid")
    if not sid:
        return None
    return SESSIONS.get(sid)


def unauthorized():
    return "401 Unauthorized", UNAUTHORIZED_HEADERS, b"unauthorized\n"


def parse_qs_simple(query: str) -> dict[str, str]:
    """`a=1&b=2&c=hello%20world` → `{"a": "1", "b": "2", "c": "hello world"}`"""
    result: dict[str, str] = {}
    if not query:
        return result
    for pair in query.split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        result[unquote_plus(key)] = unquote_plus(value)
    return result


def read_body(environ) -> bytes:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    if length <= 0:
        return b""
    return environ["wsgi.input"].read(length)


# --- view 関数（環境を渡すと (status, headers, body) を返す） ---

def view_root(environ):
    return "200 OK", PLAIN, b"hello from WSGI app\n"


def view_hello(environ):
    name = parse_qs_simple(environ.get("QUERY_STRING", "")).get("name", "stranger")
    return "200 OK", PLAIN, f"hi, {name}! (via WSGI)\n".encode("utf-8")


def view_html(environ):
    body = "<h1>HTML response</h1>\n<p>step6 (WSGI) でも HTML を返せる</p>\n".encode("utf-8")
    return "200 OK", HTML, body


def view_old(environ):
    return "302 Found", [("Location", "/hello")], b""


def view_submit(environ):
    form = parse_qs_simple(read_body(environ).decode("iso-8859-1"))
    return "200 OK", PLAIN, f"received form: {form}\n".encode("utf-8")


def view_static(environ):
    path = environ["PATH_INFO"]
    rel = path[len("/static/"):]
    if not rel:
        return "403 Forbidden", PLAIN, b"forbidden\n"
    target = (STATIC_DIR / rel).resolve()
    try:
        target.relative_to(STATIC_DIR)
    except ValueError:
        return "403 Forbidden", PLAIN, b"forbidden\n"
    if not target.is_file():
        return "404 Not Found", PLAIN, f"not found: {path}\n".encode("utf-8")
    ct, _ = mimetypes.guess_type(target.name)
    return "200 OK", [("Content-Type", ct or "application/octet-stream")], target.read_bytes()


def view_private(environ):
    """auth step1: Basic 認証を要求する保護されたページ。"""
    creds = parse_basic_auth(environ)
    if creds is None:
        return unauthorized()
    user, password = creds
    record = USERS.get(user)
    if record is None or not verify_password(password, *record):
        return unauthorized()
    return "200 OK", PLAIN, f"hi, {user}! (you are authenticated)\n".encode("utf-8")


# --- auth step2: セッション認証のビュー ---

LOGIN_HTML = b"""<!doctype html>
<meta charset="utf-8">
<title>login</title>
<form method="post" action="/login">
  <p><label>user <input name="user"></label></p>
  <p><label>password <input name="password" type="password"></label></p>
  <p><button>login</button></p>
</form>
"""


def view_login_form(environ):
    return "200 OK", HTML, LOGIN_HTML


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
    headers = PLAIN + [("Set-Cookie", cookie)]
    return "200 OK", headers, f"ok, logged in as {user}\n".encode("utf-8")


def view_me(environ):
    user = get_logged_in_user(environ)
    if user is None:
        return "401 Unauthorized", PLAIN, b"not logged in\n"
    return "200 OK", PLAIN, f"you are {user}\n".encode("utf-8")


def view_logout(environ):
    sid = parse_cookies(environ).get("sid")
    if sid:
        SESSIONS.pop(sid, None)
    expired = "sid=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0"
    return "200 OK", PLAIN + [("Set-Cookie", expired)], b"logged out\n"


# --- auth step3: JWT のビュー ---

def view_token(environ):
    """POST /api/token: 認証情報を JWT に交換する。"""
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
    }).encode("utf-8") + b"\n"
    return "200 OK", [("Content-Type", "application/json")], body


def view_api_me(environ):
    """GET /api/me: Authorization: Bearer <jwt> を検証する。"""
    header = environ.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Bearer "):
        return "401 Unauthorized", PLAIN, b"missing bearer token\n"
    payload = jwt_decode(header[len("Bearer "):])
    if payload is None:
        return "401 Unauthorized", PLAIN, b"invalid or expired token\n"
    return "200 OK", PLAIN, f"you are {payload['sub']} (via JWT)\n".encode("utf-8")


def view_not_found(environ):
    msg = f"not found: {environ['REQUEST_METHOD']} {environ['PATH_INFO']}\n"
    return "404 Not Found", PLAIN, msg.encode("utf-8")


ROUTES = {
    ("GET",  "/"):           view_root,
    ("GET",  "/hello"):      view_hello,
    ("GET",  "/html"):       view_html,
    ("GET",  "/old"):        view_old,
    ("GET",  "/private"):    view_private,
    ("POST", "/submit"):     view_submit,
    ("GET",  "/login"):      view_login_form,
    ("POST", "/login"):      view_login,
    ("GET",  "/me"):         view_me,
    ("POST", "/logout"):     view_logout,
    ("POST", "/api/token"):  view_token,
    ("GET",  "/api/me"):     view_api_me,
}


def app(environ, start_response):
    """WSGI エントリーポイント。

    server.py から `app(environ, start_response)` の形で呼ばれる。
    """
    method = environ["REQUEST_METHOD"]
    path = environ["PATH_INFO"]

    if (method, path) in ROUTES:
        view = ROUTES[(method, path)]
    elif method == "GET" and path.startswith("/static/"):
        view = view_static
    else:
        view = view_not_found

    status, headers, body = view(environ)
    start_response(status, headers)
    return [body]
