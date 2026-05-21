# auth step6: パスキー / WebAuthn（概念整理 + ライブラリ利用）

## まずパスキーとは何か

> **パスワードを使わずに、「端末 (iPhone / Mac / Android / Windows / YubiKey)
> の中の秘密鍵」で本人確認をする仕組み**。

普段の体験で言うと:

- ログイン画面で「パスキーで続行」を選ぶ
- 端末が Touch ID / Face ID / Windows Hello / PIN を聞いてくる
- 一瞬でログインが終わる (パスワードもメールに飛ぶ確認コードも要らない)

これを実現している規格名が **WebAuthn** (W3C のブラウザ API) で、
**パスキー** は「Apple / Google / Microsoft が普及のために付けた商品名」に近い。
中身はほぼ同じものを指している。

## なぜ作られたか (= パスワード認証の何が困っていたか)

| パスワード | パスキー |
|---|---|
| ユーザが **覚えて入力する** | 端末の中の鍵が **自動で署名する** |
| サーバが **パスワードハッシュ** を保管 | サーバは **公開鍵だけ** を保管 |
| DB が漏れたら全ユーザが危険 | 公開鍵が漏れても **無害** (秘密鍵は端末に閉じている) |
| **フィッシング耐性なし** (ユーザが偽サイトに入力できる) | **フィッシング耐性あり** (鍵が「正しい origin」しか署名しない) |
| 機種変したらパスワード再入力 | iCloud Keychain / Google Password Manager で **端末間同期** |

→ パスキーが解いているのは **「人間がパスワードを覚える / 入力する」モデルそのもの**。

## ざっくりどう動くか (大づかみ)

```
   登録のとき (1 回だけ)
   ────────────────────
   端末    : 鍵ペアを作る (秘密鍵 / 公開鍵)
   端末    : 秘密鍵は端末の金庫 (Secure Enclave / TPM) にしまう  ★ 一生出さない
   端末    : 公開鍵だけサーバに送る
   サーバ  : 公開鍵を DB に保存

   ログインのとき (毎回)
   ────────────────────
   サーバ  : ランダムな文字列 (challenge) を送る
   端末    : Touch ID 等で本人確認 → 秘密鍵で challenge に署名
   端末    : 署名をサーバに送る
   サーバ  : 保存してある公開鍵で署名を検証する
```

要点だけ:

- **秘密鍵は端末の外に出ない**。サーバにも、ネットにも、iCloud にも (正確には iCloud は同期するが OS の金庫の中だけ)
- サーバ側のロジックは **「公開鍵で署名を検証する」だけ**。step3 の JWT 検証と似たノリ

これが分かれば最低限の地図はできた。以降は **「ちゃんと書こうとすると何が乗っているか」** を見ていく。

## このステップで自作しない理由

ここまでの大づかみは簡単だが、**実際にちゃんと書こうとすると一気に重くなる**:

- **公開鍵暗号 (ECDSA / EdDSA)**: 楕円曲線の演算が必要。stdlib にあるが扱いが面倒
- **CBOR**: 「JSON のバイナリ版」。認証器からの返答はこれで包まれている
- **COSE**: 鍵フォーマットの規格。CBOR の中の公開鍵を読むのに必要
- **attestation**: 「この鍵は正規の認証器が作ったものです」の証明。検証ロジックが大きい
- **origin / rp_id ハッシュの厳密な検証**: フィッシング耐性の肝。間違えると無意味になる
- **sign_count のリプレイ検知**: クローン認証器を検出する地味なロジック

これらをすべて自作すると、step1〜5 の合計より大きいコード量になる。
しかも **間違えるとセキュリティが崩れる領域** で、**「自作するな」の代表例**。

そこで step6 では:

- 自作はしない (= 実装ファイルを変更しない)
- 代わりに「**ライブラリの何をどう呼ぶか / どこから先がライブラリの仕事か**」
  を理解することを目標にする

具体的に押さえるのは次の 4 つ:

