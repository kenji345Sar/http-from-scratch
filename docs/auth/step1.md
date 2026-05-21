# auth step1: Basic 認証

## ゴール

`/private` というパスを 1 つ追加し、**Authorization ヘッダで認証された
ユーザだけが見られる** ようにする。

- 認証なし → `401 Unauthorized` + `WWW-Authenticate: Basic realm="..."`
- 認証あり (正しい) → `200 OK` + 「hi, &lt;user&gt;」
- 認証あり (間違い) → `401 Unauthorized`

`server.py` (= WSGI ゲートウェイ) には手を入れない。
**認証は WSGI アプリ側 (`app.py`) の仕事** という分離を維持する。

## HTTP の仕様おさらい

Basic 認証は HTTP の標準 (RFC 7617)。

### クライアント → サーバ

```
GET /private HTTP/1.1
Authorization: Basic <base64(user:pass)>
```

`user:pass` を base64 した文字列を `Basic` の後ろに付けるだけ。
**base64 は暗号ではない**。盗聴されたら一発で復元できるので、本物の運用では
HTTPS が必須。

### サーバ → クライアント (未認証)

```
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="http-from-scratch"
```

`WWW-Authenticate` を返すと、ブラウザはダイアログを出して
ユーザ名・パスワードを聞き、次のリクエストに `Authorization` を載せて再送する。
これは **ブラウザの仕事** であり、サーバ側 JS は要らない。

## 実装手順

### 1. ユーザー DB を仮置きする

`app.py` の先頭付近に、ハードコードのユーザー表を置く。

```python
# 学習用の仮 DB。実運用では絶対にコードに書かない。
USERS = {
    "alice": "wonderland",
    "bob":   "builder",
}
```

> **本来の置き場所**: DB / LDAP / IdP のいずれか。今回はそこを省いて
> 「認証ロジックだけ」を見るために dict で代用する。後続 step で
> セッション → JWT → OIDC と進むにつれて、ここを差し替えていく。

### 2. Authorization ヘッダを読むヘルパーを書く

```python
import base64

def parse_basic_auth(environ) -> tuple[str, str] | None:
    header = environ.get("HTTP_AUTHORIZATION", "")
    if not header.startswith("Basic "):
        return None
    try:
        decoded = base64.b64decode(header[len("Basic "):]).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    user, _, password = decoded.partition(":")
    return user, password
```

ポイント:

- WSGI では HTTP ヘッダは `HTTP_<NAME 大文字>` で `environ` に入る。
  `Authorization` → `HTTP_AUTHORIZATION`。
- `Basic ` の後ろの文字列を base64 デコードすると `user:pass` の形になる。
- パースに失敗したら `None` を返し、呼び出し側で `401` を返す。

### 3. 認可レス (401) を組み立てるヘルパー

```python
UNAUTHORIZED_HEADERS = PLAIN + [
    ("WWW-Authenticate", 'Basic realm="http-from-scratch"'),
]

def unauthorized():
    return "401 Unauthorized", UNAUTHORIZED_HEADERS, b"unauthorized\n"
```

`WWW-Authenticate` を返すのが Basic 認証の肝。これがないと
ブラウザはダイアログを出さない。

### 4. `/private` ビューを足す

```python
def view_private(environ):
    creds = parse_basic_auth(environ)
    if creds is None:
        return unauthorized()
    user, password = creds
    if USERS.get(user) != password:
        return unauthorized()
    return "200 OK", PLAIN, f"hi, {user}! (you are authenticated)\n".encode("utf-8")
```

ROUTES に登録:

```python
ROUTES = {
    ...
    ("GET", "/private"): view_private,
}
```

### 5. 動作確認

```bash
python3 server.py
```

別ターミナルから:

```bash
# 1) 認証なし → 401
curl -i http://127.0.0.1:8080/private

# 2) 正しい認証 → 200
curl -i -u alice:wonderland http://127.0.0.1:8080/private

# 3) 間違った認証 → 401
curl -i -u alice:wrong http://127.0.0.1:8080/private
```

ブラウザで `http://127.0.0.1:8080/private` を開くと、ダイアログが出る。
`alice` / `wonderland` を入れると本文が見える。

## 注意点 (`401 Unauthorized` の罠)

| ステータス | 意味 |
|---|---|
| 401 Unauthorized | 「**認証されていない** (誰だか分からない)」← 名前と裏腹に「未認証」 |
| 403 Forbidden | 「**認証はされているが、権限がない**」 |

英語名が紛らわしいだけで、HTTP の世界では `401 = 認証不足` で固定。
認可エラー (= ロール不足など) は次の step で `403` を返す。

## パスワード比較について

`USERS.get(user) != password` という比較は、本来は
**タイミング攻撃に弱い** (一致部分が増えると比較に時間がかかる)。

実運用では:

- `hmac.compare_digest(stored, given)` で **定数時間比較** する
- そもそも生パスワードは保存せず、**bcrypt / argon2 でハッシュ化** して保存する

ここまでやり始めると本題から外れるので、step1 では普通の `!=` で進める。
ハッシュとタイミング比較は **セッション認証 (step2)** で改めて触れる。

## 製品はここをどうやっているか

| 仕事 | 自作 (今回) | 製品 |
|---|---|---|
| Authorization ヘッダのパース | 自分で書く | フレームワーク (Flask: `request.authorization`) が自動でやる |
| ユーザー DB | ハードコード dict | DB / LDAP / IdP |
| パスワード比較 | `!=` (学習用) | bcrypt / argon2 + 定数時間比較 |
| WWW-Authenticate の返却 | 自分で書く | フレームワークの `@auth.login_required` などが自動 |

Basic 認証自体は **製品の出番がほぼない領域**。HTTP の素朴な機能なので、
フレームワークがちょっとした糖衣を着せている程度。
ここから先 (セッション / JWT / OIDC) で初めて、Auth0 / Cognito などが
肩代わりする領域に入っていく。

## step6 (本編最終形) からの追加箇所

このシリーズは `snapshots/step6/` の状態に上積みしている。
step6 と比べて、auth step1 で **追加・変更した箇所だけ** を抜き出すと:

### `server.py`

**変更なし**。認証は WSGI ゲートウェイの仕事ではないので一切触らない。

### `app.py`

| 場所 | 追加内容 |
|---|---|
| import | `import base64` を追加 |
| 定数 | `USERS` (学習用の仮ユーザー DB)、`UNAUTHORIZED_HEADERS` (`WWW-Authenticate` 付き) |
| ヘルパー関数 | `parse_basic_auth(environ)`、`unauthorized()` |
| ビュー関数 | `view_private(environ)` |
| `ROUTES` | `("GET", "/private"): view_private` を追加 |

それ以外 (`parse_qs_simple` / `read_body` / 既存のビュー全て / `app()`) は **無改修**。

差分を直接見たい場合:

```bash
diff snapshots/step6/app.py snapshots/auth-step1/app.py
```

## 完了条件

- [ ] `curl -u alice:wonderland http://127.0.0.1:8080/private` で 200 が返る
- [ ] `curl http://127.0.0.1:8080/private` で 401 + `WWW-Authenticate` が返る
- [ ] ブラウザでアクセスして認証ダイアログが出る
- [ ] `snapshots/auth-step1/` にコードを凍結する
