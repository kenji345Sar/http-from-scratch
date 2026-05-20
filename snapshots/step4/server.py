"""step4: ステータス + ヘッダ + ボディの形でレスポンスを組み立てる。

step3 では handler は「ボディ文字列」だけを返していた。レスポンス組み立ては
固定 (Content-Type 固定、ステータスは 200/404 のみ)。

step4 では handler が (status, headers, body) を返すように拡張し、
build_response 側も任意ステータス・任意ヘッダ・バイト列ボディを扱えるようにする。
"""

import socket

HOST = "127.0.0.1"
PORT = 8080
RECV_SIZE = 4096


# --- リクエストパース（step2 から） ---

def parse_request(raw: bytes) -> dict:
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")
    method, path, version = lines[0].split(" ", 2)
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return {
        "method": method,
        "path": path,
        "version": version,
        "headers": headers,
        "body": body,
    }


# --- レスポンスを作るためのヘルパー（handler が呼ぶ） ---

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
    return text("hi there!\n")


def handle_html_demo(req):
    return html("<h1>HTML response</h1>\n<p>step4 で Content-Type を切り替えられるようになった</p>\n")


def handle_submit(req):
    body_text = req["body"].decode("utf-8", errors="replace")
    return text(f"received: {body_text}\n")


def handle_old(req):
    return redirect("/hello")


def handle_not_found(req):
    return text(f"not found: {req['method']} {req['path']}\n", status=404)


ROUTES = {
    ("GET", "/"):         handle_root,
    ("GET", "/hello"):    handle_hello,
    ("GET", "/html"):     handle_html_demo,
    ("GET", "/old"):      handle_old,
    ("POST", "/submit"):  handle_submit,
}


# --- ルーティング ---

def dispatch(req) -> tuple[int, dict, bytes, str]:
    method = req["method"]
    path = req["path"].split("?", 1)[0]
    key = (method, path)
    if key in ROUTES:
        handler = ROUTES[key]
        status, headers, body = handler(req)
        return status, headers, body, handler.__name__
    status, headers, body = handle_not_found(req)
    return status, headers, body, handle_not_found.__name__


# --- レスポンス組み立て ---

REASON = {
    200: "OK",
    302: "Found",
    400: "Bad Request",
    404: "Not Found",
    500: "Internal Server Error",
}


def build_response(status: int, headers: dict, body: bytes) -> bytes:
    """status + headers + body の三つ組を HTTP/1.1 のバイト列に組み立てる。

    Content-Length は body の長さから自動算出して必ず付ける。
    Connection: close も既定で付ける（step3 までと同じ振る舞い）。
    """
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
                print(f"{req['method']} {req['path']} {req['version']}")
                pure_path = req["path"].split("?", 1)[0]
                tag = "matched" if status != 404 else "no route"
                ct = headers.get("Content-Type", "-")
                print(f"→ {tag}: ({req['method']!r}, {pure_path!r}) → {handler_name} → {status} {REASON[status]} ({ct})")
                print(f"--- request {len(raw)} bytes / response body {len(body)} bytes ---\n")

                conn.sendall(build_response(status, headers, body))


if __name__ == "__main__":
    try:
        serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
