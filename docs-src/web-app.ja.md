# Web アプリ

```bash
pip install "kogo[serve]"
kogo fetch-viewer
kogo serve
```

ブラウザで <http://127.0.0.1:8080> を開きます。プレビューは
[Mozilla PDF.js](https://github.com/mozilla/pdf.js) による文字選択可能な表示で、
旧版ハイライトPDF・新版ハイライトPDF・左右比較PDFをダウンロードできます。

## Docker

```bash
docker compose up -d --build
```

ブラウザで <http://localhost:8080> を開きます。初期設定ではコンテナは
`127.0.0.1` にのみバインドされます。LAN上で共有する場合 — 認証機能は組み込まれていないため、
信頼できるネットワーク内でのみ以下を行ってください:

```bash
KOGO_HOST=0.0.0.0 docker compose up -d --build
```

`docker-compose.yml` では `mem_limit: 2g`、`cpus: 2`、`pids_limit: 256`
をバックストップとして設定しています。PyMuPDFとOpenCVは未検証のPDFを処理する
ネイティブコードのパーサーであるためです。正当な比較処理がOOMキルやスロットリング
される場合は、これらの値を上げてください。

## 設定

Webアプリが読み込む環境変数:

| 変数 | 初期値 | 説明 |
|---|---:|---|
| `JOBS_DIR` | `~/.local/share/kogo/jobs` | アップロードされたファイルと比較結果の保存先 |
| `MAX_UPLOAD_MB` | 100 | アップロードするPDF 1ファイルあたりの最大サイズ |
| `MAX_PAGES` | 200 | PDF 1ファイルあたりの最大ページ数 |
| `JOB_TTL_HOURS` | 24 | 比較結果を削除するまでの保持時間 |
| `MAX_CONCURRENT_JOBS` | 2 | 同時に処理する比較件数 |
| `JOB_TIMEOUT_SECONDS` | 900 | 1件の比較処理を中断するまでの上限時間(秒、最小60) |
| `KOGO_VENDOR_DIR` | `~/.local/share/kogo/vendor/pdfjs` | `kogo fetch-viewer` がローカルPDF.jsビューア資産をインストールする場所(サーバーもここを参照) |
| `KOGO_SOURCE_URL` | `https://github.com/ta-061/kogo` | Webアプリのフッターと `kogo serve` の起動バナーに表示するソースコードへのリンク |

!!! warning "組み込みの認証機能はありません"
    認証機能は組み込まれていません。`kogo serve` と初期設定のDocker Composeは
    ローカルホストにのみバインドされます。ローカル環境や信頼できるLANの外へ公開する
    前に、認証付きのリバースプロキシの背後に配置してください。

!!! note "AGPL-3.0 第13条"
    kogo を改変し、ネットワーク経由で他者に利用させる場合(例: 改変版のWebアプリを
    自前でホストする場合)、AGPL-3.0 第13条により、利用者に対応するソースコードを
    提供する必要があります。これを満たすには `KOGO_SOURCE_URL` を自分のフォークの
    リポジトリに設定してください。詳細は
    [README のライセンスの節](https://github.com/ta-061/kogo#license) を参照してください。
