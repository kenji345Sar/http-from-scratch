# Python のここが少し独特

> このファイルは、Python が他の言語（C# / Java / PHP / Go など）と
> 書き方が違うために「最初は引っかかる」ところをまとめておく場所。
> 必要になったときに 1 項目ずつ足していく。

---

## `dict` を「型 / 呼ぶ / 添え字 / isinstance」全部で使える件

このプロジェクトのコード中に、こういう書き方が混在している。

```python
def parse_request(raw: bytes) -> dict:        # ① 型ヒント
    ...

headers: dict[str, str] = {}                  # ② 型パラメータ付きの型ヒント

return f"received form: {dict(request.form)}\n"  # ③ 変換のために呼び出し
```

`dict` が型として書かれたり、関数のように呼ばれたり、`[]` で添え字されたりしているのに、`import` は要らない。**C# / Java から来ると「これは関数？型？キーワード？」と引っかかるはず。**

### 結論

- `dict` は **クラス（型オブジェクト）**。関数でも予約語でもない
- Python では **クラス自体も普通のオブジェクト**（"everything is an object"）
- だから、いろんな構文位置に置ける（型として / 呼び出しとして / 添え字として / 引数として）
- これは `dict` 特有ではなく、`int` / `str` / `list` / `set` / `tuple` / `frozenset` 全部同じ性質

### 1 つの名前、4 つの使い方

```python
>>> dict
<class 'dict'>            # それ自体を見ると「型（クラス）」

>>> dict()                # () で呼ぶと「インスタンスを作る」
{}

>>> def f() -> dict:      # 「-> 」のあとは「型ヒント」
...     ...

>>> dict[str, int]        # [] で添え字すると「型パラメータ付き dict」
dict[str, int]

>>> isinstance({}, dict)  # 型として比較
True
```

すべて **同じ 1 つの `dict` オブジェクト** が、別の位置に置かれているだけ。

### 他の言語との対比

| 概念 | Python | C# | Java | PHP |
|---|---|---|---|---|
| 辞書型そのもの | `dict`（クラス） | `Dictionary<K,V>`（クラス） | `Map<K,V>` インタフェース | `array`（型システム緩め） |
| 辞書を作るコード | `dict()` | `new Dictionary<string,int>()` | `new HashMap<>()` | `[]` |
| 型ヒント | `-> dict` | パラメータの型宣言 | パラメータの型宣言 | PHPDoc コメント |
| 型と「作る関数」の関係 | **同じオブジェクト** | クラス名 + `new` で別の概念 | クラス名 + `new` で別の概念 | 型システムが薄い |

C# / Java 出身だと「型を呼び出すには `new` が要る」「型と関数は別物」と思っているはず。Python は **「クラス自体を呼べばインスタンスができる」** 設計なので `new` が要らない。代わりに「型を直接呼んでいるように見える」コードになる。

### なぜそういう仕組みになっているか

実装としては:

| 構文 | 内部で呼ばれているもの | 効果 |
|---|---|---|
| `dict()` | `dict.__call__()` | インスタンス生成（クラスを呼ぶとインスタンスができる） |
| `dict(other)` | `dict.__init__(other)` | 別のマッピング/イテラブルから変換 |
| `dict[str, int]` | `dict.__class_getitem__((str, int))` | 型パラメータ付きの型表現（PEP 585、Python 3.9+） |
| `-> dict:` | 実行時には解釈されない、ただの注釈 | 型ヒント（型チェッカ・読み手向け） |
| `isinstance(x, dict)` | 型として比較 | x が dict のインスタンスか |

「複数の用途」は **複数の機能の寄せ集めではなく、同じ `dict` クラスが、各構文位置で別のメソッドに振り分けられているだけ**。

### import しなくていい理由

`dict` / `list` / `print` などは Python の `builtins` モジュールに入っていて、Python が起動するときに自動でグローバル名前空間に見える状態になっている。書いていないだけで **「常に `from builtins import *` 相当」が効いている** イメージ。

```
python3 -c "import builtins; print(builtins.dict is dict)"
# True ← どちらも同じオブジェクト
```

### このプロジェクトのどこに出てくるか

- 型ヒント: [`server.py`](../server.py) の `def parse_request(raw: bytes) -> dict:`
- 型パラメータ: 同じファイルの `headers: dict[str, str] = {}`
- 変換: [`flask_equivalent.py`](../flask_equivalent.py) の `dict(request.form)`

---

## 「import なしで使えるもの」は言語によって全然違う

前項で「`dict` は import なしで使える、builtins から自動で見えているから」と書いた。
これに関連して、**「何が import なしで使えるか」** は言語ごとに大きく違う。
他言語と並べると、Python がどのへんに居るかが見える。