1. **WebAuthn / FIDO2 / パスキー** の用語の関係
2. **2 つの儀式 (ceremony)**: 登録と認証の流れの全体図
3. **秘密鍵がどこにあるか** (端末の金庫の正体)
4. サーバ側コードの「**自分で書く部分 / ライブラリに任せる部分** の境界」

## 用語整理

| 用語 | 何 | 立ち位置 |
|---|---|---|
| **WebAuthn** | W3C の Web 仕様。ブラウザに `navigator.credentials.create/get` を生やす | フロントエンド API |
| **CTAP2** | ブラウザ (or OS) と認証器が話す USB/BLE/NFC プロトコル | ブラウザより下 |
| **FIDO2** | WebAuthn + CTAP2 のセット呼び名 | 規格群の総称 |
| **パスキー** | 「**端末間で同期される / 検出可能 (discoverable)**」 タイプの WebAuthn 認証情報。ユーザ視点の呼び名 | 製品名・マーケ用語に近い |
| **Authenticator** | 鍵を持つもの。Touch ID / Windows Hello / iCloud Keychain / YubiKey など | デバイス側 |
| **Relying Party (RP)** | 認証を受ける側 = 自分のアプリ | サーバ + フロント |
| **attestation** | 「この鍵を生成したのは正規の認証器です」という証明 (任意) | 登録時のみ |
| **assertion** | 「秘密鍵を持っている本人です」という署名 (毎回) | 認証時 |

要点: **WebAuthn が技術名、パスキーが商品名**。挙動の中核は同じ。

## 2 つの儀式

### 登録 (registration) ceremony

```
[ブラウザ]                                    [サーバ (RP)]
                                              ライブラリ呼び出し:
                                                generate_registration_options(...)
                                          ◄─  challenge, rp_id, user 情報 (JSON)
   │
   ├─ navigator.credentials.create({publicKey: options})
   │
   ├─ ブラウザ → OS → 認証器 (Touch ID 等)
   │      └─ 鍵ペアを生成 (秘密鍵は Secure Enclave 内に留まる)
   │      └─ 公開鍵 + attestation を返す
   │
   POST /passkey/register/complete  (credential JSON)
   ├─────────────────────────────────────►
                                              ライブラリ呼び出し:
                                                verify_registration_response(...)
                                                 - origin 検証
                                                 - rp_id ハッシュ検証
                                                 - challenge 一致
                                                 - 署名検証
                                              public_key, credential_id を DB に保存
                                          ◄─  200 OK
```

### 認証 (authentication) ceremony

```
[ブラウザ]                                    [サーバ (RP)]
                                              ライブラリ呼び出し:
                                                generate_authentication_options(...)
                                          ◄─  challenge (JSON)
   ├─ navigator.credentials.get({publicKey: options})
   │
   ├─ ブラウザ → OS → 認証器
   │      └─ 秘密鍵で challenge に署名
   │      └─ signature + clientDataJSON + authenticatorData を返す
   │
   POST /passkey/login/complete  (assertion JSON)
   ├─────────────────────────────────────►
                                              ライブラリ呼び出し:
                                                verify_authentication_response(...)
                                                 - origin 検証
                                                 - challenge 一致
                                                 - 保存済み公開鍵で署名検証
                                                 - sign_count 単調増加 (リプレイ検知)
                                              セッション発行 (= step2 と同じ)
                                          ◄─  200 OK + Set-Cookie
```

## サーバ側: ライブラリで書くとこのくらい

代表的な Python ライブラリ `py_webauthn` を使った最小例 (= 自作で代用できる
部分のほぼ全てがライブラリ呼び出し):

