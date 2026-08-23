# kogo へのコントリビュート

## セットアップ

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[serve,dev]'
```

## テストの実行

```bash
python -m unittest discover -s tests -v
```

テストは差分エンジン(`tests/test_engine.py`)、CLI(`tests/test_cli.py`)、
Webアプリ(`tests/test_app.py`)をカバーしています。機能を追加した場合は、
それに合わせてテストを追加または拡張してください。

## コードスタイル

編集しているファイルに既にあるスタイルに合わせてください: 型注釈まみれの
docstringは書かない、非自明な*理由*(隠れた制約、回避策、微妙な不変条件)を
説明する場合を除いてコメントは書かない、投機的な抽象化より小さく焦点の
絞られた関数を優先する、といった方針です。

## プルリクエスト

- PRは1つの変更に絞り、無関係なリファクタリングを混ぜないでください。
- PRの説明には「何を」だけでなく「なぜ」を書いてください。
- PRを開く前に `python -m unittest discover -s tests -v` が通ることを確認してください。
- WebUIを触った場合は、どうテストしたか(ブラウザでの手動確認など、ブラウザテスト
  スイートは存在しないため)をPRの説明に書いてください。
- 公開API(`kogo/__init__.py`、`compare_pdfs` のシグネチャや戻り値の形式)、
  CLIフラグ、設定を変更した場合は、同じPRで `docs-src/`(クイックスタートに
  関わる場合は `README.md`/`README.ja.md` も)を更新してください。

## ドキュメントサイト

`docs-src/` には、<https://kogo.tatu-sec.dev/manual/> で公開されているマニュアルの
[mkdocs-material](https://squidfunk.github.io/mkdocs-material/) ソースが入っています。
ライブラリAPIリファレンスページは、docstringから
[mkdocstrings](https://mkdocstrings.github.io/) によって生成されます —
docstringを改善すれば、そのページも改善されます。ローカルでプレビューするには:

```bash
pip install -e '.[docs]'
mkdocs serve
```

サイトは `main` へのpushのたびに `.github/workflows/pages.yml` によってビルド・
デプロイされます。`docs/site/manual/` 以下を手動でコミットしないでください。

### マニュアルの翻訳

マニュアルは [mkdocs-static-i18n](https://ultrabug.github.io/mkdocs-static-i18n/)
により複数言語に対応しています。日本語訳はすべてのページに存在します
(`docs-src/*.ja.md`、`docs-src/recipes/*.ja.md`)。他の言語への翻訳も大歓迎です。
追加する手順:

1. 既存ページを英語版と同じディレクトリに `<ページ名>.<ロケール>.md`
   (例: `cli.fr.md`)としてコピーし、翻訳してください。コードブロック、
   フラグ名、環境変数名はそのまま残してください。
2. `mkdocs.yml` の `plugins.i18n.languages` に言語を登録し、
   `plugins.i18n.nav_translations.<ロケール>` に翻訳したナビゲーションラベルを
   追加してください。
3. まだ翻訳していないページがあっても問題ありません — プラグインが自動的に
   英語版にフォールバックします。
4. PRを開く前にローカルで `mkdocs serve` を実行し、表示とページ内リンクを
   確認してください(見出しのアンカーは翻訳後の見出しテキストから生成されるため、
   `architecture.md#page-alignment` のようなページ内リンクは、翻訳先のファイルでは
   翻訳後のアンカーを指す必要があります)。

ライブラリAPIページ(`library-api.md`/`.ja.md`)はPythonのdocstringから
mkdocstringsによって生成されるため、docstring自体を翻訳しない限り、ページの
言語に関わらずリファレンス部分は英語のままです — これは別の、より大きな取り組みで
あり、最初の翻訳PRの対象範囲外です。