### 結論

「自動でグローバルに見えるか」のゆるさで、Web 系言語は 3 段階に分かれる。

| 段階 | 例 | 何が import なしで使えるか |
|---|---|---|
| ① ゆるい（ほぼ全部見える） | **PHP** | 組み込み関数（`strlen` / `array_map` / `count` / `date`）全部、組み込みクラス（`DateTime` / `PDO`）全部 |
| ② 中間（基本型だけ自動） | **Python** / **Java** | 言語標準の基本型／関数だけ。それ以外は明示 import |
| ③ きつい（ほぼ何も自動でない） | **React / モダン JS（ES Modules）** | ブラウザ固有のグローバル (`window`, `document`, `Math`, `console`, `Array`) のみ。`useState` も `React` 自体も import |

### 各言語ごとの様子

**PHP — 組み込みは丸ごとグローバル**

```php
<?php
echo strlen("hello");        // import 不要
$d = new DateTime();         // import 不要
$arr = array_map(...);       // import 不要
```

PHP はデフォルトでグローバル名前空間に居て、組み込み関数・組み込みクラスが全部最初から見えている。Laravel でも `use Illuminate\Http\Request;` のような import はたまに出るが、`strlen` や `array_map` には永遠に import がない。

**Python — `builtins` だけ自動、それ以外は明示**

```python
print(len([1, 2]))           # print も len も builtins から自動

import json                  # 標準ライブラリでも明示
import socket
from urllib.parse import unquote_plus
```

自動で見えるのは [`builtins`](https://docs.python.org/ja/3/library/builtins.html) モジュールの中身だけ（`dict` / `list` / `print` / `len` / `range` 等）。`json` や `socket` のような標準ライブラリは明示 import。

**Java — `java.lang.*` だけ自動**

```java
String s = "hello";          // java.lang.String, 自動
System.out.println(s);       // java.lang.System, 自動

import java.util.HashMap;    // それ以外は明示
import java.io.File;
```

`java.lang` パッケージだけ自動。それ以外は全部 `import`。設計思想は Python に近い。

**React / モダン JS — ほぼ何も自動でない**

```javascript
import React, { useState } from 'react';
import { Button } from '@mui/material';
import axios from 'axios';

function App() {
  const [n, setN] = useState(0);
  return <Button onClick={() => setN(n + 1)}>{n}</Button>;
}
```

自動で見えるのはブラウザの組み込みグローバル（`window`, `document`, `console`, `Math`, `Array`, `JSON`, `fetch`）だけ。React 自身も、`useState` のような Hook も import が必要。**ES Modules は「1 ファイル 1 スコープ、明示的に出し入れする」設計**。

### なぜここまで違うのか

| 言語 | 当初の発想 | 結果 |
|---|---|---|
| PHP | HTML に埋め込むテンプレート言語として始まった。「とにかく手軽に書ける」優先 | 組み込みを全部グローバルに置いた |
| Python / Java | 構造化プログラミング志向。「explicit is better than implicit」 | 基本型だけ自動、ほかは明示 |
| モダン JS / TS | 昔の JS は「全部 window にぶら下げる」で名前衝突に死ぬほど苦しんだ。**その反動で**今は逆方向に振り切った | 何も自動にしない |

JS の「import 地獄」と呼ばれることもあるくらいの厳しさは、過去の「全部グローバル」時代の反省の上に立っている。

### 早見表

| 観点 | PHP | Python | Java | React (ES Modules) |
|---|---|---|---|---|
| 組み込み関数を import なしで使える | ✅ | ✅（builtins） | ✅（java.lang） | ✅（ブラウザ global） |
| 標準ライブラリを import なしで使える | ✅（だいたい） | ❌ | ❌ | ❌ |
| ユーザ定義クラスを import なしで使える | ❌（namespace 切れば） | ❌ | ❌ | ❌ |
| import の頻度 | 少ない | 中 | 多い | **超多い** |

「PHP は import がほぼ要らない、React はやたら import が多い」という肌感覚は両方とも正しくて、Python はその真ん中に居る、というのが今の Web 系言語の見取り図。

---

## （今後追加していく場所）

Python を読み書きしていて「これ独特だな」と感じたものをここに書き足していく。
候補（必要になってから書く）:

- デコレータ（`@app.route("/")` の `@` は何）
- `if __name__ == "__main__":` のおまじない
- `from app import app`: 同じ名前のモジュールとオブジェクトの混在
- 型ヒントは実行時に何もしないこと（型チェッカ専用）
- `with` 文と `__enter__` / `__exit__`
- ダックタイピング（型より「振る舞い」を見る）
