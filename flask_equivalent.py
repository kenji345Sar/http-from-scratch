"""flask_equivalent.py: step1〜6 と同じ振る舞いを Flask で書いた版。

これと、自前の app.py + server.py を見比べると、Flask が import の裏で
何を内包しているかが分かる（詳しくは docs/flask-equivalent.md）。

セットアップ:
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python flask_equivalent.py

別ターミナルから:
    curl 'http://127.0.0.1:8080/'
    curl 'http://127.0.0.1:8080/hello?name=tsk'
    curl -i 'http://127.0.0.1:8080/html'
    curl -i 'http://127.0.0.1:8080/old'
    curl -X POST -d 'a=1&b=2' 'http://127.0.0.1:8080/submit'
    curl -i 'http://127.0.0.1:8080/static/hello.txt'

自前の server.py と同時には起動できない（同じ 8080 を使うため）。
どちらかを止めてから起動する。
"""

from flask import Flask, redirect, request

app = Flask(__name__, static_folder="static", static_url_path="/static")


@app.route("/")
def root():
    return "hello from Flask\n"


@app.route("/hello")
def hello():
    name = request.args.get("name", "stranger")
    return f"hi, {name}! (via Flask)\n"


@app.route("/html")
def html():
    return (
        "<h1>HTML response</h1>\n<p>Flask 経由でも HTML を返せる</p>\n",
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


@app.route("/old")
def old():
    return redirect("/hello")


@app.route("/submit", methods=["POST"])
def submit():
    return f"received form: {dict(request.form)}\n"


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080)
