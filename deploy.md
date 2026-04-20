# MIXZ Deployment Guide

本文给出两种部署路径：

- 路径 A：本机 Python 启动（推荐先验证）
- 路径 B：Docker Compose 启动（适合长期运行）

## 1. 前置条件

- Linux/macOS
- Python 3.12+
- 已创建虚拟环境 `.venv`
- PostgreSQL 可访问（例如 Supabase）

## 2. 环境变量

必须设置：

```bash
# 推荐使用 psycopg 驱动方言（与当前 SQLAlchemy 配置一致）
export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:password@host:5432/db?sslmode=require'
```

注意：
- 如果密码包含 `/`、`@`、`:` 等特殊字符，必须先做 URL 编码（例如 `/` -> `%2F`）。
- Supabase 场景建议显式带上 `?sslmode=require`。

可选：

```bash
export MIXZ_ENV=production
export MIXZ_WEB_PORT=8080
```

## 3. 数据库迁移

```bash
bash scripts/mixz_migrate.sh
```

如果你只是先看 SQL，可离线检查：

```bash
alembic upgrade head --sql
```

## 4. 路径 A：本机 Python 启动 API

安装依赖：

```bash
.venv/bin/pip install -r requirements.txt
```

启动：

```bash
MIXZ_POSTGRES_DSN="$MIXZ_POSTGRES_DSN" .venv/bin/uvicorn apps.api.main:app --host 0.0.0.0 --port 8000
```

健康检查：

```bash
curl -fsS http://127.0.0.1:8000/health
```

## 5. 路径 B：Docker Compose 启动

启动：

```bash
bash scripts/mixz_compose_up.sh
```

停止：

```bash
bash scripts/mixz_compose_down.sh
```

访问：

- Site: `http://localhost:8080`
- API: `http://localhost:8080/api/health`

如果出现 `permission denied while trying to connect to docker API`，说明当前用户没有 docker 组权限。

如果你刚执行过 `sudo usermod -aG docker $USER`，当前 shell 通常还未刷新组信息，可临时这样执行：

```bash
sg docker -c 'docker compose config'
sg docker -c 'bash scripts/mixz_compose_up.sh'
```

然后重新登录 shell，使新组权限长期生效。

注意（生产环境经验）：
- 某些主机中，容器内访问 Supabase 会优先走 IPv6，可能出现 `Network is unreachable` 导致 API 数据接口 500。
- 若遇到该问题，建议使用“路径 C（systemd + host 网络）”作为生产方案。

## 6. 路径 C：systemd + Nginx（推荐生产）

适用于本机已运行 Nginx、并希望避免 Docker 网络/IPv6 问题的场景。

1) 写环境变量文件：

```bash
cat > /etc/mixz.env <<'EOF'
MIXZ_POSTGRES_DSN=postgresql+psycopg://user:password@host:5432/db?sslmode=require
MIXZ_ENV=production
EOF
chmod 600 /etc/mixz.env
```

2) 创建 systemd 服务：

```bash
cat > /etc/systemd/system/mixz-api.service <<'EOF'
[Unit]
Description=MIXZ FastAPI service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/.openclaw/workspace/mixz
EnvironmentFile=/etc/mixz.env
ExecStart=/root/.openclaw/workspace/mixz/.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now mixz-api.service
systemctl status --no-pager mixz-api.service
```

3) Nginx 反向代理 `/api/`：

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8000/;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_http_version 1.1;
}
```

4) 重载 Nginx：

```bash
nginx -t && systemctl reload nginx
```

5) 验证：

```bash
curl -i https://mixz.wulab.tech/api/health
curl -i "https://mixz.wulab.tech/api/papers?page=1&page_size=3"
```

## 7. 回填历史数据（可选）

先演练：

```bash
MIXZ_POSTGRES_DSN="$MIXZ_POSTGRES_DSN" .venv/bin/python scripts/mixz_backfill_postgres.py --sqlite-path site/data/papers.db --dry-run
```

正式执行：

```bash
MIXZ_POSTGRES_DSN="$MIXZ_POSTGRES_DSN" .venv/bin/python scripts/mixz_backfill_postgres.py --sqlite-path site/data/papers.db
```

## 8. 发布前最小检查清单

建议先跑一次一键自检：

```bash
bash scripts/mixz_self_check.sh
```

- `GET /health` 返回 200
- `GET /papers?page=1&page_size=5` 返回 200
- `GET /stats` 返回 200
- Alembic 版本在 `head`
- 真实数据回填后 `total_papers > 0`（如适用）
