# Recipe: self-hosting `kogo serve` beyond localhost

kogo's web app has no built-in authentication by design — `kogo serve` and
the default `docker-compose.yml` only bind to `127.0.0.1`. If you want to
share it with a team over a network, put a reverse proxy with authentication
in front of it rather than binding it directly. Two concrete configs below;
adapt the auth mechanism to whatever your team already uses (basic auth here
is the simplest starting point, not a recommendation to stop there).

## nginx

```nginx
server {
    listen 443 ssl;
    server_name kogo.internal.example.com;

    # ssl_certificate / ssl_certificate_key ...

    auth_basic "kogo";
    auth_basic_user_file /etc/nginx/kogo.htpasswd;

    # Matches MAX_UPLOAD_MB (default 100) with headroom for both files plus
    # multipart overhead; keep this above whatever you set MAX_UPLOAD_MB to.
    client_max_body_size 220m;

    location / {
        proxy_pass http://127.0.0.1:8080;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 920s;  # above JOB_TIMEOUT_SECONDS (default 900)
    }
}
```

Generate the password file once: `htpasswd -c /etc/nginx/kogo.htpasswd yourname`.

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

Generate the bcrypt hash with `caddy hash-password`.

## Why the reverse proxy needs its own size limit

`kogo serve` enforces `MAX_UPLOAD_MB` while *reading* each upload, but a
client that omits `Content-Length` (chunked transfer) bypasses the early
size check — the streaming check inside kogo is the remaining backstop for
that case. Setting `client_max_body_size`/`request_body.max_size` at the
proxy is defense in depth, not optional hardening, when kogo is reachable
beyond a single trusted machine.

## Docker Compose

If you're running the bundled `docker-compose.yml`, put the reverse proxy in
front of the container instead of setting `KOGO_HOST=0.0.0.0` and exposing
the port directly — keep kogo's own port bound to `127.0.0.1` (the default)
and let the proxy be the only thing listening on a public interface.
