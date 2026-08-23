# CLI リファレンス

## `kogo diff`

```bash
kogo diff OLD.pdf NEW.pdf \
  -o kogo-diff \
  --dpi 144 \
  --sensitivity standard \
  --max-pages 200
```

| フラグ | 初期値 | 説明 |
|---|---:|---|
| `-o`, `--out` | `kogo-diff` | 出力先ディレクトリ |
| `--dpi` | `144` | 視覚差分のレンダリング解像度、96〜180 |
| `--sensitivity` | `standard` | 図・視覚要素の検出感度: `high` / `standard` / `low` |
| `--max-pages` | `200` | PDF 1ファイルあたりの最大ページ数 |
| `--no-previews` | オフ | ページプレビュー画像の生成を省略 |
| `--json` | オフ | テキストの要約ではなく、結果全体をJSONとして出力 |

`--json` を指定しない場合、対応付けられたページのペアを比較するたびに進捗が
標準エラー出力へ表示されます(`Comparing page N/total...`)。これはライブラリの
`on_progress` コールバックによるものです。[ライブラリ API](library-api.md) を参照してください。

## `kogo serve`

```bash
kogo serve --host 127.0.0.1 --port 8080
```

`serve` 追加パッケージが必要です: `pip install "kogo[serve]"`。設定については
[Web アプリ](web-app.md) を参照してください。

## `kogo fetch-viewer`

```bash
kogo fetch-viewer
```

Webプレビューで使用するローカルの [PDF.js](https://github.com/mozilla/pdf.js)
ビューア資産をダウンロードし、固定されたSHA-256チェックサムで検証します。
これらを同梱しているDockerでは不要です。
