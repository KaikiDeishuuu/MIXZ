# MIXZ 使用与测试说明

## 1. 当前状态

- API 服务代码可运行。
- 关键只读接口 smoke 已通过：`/health`、`/meta`、`/papers`、`/batches`、`/archive`、`/stats`。
- Docker 编排文件语法有效，但当前终端用户无 docker.sock 权限，无法直接 `docker compose up`。

## 2. 快速测试（本机）

### 2.1 启动 API

```bash
export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:password@host:5432/db'
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

### 2.2 接口验证

```bash
curl -i http://127.0.0.1:8000/health
curl -i "http://127.0.0.1:8000/papers?page=1&page_size=5"
curl -i http://127.0.0.1:8000/stats
```

### 2.4 一键自检（自动拉起 + 健康检查）

```bash
# 使用 psycopg DSN；若密码含特殊字符（如 /），先 URL 编码
export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:password@host:5432/db?sslmode=require'
bash scripts/mixz_self_check.sh
```

提示：
- Supabase 建议追加 `sslmode=require`
- 例如密码 `abc/def` 应写为 `abc%2Fdef`

脚本会自动检查：`/health`、`/meta`、`/papers`、`/batches`、`/archive`、`/stats`，并输出 PASS/FAIL 汇总。

### 2.3 DOI 明细验证

注意 DOI 含 `/`，必须用完整路径参数：

```bash
curl -i "http://127.0.0.1:8000/papers/10.9999/mixz.fixture.2026.001"
```

## 3. 写接口验证（建议在测试数据下）

### 3.1 重新分配批次

```bash
curl -i -X POST http://127.0.0.1:8000/admin/reassign-batch \
  -H 'Content-Type: application/json' \
  -d '{"doi":"10.9999/mixz.fixture.2026.001","target_batch_id":"1a1a0a45-2fd3-5cb4-aaaf-87ae4ee73a28"}'
```

### 3.2 触发重建

```bash
curl -i -X POST http://127.0.0.1:8000/admin/rebuild \
  -H 'Content-Type: application/json' \
  -d '{"render_only":true,"prune_redundant_batches":false}'
```

## 4. Docker 测试

```bash
export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:password@host:5432/db'
docker compose config
bash scripts/mixz_compose_up.sh
```

如果报权限错误，请先处理 Docker 用户权限，再执行。

当前会话可直接临时使用：

```bash
sg docker -c 'docker compose config'
sg docker -c 'bash scripts/mixz_compose_up.sh'
```

长期生效方式：重新登录 shell（或重启机器）让 `docker` 组在新会话中生效。

## 5. 常见问题

- 503 `MIXZ_POSTGRES_DSN is not set`：未注入数据库连接。
- 404 `/papers/{doi}`：旧路由问题，现已改为 `/papers/{doi:path}`，请确认运行的是最新代码。
- 回填全 0：通常是源 SQLite 本身为空，需指向真实历史库。
