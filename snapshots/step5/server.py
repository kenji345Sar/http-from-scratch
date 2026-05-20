"""step5: クエリ・フォームの取り出しと、静的ファイル配信。

step4 までは「method と path だけでハンドラを呼ぶ」サーバだった。
step5 では、URL のクエリ文字列・POST のフォームデータを辞書化し、
さらに /static/* で実ファイルを返せるようにする。

URL デコード (a%20b → "a b") と MIME 推定 (.css → text/css) は、
標準ライブラリの urllib.parse / mimetypes に任せる。
"""

import mimetypes
import socket
from pathlib import Path
from urllib.parse import unquote_plus

HOST = "127.0.0.1"
PORT = 8080
RECV_SIZE = 4096
STATIC_DIR = (Path(__file__).parent / "static").resolve()


# --- パース ---

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


def parse_request(raw: bytes) -> dict:
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")
    method, full_path, version = lines[0].split(" ", 2)

    # path とクエリを分離
    pure_path, _, query_string = full_path.partition("?")

    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()

    # application/x-www-form-urlencoded のときだけ body を form として辞書化
    form: dict[str, str] = {}
    if headers.get("content-type", "").startswith("application/x-www-form-urlencoded"):
        form = parse_qs_simple(body.decode("iso-8859-1"))

    return {
        "method": method,
        "path": pure_path,                   # クエリを含まない
        "raw_path": full_path,               # クエリを含む（ログ用）
        "version": version,
        "headers": headers,
        "body": body,
        "query": parse_qs_simple(query_string),
        "form": form,
    }


# --- レスポンスヘルパー ---

def text(body: str, status: int = 200) -> tuple[int, dict, bytes]:
    return status, {"Content-Type": "text/plain; charset=utf-8"}, body.encode("utf-8")


def html(body: str, status: int = 200) -> tuple[int, dict, bytes]:
    return status, {"Content-Type": "text/html; charset=utf-8"}, body.encode("utf-8")


def redirect(location: str, status: int = 302) -> tuple[int, dict, bytes]:
    return status, {"Location": location}, b""


# --- ハンドラ ---

def handle_root(req):
    return text("hello from http-from-scratch\n")


def handle_hello(req):
    name = req["query"].get("name", "stranger")
    return text(f"hi, {name}!\n")


def handle_html_demo(req):
    return html("<h1>HTML response</h1>\n<p>step4 で Content-Type を切り替えられるようになった</p>\n")


def handle_submit(req):
    return text(f"received form: {req['form']}\n")


def handle_old(req):
    return redirect("/hello")


def handle_not_found(req):
    return text(f"not found: {req['method']} {req['raw_path']}\n", status=404)


def handle_static(req):
    """`/static/foo.css` のような GET を、static/ ディレクトリの実ファイルで返す。"""
    rel = req["path"][len("/static/"):]
    if not rel:
        return text("forbidden\n", status=403)

    target = (STATIC_DIR / rel).resolve()
    # ../ で静的ディレクトリの外を読まれないようガード
    try:
        target.relative_to(STATIC_DIR)
    except ValueError:
        return text("forbidden\n", status=403)

    if not target.is_file():
        return text(f"not found: {req['path']}\n", status=404)

    content_type, _ = mimetypes.guess_type(target.name)
    if not content_type:
        content_type = "application/octet-stream"

    return 200, {"Content-Type": content_type}, target.read_bytes()


ROUTES = {
    ("GET", "/"):        handle_root,
    ("GET", "/hello"):   handle_hello,
    ("GET", "/html"):    handle_html_demo,
    ("GET", "/old"):     handle_old,
    ("POST", "/submit"): handle_submit,
}


# --- ルーティング ---

def dispatch(req) -> tuple[int, dict, bytes, str]:
    key = (req["method"], req["path"])
    if key in ROUTES:
        handler = ROUTES[key]
        status, headers, body = handler(req)
        return status, headers, body, handler.__name__
    # 静的ファイル: 完全一致しなかった GET /static/* はここで拾う
    if req["method"] == "GET" and req["path"].startswith("/static/"):
        status, headers, body = handle_static(req)
        return status, headers, body, handle_static.__name__
    status, headers, body = handle_not_found(req)
    return status, headers, body, handle_not_found.__name__


# --- レスポンス組み立て ---

REASON = {
    200: "OK",
    302: "Found",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    500: "Internal Server Error",
}


def build_response(status: int, headers: dict, body: bytes) -> bytes:
    headers = dict(headers)
    headers.setdefault("Content-Length", str(len(body)))
    headers.setdefault("Connection", "close")

    lines = [f"HTTP/1.1 {status} {REASON[status]}"]
    for name, value in headers.items():
        lines.append(f"{name}: {value}")
    head = "\r\n".join(lines) + "\r\n\r\n"
    return head.encode("iso-8859-1") + body


def serve_forever() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(5)
        print(f"listening on http://{HOST}:{PORT}")

        while True:
            conn, addr = server.accept()
            with conn:
                raw = conn.recv(RECV_SIZE)
                if not raw:
                    continue
                req = parse_request(raw)
                status, headers, body, handler_name = dispatch(req)

                print(f"--- request from {addr[0]}:{addr[1]} ---")
                print(f"{req['method']} {req['raw_path']} {req['version']}")
                if req["query"]:
                    print(f"query: {req['query']}")
                if req["form"]:
                    print(f"form:  {req['form']}")
                ct = headers.get("Content-Type", "-")
                print(f"→ {handler_name} → {status} {REASON[status]} ({ct})")
                print(f"--- request {len(raw)} bytes / response body {len(body)} bytes ---\n")

                conn.sendall(build_response(status, headers, body))


if __name__ == "__main__":
    try:
        serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
