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
import mimetypes
from pathlib import Path
from urllib.parse import unquote_plus

STATIC_DIR = (Path(__file__).parent / "static").resolve()

PLAIN = [("Content-Type", "text/plain; charset=utf-8")]
HTML = [("Content-Type", "text/html; charset=utf-8")]

# auth step1: 学習用の仮ユーザー DB（実運用ではコードに書かない）
USERS = {
    "alice": "wonderland",
    "bob":   "builder",
}

UNAUTHORIZED_HEADERS = PLAIN + [
    ("WWW-Authenticate", 'Basic realm="http-from-scratch"'),
]


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
    if USERS.get(user) != password:
        return unauthorized()
    return "200 OK", PLAIN, f"hi, {user}! (you are authenticated)\n".encode("utf-8")


def view_not_found(environ):
    msg = f"not found: {environ['REQUEST_METHOD']} {environ['PATH_INFO']}\n"
    return "404 Not Found", PLAIN, msg.encode("utf-8")


ROUTES = {
    ("GET", "/"):        view_root,
    ("GET", "/hello"):   view_hello,
    ("GET", "/html"):    view_html,
    ("GET", "/old"):     view_old,
    ("GET", "/private"): view_private,
    ("POST", "/submit"): view_submit,
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
