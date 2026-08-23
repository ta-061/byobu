# レシピ: `kogo serve` をlocalhostの外でセルフホストする

kogo のWebアプリは設計上、組み込みの認証機能を持ちません — `kogo serve` と初期設定の
`docker-compose.yml` は `127.0.0.1` にのみバインドされます。チーム内でネットワーク越しに
共有したい場合は、直接バインドするのではなく、認証付きのリバースプロキシを前段に
配置してください。以下は2つの具体的な設定例です。認証方式はチームで既に使っている
ものに合わせて調整してください(ここでのBasic認証は最も手軽な出発点であり、
そこで止めるべきという推奨ではありません)。

## nginx

```nginx
server {
    listen 443 ssl;
    server_name kogo.internal.example.com;

    # ssl_certificate / ssl_certificate_key ...

    auth_basic "kogo";
    auth_basic_user_file /etc/nginx/kogo.htpasswd;

    # MAX_UPLOAD_MB(初期値100)に、2ファイル分とマルチパートのオーバーヘッド分の
    # 余裕を加えた値。MAX_UPLOAD_MB に設定した値より必ず大きくしてください。
    client_max_body_size 220m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 920s;  # JOB_TIMEOUT_SECONDS(初期値900)より大きく
    }
}
```

パスワードファイルは一度だけ生成します: `htpasswd -c /etc/nginx/kogo.htpasswd yourname`。

## Caddy

```caddyfile
kogo.internal.example.com {
    basicauth {
        yourname <bcrypt-hash>
    }
    request_body {
        max_size 220MB
    }
    reverse_proxy 127.0.0.1:8080 {
        transport http {
            read_timeout 920s
        }
    }
}
```

bcryptハッシュは `caddy hash-password` で生成します。

## リバースプロキシ自身にもサイズ上限が必要な理由

`kogo serve` は各アップロードを*読み込む際*に `MAX_UPLOAD_MB` を適用しますが、
`Content-Length` を送らないクライアント(chunked転送)は、この早期のサイズチェックを
回避できます — kogo内部のストリーミングチェックが、その場合の最後の砦になります。
kogo が単一の信頼できるマシンを超えて到達可能な場合、プロキシ側で
`client_max_body_size`/`request_body.max_size` を設定することは、任意の追加対策ではなく
多層防御として必須です。

## Docker Compose

同梱の `docker-compose.yml` を使っている場合は、`KOGO_HOST=0.0.0.0` を設定して
ポートを直接公開するのではなく、コンテナの前段にリバースプロキシを配置してください —
kogo自身のポートは(初期設定のとおり)`127.0.0.1` にバインドしたままにし、
公開インターフェースをリッスンするのはプロキシだけにします。
