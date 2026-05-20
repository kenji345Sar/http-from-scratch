"""step1: 生 TCP で HTTP リクエストを受け取る。

HTTP のパース・ルーティング・レスポンス生成はまだ一切やらない。
受け取ったバイト列をそのまま表示し、固定のレスポンスだけ返す。
"""

import socket

HOST = "127.0.0.1"
PORT = 8080
RECV_SIZE = 4096

# 固定の HTTP レスポンス。中身を組み立てるのは step4 の仕事。
FIXED_RESPONSE = (
    b"HTTP/1.1 200 OK\r\n"
    b"Content-Type: text/plain; charset=utf-8\r\n"
    b"Content-Length: 29\r\n"
    b"Connection: close\r\n"
    b"\r\n"
    b"hello from http-from-scratch\n"
)


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
                print(f"--- request from {addr[0]}:{addr[1]} ---")
                print(raw.decode("utf-8", errors="replace"), end="")
                print(f"--- {len(raw)} bytes ---\n")
                conn.sendall(FIXED_RESPONSE)


if __name__ == "__main__":
    try:
        serve_forever()
    except KeyboardInterrupt:
        print("\nbye")