```python
# pip install webauthn
from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    UserVerificationRequirement,
    ResidentKeyRequirement,
)

RP_ID = "localhost"
RP_NAME = "http-from-scratch"
ORIGIN = "http://localhost:8080"

# ---- 登録 begin ----
def passkey_register_begin(user_id: bytes, user_name: str):
    options = generate_registration_options(
        rp_id=RP_ID,
        rp_name=RP_NAME,
        user_id=user_id,
        user_name=user_name,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,   # passkey
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    # options.challenge を セッション側にも保存する
    CHALLENGES[user_id] = options.challenge
    return options_to_json(options)

# ---- 登録 complete ----
def passkey_register_complete(user_id: bytes, client_response: dict):
    verification = verify_registration_response(
        credential=client_response,
        expected_challenge=CHALLENGES.pop(user_id),
        expected_origin=ORIGIN,
        expected_rp_id=RP_ID,
    )
    PASSKEYS[user_id] = {
        "credential_id": verification.credential_id,
        "public_key": verification.credential_public_key,
        "sign_count": verification.sign_count,
    }

# ---- 認証 begin ----
def passkey_login_begin():
    options = generate_authentication_options(rp_id=RP_ID)
    CHALLENGES["__pending"] = options.challenge
    return options_to_json(options)

# ---- 認証 complete ----
def passkey_login_complete(client_response: dict):
    # client_response.response.userHandle で誰のクレデンシャルか分かる
    user_id = base64url_decode(client_response["response"]["userHandle"])
    record = PASSKEYS[user_id]
    verification = verify_authentication_response(
        credential=client_response,
        expected_challenge=CHALLENGES.pop("__pending"),
        expected_rp_id=RP_ID,
        expected_origin=ORIGIN,
        credential_public_key=record["public_key"],
        credential_current_sign_count=record["sign_count"],
    )
    record["sign_count"] = verification.new_sign_count
    # 以後は step2 と同じ。セッションを発行する。
```

**実装側で書くもの**:

- 4 つの HTTP エンドポイント (`register/begin`, `register/complete`, `login/begin`, `login/complete`)
- `CHALLENGES` をセッションや Redis に持つ (リプレイ対策)
- 検証成功後は **step2 のセッション** または **step3 の JWT** を発行する。
  パスキーは「**最初の本人確認**」を置き換えるもので、それ以降のリクエスト
  認証は今まで通り。

**ライブラリに任せるもの**:

- CBOR / COSE のパース
- 署名検証 (ES256 / EdDSA / RS256)
- origin / rp_id ハッシュの検証
- attestation の検証
- sign_count のリプレイ検知ロジック

## フロント側 (最小 JS)

```html
<button id="register">register passkey</button>
<button id="login">login with passkey</button>

<script>
const b64uToBytes = s => Uint8Array.from(atob(s.replace(/-/g,'+').replace(/_/g,'/')), c => c.charCodeAt(0));
const bytesToB64u = b => btoa(String.fromCharCode(...new Uint8Array(b))).replace(/\+/g,'-').replace(/\//g,'_').replace(/=+$/,'');

document.getElementById('register').onclick = async () => {
  const opts = await fetch('/passkey/register/begin', {method:'POST'}).then(r => r.json());
  opts.challenge = b64uToBytes(opts.challenge);
  opts.user.id   = b64uToBytes(opts.user.id);
  const cred = await navigator.credentials.create({publicKey: opts});
  // cred はそのままだと送れないので、ArrayBuffer を base64url にして送る
  await fetch('/passkey/register/complete', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      id: cred.id,
      rawId: bytesToB64u(cred.rawId),
      type: cred.type,
      response: {
        clientDataJSON: bytesToB64u(cred.response.clientDataJSON),
        attestationObject: bytesToB64u(cred.response.attestationObject),
      },
    }),
  });
};
</script>
```

ポイント: **ブラウザの API が `ArrayBuffer` を返す** ので、JSON で送るには
base64url で包む必要がある。これだけは手で書く部分。

## 秘密鍵はどこにあるか

| 環境 | 秘密鍵の保管庫 |
|---|---|
| iPhone / Mac | Secure Enclave + **iCloud Keychain** 同期 |
| Android / Chrome | TEE (Trusted Execution Environment) + **Google Password Manager** 同期 |
| Windows | Windows Hello (TPM) |
| YubiKey などのハードキー | キー本体の中。**端末にも OS にもコピーされない** |
| 1Password / Bitwarden | ベンダーのパスワードマネージャー内 |

要点:

