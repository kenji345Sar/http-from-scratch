"""step3: パス + メソッドでハンドラを選ぶ（ルーティング）。

step2 まではどんなリクエストにも固定の 1 レスポンスを返していた。
ここから、リクエストの method と path を見て、呼ぶ関数を切り替える。

レスポンス組み立ては step4 で本格化する。step3 では動かすための最小限。
"""

import socket

HOST = "127.0.0.1"
PORT = 8080
RECV_SIZE = 4096


# --- リクエストパース（step2 から流用） ---

def parse_request(raw: bytes) -> dict:
    """HTTP リクエストのバイト列を method / path / version / headers / body に分解する。"""
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


# --- ハンドラ ---

def handle_root(req: dict) -> str:
    return "hello from http-from-scratch\n"


def handle_hello(req: dict) -> str:
    return "hi there!\n"


def handle_submit(req: dict) -> str:
    body_text = req["body"].decode("utf-8", errors="replace")
    return f"received: {body_text}\n"


def handle_not_found(req: dict) -> str:
    return f"not found: {req['method']} {req['path']}\n"


ROUTES = {
    ("GET", "/"): handle_root,
    ("GET", "/hello"): handle_hello,
    ("POST", "/submit"): handle_submit,
}


# --- ルーティング本体 ---

def dispatch(req: dict) -> tuple[int, str, str]:
    """method と path から呼ぶハンドラを決め、(status, body, handler_name) を返す。

    クエリ文字列（?以降）はルーティングに使わない。クエリの取り出しは step5。
    """
    method = req["method"]
    path = req["path"].split("?", 1)[0]
    key = (method, path)
    if key in ROUTES:
        handler = ROUTES[key]
        return 200, handler(req), handler.__name__
    return 404, handle_not_found(req), handle_not_found.__name__


# --- レスポンス組み立て（step3 の最小限版。step4 で拡張） ---

REASON = {200: "OK", 404: "Not Found"}


def build_response(status: int, body: str) -> bytes:
    body_bytes = body.encode("utf-8")
    head = (
        f"HTTP/1.1 {status} {REASON[status]}\r\n"
        f"Content-Type: text/plain; charset=utf-8\r\n"
        f"Content-Length: {len(body_bytes)}\r\n"
        f"Connection: close\r\n"
        f"\r\n"
    ).encode("utf-8")
    return head + body_bytes


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
                status, body, handler_name = dispatch(req)

                print(f"--- request from {addr[0]}:{addr[1]} ---")
                print(f"{req['method']} {req['path']} {req['version']}")
                pure_path = req["path"].split("?", 1)[0]
                tag = "matched" if status != 404 else "no route"
                print(f"→ {tag}: ({req['method']!r}, {pure_path!r}) → {handler_name} → {status} {REASON[status]}")
                print(f"--- request {len(raw)} bytes ---\n")

                conn.sendall(build_response(status, body))


if __name__ == "__main__":
    try:
        serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
