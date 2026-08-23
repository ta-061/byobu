# kogo

kogo(校合)は、更新前と更新後のPDFを比較し、追加・削除された文字、図、数式、注釈を
ブラウザとマーカー入りPDFの両方でハイライトする、レイアウトを考慮したPDF差分ツールです。
「校合」は、改訂版を原本と照合するという意味の日本の出版用語に由来します。

すべての処理はローカルで行われ、外部サービスには何も送信されません。

## インストール

```bash
pip install kogo
```

## CLI

```bash
kogo diff old.pdf new.pdf -o out/
```

全フラグの一覧は [CLI リファレンス](cli.md) を参照してください。

## ライブラリ

```python
import kogo

result: kogo.ComparisonResult = kogo.compare_pdfs("old.pdf", "new.pdf", "out/")
print(result["summary"]["changed_pages"])
```

ライブラリとして使うだけなら `pip install kogo` で十分です(Web用の追加パッケージは不要)。
戻り値の完全なシグネチャと形式は [ライブラリ API リファレンス](library-api.md) を参照してください。

## Web アプリ

```bash
pip install "kogo[serve]"
kogo fetch-viewer
kogo serve
```

ブラウザで <http://127.0.0.1:8080> を開きます。設定やDockerでのデプロイについては
[Web アプリ](web-app.md) を参照してください。

## 次に読むもの

- [ライブラリ API](library-api.md) — `compare_pdfs` のシグネチャ、`ComparisonResult`
  の形式、書き込みなしモード、進捗コールバック
- [仕組み](architecture.md) — ページ対応付け、テキスト差分、視覚差分のアルゴリズム
- [レシピ](recipes/ci-integration.md) — CIステップから kogo を使う
- [よくある質問](faq.md)