- **秘密鍵は OS / ハードウェアに閉じ込められている**。サーバには一度も渡らない
- **パスキー (同期型)** は便利だが、**iCloud / Google アカウントが侵害される
  と全部失われる** 弱点もある。エンタープライズではあえて **同期しない
  (device-bound) 鍵** を選ぶ場合もある (YubiKey など)

## 製品はここをどうやっているか

| 仕事 | 自作 (今回はしない) | 製品 |
|---|---|---|
| `register/login` の 4 エンドポイント | `py_webauthn` で書く | Auth0 Passkeys、Clerk、Stytch、Hanko、Keycloak |
| 鍵ストレージ (DB) | 自前 | 製品が肩代わり |
| メール認証 / フォールバック | 自前 | 製品が一式持ってる |
| アカウントリカバリ | 大問題 (鍵を失った人) | 製品が UX を用意 |
| クロスデバイス登録 (QR コード) | ブラウザがやる | 製品が UX を用意 |

ライブラリ候補:

| 言語 | ライブラリ |
|---|---|
| Python | `py_webauthn` (Duo Security) |
| Node | `@simplewebauthn/server` |
| Go | `go-webauthn` |
| Rust | `webauthn-rs` |
| Java | `webauthn4j` |

製品 (SaaS / OSS):

| 製品 | 種別 | 特徴 |
|---|---|---|
| Auth0 Passkeys | SaaS | 既存 IDaaS に組み込み |
| Clerk | SaaS | デフォルトでパスキー対応の DX |
| Stytch | SaaS | パスワードレス専業 |
| Hanko | OSS / SaaS | パスキー特化 OSS |
| Keycloak | OSS | エンタープライズ向け |

## パスキーは何を置き換えて、何を置き換えないか

| シリーズの step | パスキーで置き換わるか |
|---|---|
| step1 Basic 認証 | 完全に置き換わる |
| step2 セッション (ログイン部分) | **ログインの瞬間だけ**。以後の `sid` 運用は同じ |
| step3 JWT | 置き換わらない (API のアクセス手段は別問題) |
| step4 認可 (RBAC) | 置き換わらない (認証と認可は別) |
| step5 OAuth/OIDC | 置き換わらない。IdP の **裏のログイン手段** がパスキーになる |

つまりパスキーは **「最初の本人確認」** の手段を変えるだけ。
セッションや JWT や認可は、これまで通り上に積み上がる。

## シリーズ全体の振り返り

`http-from-scratch` の auth シリーズで触ったのは以下:

| step | 自作したもの | 何が肩代わりされるか (本番) |
|---|---|---|
| 概念 | (用語と全体像) | — |
| step1 | Basic 認証 | フレームワークが少しだけ糖衣 |
| step2 | セッション + Cookie + パスワードハッシュ | フレームワーク (`flask.session` 等) |
| step3 | JWT (HS256) | `PyJWT`、Auth0 / Cognito の access token |
| step4 | RBAC | IDaaS のロール機能、Casbin、OPA |
| step5 | OAuth 2.0 / OIDC のフロー | Auth0 / Cognito / Keycloak / Clerk |
| step6 | (自作せず) パスキー / WebAuthn | `py_webauthn` + 製品が UX を提供 |

**学んだことの本質**:

- 認証・認可は **HTTP の上に積み上がっている薄い層** であって、魔法ではない
- 製品は **「自分で書くと面倒な部分」を肩代わり** しているだけで、内部の
  動きは同じ
- どの step も `server.py` (WSGI ゲートウェイ) には触っていない。
  **認証・認可はアプリ側の関心事** であり、HTTP 層には漏らさない設計が
  保てている

## 完了条件

このステップは自作しないので、コード変更とスナップショットはなし。

- [ ] `py_webauthn` の `generate_registration_options` / `verify_*` の
      4 関数の役割が説明できる
- [ ] 「秘密鍵はサーバに来ない」 を一行で説明できる
- [ ] パスキーが置き換えるのは「最初の本人確認」だけで、セッション・JWT・
      RBAC・OIDC は上に積まれ続けることが理解できている
