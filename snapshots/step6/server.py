"""step6: server.py を WSGI ゲートウェイにする。

ここまで server.py は「parse → dispatch → handler → build_response」を
ぜんぶ自分でやっていた。step6 では、その内部処理（dispatch + handler）を
外の WSGI アプリ（app.py）に切り出す。

server.py に残るのは:
  - TCP socket の listen / accept / recv / send
  - 生のリクエストを WSGI の environ 辞書に変換
  - WSGI アプリを呼び、戻り値からレスポンスを組み立てて送信

WSGI アプリ (app.py) に出ていくのは:
  - ルーティング
  - ハンドラ本体（アプリのロジック）
  - ステータス・ヘッダ・ボディの生成

これで自分の server.py の上に、Flask のような WSGI アプリも乗せられる。
"""

import io
import socket
import sys

from app import app  # WSGI アプリは app.py から import

HOST = "127.0.0.1"
PORT = 8080
RECV_SIZE = 65536


def parse_request(raw: bytes) -> dict:
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")
    method, full_path, version = lines[0].split(" ", 2)
    headers: dict[str, str] = {}
    for line in lines[1:]:
        if not line:
            continue
        name, _, value = line.partition(":")
        headers[name.strip().lower()] = value.strip()
    return {
        "method": method,
        "full_path": full_path,
        "version": version,
        "headers": headers,
        "body": body,
    }


def build_environ(req: dict, client_addr) -> dict:
    """parsed request を WSGI environ 辞書に変換する（PEP 3333）。

    キーの並び:
      - REQUEST_METHOD / PATH_INFO / QUERY_STRING / SERVER_*
      - CONTENT_TYPE / CONTENT_LENGTH（リクエストにあった場合のみ）
      - HTTP_*（それ以外のリクエストヘッダ）
      - wsgi.*（WSGI 固有）
    """
    pure_path, _, query_string = req["full_path"].partition("?")
    headers = req["headers"]
    environ = {
        "REQUEST_METHOD": req["method"],
        "SCRIPT_NAME": "",
        "PATH_INFO": pure_path,
        "QUERY_STRING": query_string,
        "SERVER_NAME": HOST,
        "SERVER_PORT": str(PORT),
        "SERVER_PROTOCOL": req["version"],
        "REMOTE_ADDR": client_addr[0],
        "REMOTE_PORT": str(client_addr[1]),
        "wsgi.version": (1, 0),
        "wsgi.url_scheme": "http",
        "wsgi.input": io.BytesIO(req["body"]),
        "wsgi.errors": sys.stderr,
        "wsgi.multithread": False,
        "wsgi.multiprocess": False,
        "wsgi.run_once": False,
    }
    if "content-type" in headers:
        environ["CONTENT_TYPE"] = headers["content-type"]
    if "content-length" in headers:
        environ["CONTENT_LENGTH"] = headers["content-length"]
    for name, value in headers.items():
        if name in ("content-type", "content-length"):
            continue
        key = "HTTP_" + name.upper().replace("-", "_")
        environ[key] = value
    return environ


def call_app(app, environ) -> tuple[str, list, bytes]:
    """WSGI app を 1 リクエスト分呼んで (status, headers, body) を取り出す。"""
    captured: dict = {}

    def start_response(status, headers, exc_info=None):
        captured["status"] = status
        captured["headers"] = headers
        return lambda chunk: None  # WSGI の write callable は今回使わない

    body_iter = app(environ, start_response)
    try:
        body = b"".join(body_iter)
    finally:
        close = getattr(body_iter, "close", None)
        if close is not None:
            close()
    return captured["status"], captured["headers"], body


def build_response(status: str, headers: list, body: bytes) -> bytes:
    """WSGI 流の (status, headers, body) を HTTP/1.1 のバイト列にする。

    status は "200 OK" のような文字列、headers は [(name, value), ...]。
    """
    headers = list(headers)
    if not any(name.lower() == "content-length" for name, _ in headers):
        headers.append(("Content-Length", str(len(body))))
    if not any(name.lower() == "connection" for name, _ in headers):
        headers.append(("Connection", "close"))

    lines = [f"HTTP/1.1 {status}"]
    for name, value in headers:
        lines.append(f"{name}: {value}")
    head = "\r\n".join(lines) + "\r\n\r\n"
    return head.encode("iso-8859-1") + body


def serve_forever(app) -> None:
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
                environ = build_environ(req, addr)
                status, headers, body = call_app(app, environ)

                print(f"--- request from {addr[0]}:{addr[1]} ---")
                print(f"{environ['REQUEST_METHOD']} {req['full_path']} {environ['SERVER_PROTOCOL']}")
                print(f"→ WSGI app → {status}")
                print(f"--- request {len(raw)} bytes / response body {len(body)} bytes ---\n")

                conn.sendall(build_response(status, headers, body))


if __name__ == "__main__":
    try:
        serve_forever(app)
    except KeyboardInterrupt:
        print("\nbye")
