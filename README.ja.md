# kogo

kogo は、更新前と更新後のPDFを比較し、追加・削除された文字、図、注釈をブラウザとマーカー入りPDFの両方でハイライトする、レイアウトを考慮したPDF差分ツールです。

kogo(校合)は、改訂版を原本と照合するという意味の、日本の出版用語に由来する名前です。

![kogo results](https://ta-061.github.io/kogo/screenshot-results.png)

`kogo diff old.pdf new.pdf` — 削除は旧ページに赤、追加は新ページに緑でハイライトされ、変更された図の領域は両方でマークされます:

![旧版は赤で削除箇所、新版は緑で追加箇所がハイライトされるkogoの差分結果](https://ta-061.github.io/kogo/demo-ja.gif)

プロジェクトサイト: <https://kogo.tatu-sec.dev/>
ドキュメント: <https://kogo.tatu-sec.dev/manual/>

## 主な機能

- 欧文は単語単位、日中韓(CJK)は文字単位で精度の高いテキスト差分を検出(CJK拡張漢字 B〜J領域のまれな漢字を含む)
- ページ内の空白領域からレイアウトを分析して読み順を再構築するため、段組みやスライドのテキストボックスも正しく比較(単純な抽出順の混在を避ける)
- テキストと視覚的なページ特徴の両方を使った類似度ベースのページ対応付けにより、ページの挿入・削除があっても対応がずれない
- 図・数式・レイアウトの視覚差分を検出。テキスト領域はマスクして除外し、画像だけのページではスキャンや書き出しによる微小なズレを補正
- PDFに付いたハイライト・コメント・手書き注釈の追加・削除も検出
- 太字・斜体・文字サイズなど、文字自体は変わっていないスタイルのみの変更をアンバー色で検出
- マーカーはページ内容へ焼き込まれるため、注釈を表示しないビューアでも常に見える
- Mozilla PDF.jsによる、文字選択可能なWebプレビュー
- 旧版ハイライトPDF・新版ハイライトPDF・左右比較PDFをダウンロード可能
- すべての処理はローカルで行われ、外部サービスには何も送信されない

## クイックスタート

### CLIのみ

```bash
pip install kogo
kogo diff old.pdf new.pdf -o out/
```

### Webアプリ

```bash
pip install "kogo[serve]"
kogo fetch-viewer
kogo serve
```

`kogo fetch-viewer` は、Webプレビューで使うPDF.jsビューアの資産をローカルにダウンロードします([設定](#設定)を参照)。Dockerイメージにはあらかじめ同梱されているため、この手順は不要です。

ブラウザで <http://127.0.0.1:8080> を開きます。

### Docker

```bash
docker compose up -d --build
```

ブラウザで <http://localhost:8080> を開きます。初期設定ではコンテナは `127.0.0.1`(ローカルホスト)にのみバインドされます。LAN上で共有したい場合、認証機能は組み込まれていないため、信頼できるネットワーク内でのみ以下のようにしてください。

```bash
KOGO_HOST=0.0.0.0 docker compose up -d --build
```

`docker-compose.yml` では、PyMuPDFとOpenCVが未検証のPDFを処理するネイティブコードであることを踏まえ、`mem_limit: 2g` / `cpus: 2` / `pids_limit: 256` をバックストップとして設定しています。正当な比較処理がOOMキルやスロットリングされる場合は値を上げてください。`docker run` の場合は `--memory=2g --cpus=2 --pids-limit=256` が同等の指定です。

## CLIの使い方

```bash
kogo diff OLD.pdf NEW.pdf \
  -o kogo-diff \
  --dpi 144 \
  --sensitivity standard \
  --max-pages 200
```

オプション:

- `-o, --out` — 出力先ディレクトリ(初期値 `kogo-diff`)
- `--dpi` — 視覚差分の解析解像度、96〜180(初期値 144)
- `--sensitivity` — `high` / `standard` / `low`(初期値 `standard`)
- `--max-pages` — PDF 1ファイルあたりの最大ページ数(初期値 200)
- `--no-previews` — ページプレビュー画像の生成を省略
- `--json` — 結果をJSONとして標準出力に出力

`kogo serve` でWebアプリを起動します。

```bash
kogo serve --host 127.0.0.1 --port 8080
```

## ライブラリとして使う

差分エンジンは通常のPython APIです。`pip install kogo` だけで使えます(Web依存は不要)。

```python
import kogo

result = kogo.compare_pdfs("old.pdf", "new.pdf", "out/")
print(result["summary"])
# out/ に old-highlighted.pdf、new-highlighted.pdf、
# side-by-side.pdf、result.json、ページプレビューが生成されます。
```

`kogo.compare_pdfs` は、暗号化・空・ページ数超過・読み込み不能などの場合に `kogo.ComparisonError` を送出します。キーワード引数はCLIと同じです(`dpi`、`sensitivity`、`max_pages`、`previews`、`old_name`、`new_name`)。

## 設定

Webアプリは以下の環境変数を読み込みます。

| 変数 | 初期値 | 内容 |
|---|---:|---|
| `JOBS_DIR` | `~/.local/share/kogo/jobs` | アップロードファイルと比較結果の保存先 |
| `MAX_UPLOAD_MB` | 100 | アップロードするPDF 1ファイルの最大サイズ |
| `MAX_PAGES` | 200 | PDF 1ファイルあたりの最大ページ数 |
| `JOB_TTL_HOURS` | 24 | 比較結果を保持する時間(初期値。変更可能) |
| `MAX_CONCURRENT_JOBS` | 2 | 同時に処理する比較件数 |
| `JOB_TIMEOUT_SECONDS` | 900 | 1件の比較処理を中断するまでの上限時間(秒、最小60) |
| `KOGO_VENDOR_DIR` | `~/.local/share/kogo/vendor/pdfjs` | `kogo fetch-viewer` がローカルPDF.jsビューア資産をインストールする場所(サーバもここを参照します) |
| `KOGO_SOURCE_URL` | `https://github.com/ta-061/kogo` | Webアプリのフッターと `kogo serve` の起動時バナーに表示するソースコードへのリンク([ライセンス](#ライセンス)を参照) |

## 仕組み

テキストは単語単位(CJKは文字単位)で抽出し、空白領域を再帰的に分割することで読み順を再構築します。これにより、段組みやスライドのテキストボックス、行の折り返しが変わった段落も、PDF内部の生の抽出順ではなく、意味のある順序で比較されます。2つの文書のページは、テキストの類似度(画像中心のページでは視覚的特徴も併用)に基づく類似度ベースの配列アラインメントで対応付けられるため、ページの挿入・削除があっても残りの比較がずれません。残った差分はPythonの `difflib` で比較します。

図・数式などのテキスト以外のレイアウトは、各ページを画像として描画し、テキスト差分で検出済みの領域をマスクしたうえで画素差分を取ることで比較します。画像だけのページでは、画素差分の前にスキャンや書き出し処理による微小なズレを補正する位置合わせを行います。既存のPDF注釈(ハイライト・コメント・手書き)はフィンガープリント化して別途比較します。

## 制限事項

- 文字情報を持たないスキャンのみのPDFは視覚的な比較のみとなります。単語単位の文字差分が必要な場合は、事前にOCRで文字情報を付与してください
- パスワード保護されたPDFには対応していません
- 複雑な表や縦書きレイアウトは、自動差分に加えて目視確認が必要な場合があります
- 認証機能は組み込まれていません。`kogo serve` および初期設定のDocker Composeはローカルホストにのみバインドされます。ローカル環境や信頼できるLANの外へ公開する場合は、認証付きのリバースプロキシの背後に配置してください
- `MAX_UPLOAD_MB` は各アップロードの読み込み中に適用されますが、`Content-Length` ヘッダを送らないクライアント(chunked転送)からの大きなボディは、同じストリーミング検査でしか検出できず、事前には拒否されません。前段のリバースプロキシ側でもボディサイズの上限(例: nginxの `client_max_body_size`)を設定することを推奨します

## 開発

```bash
python -m unittest discover -s tests -v
```

## ライセンス

kogo は AGPL-3.0 で公開しています。詳細は [LICENSE](LICENSE) を参照してください。

Copyright (C) 2026 ta-061. Released under the GNU Affero General Public License v3.0 (AGPL-3.0-only).

PyMuPDF(および内部で使われるMuPDF)は AGPL-3.0 または商用ライセンスのデュアルライセンスで配布されています。kogo を再配布したり、ネットワークサービスとして提供する場合は、事前にライセンス条件を確認してください。

kogo を改変してネットワーク経由で他者に利用させる場合(例:改変版のWebアプリを自前でホストする場合)、AGPL-3.0 第13条により、利用者に対応するソースコードを提供する必要があります。Webアプリのフッターの「Source code」リンクと `kogo serve` の起動時バナーは、いずれも環境変数 `KOGO_SOURCE_URL`(初期値: 本リポジトリ)を参照しています。改変版を運用する場合は、第13条を満たすために **必ず** 自分のフォークのリポジトリURLに設定してください。

クレジット:

- [Mozilla PDF.js](https://github.com/mozilla/pdf.js)(Apache-2.0)
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF)(AGPL-3.0 または商用ライセンス)
- [OpenCV](https://github.com/opencv/opencv)(Apache-2.0)
- [FastAPI](https://github.com/tiangolo/fastapi)(MIT)
