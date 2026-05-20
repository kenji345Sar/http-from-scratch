"""step2: 受け取った HTTP リクエストをパースする。

step1 までは「届いたバイト列を表示する」だけだった。
ここから、リクエスト行・ヘッダ・ボディに分解して、辞書として扱う。

ルーティングやレスポンス組み立てはまだやらない（step3 / step4）。
"""

import socket

HOST = "127.0.0.1"
PORT = 8080
RECV_SIZE = 4096

FIXED_RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"Content-Length: 29\r\n"
    b"Connection: close\r\n"
    b"\r\n"
    b"hello from http-from-scratch\n"
)


def parse_request(raw: bytes) -> dict:
    """HTTP リクエストのバイト列を method / path / version / headers / body に分解する。

    フォーマット:
        リクエスト行\r\n
        ヘッダ名: 値\r\n
        ...
        \r\n            ← 空行（ヘッダの終わり）
        ボディ
    """
    head, _, body = raw.partition(b"\r\n\r\n")
    lines = head.decode("iso-8859-1").split("\r\n")

    # 1 行目: リクエスト行 ("GET /hello?name=tsk HTTP/1.1")
    method, path, version = lines[0].split(" ", 2)

    # 2 行目以降: ヘッダ ("Host: 127.0.0.1:8080" など)
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
                print(f"--- request from {addr[0]}:{addr[1]} ---")
                print(f"method:  {req['method']}")
                print(f"path:    {req['path']}")
                print(f"version: {req['version']}")
                print("headers:")
                for k, v in req["headers"].items():
                    print(f"  {k}: {v}")
                body_text = req["body"].decode("utf-8", errors="replace")
                print(f"body:    {body_text!r}" if body_text else "body:    (empty)")
                print(f"--- {len(raw)} bytes ---\n")
                conn.sendall(FIXED_RESPONSE)


if __name__ == "__main__":
    try:
        serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
