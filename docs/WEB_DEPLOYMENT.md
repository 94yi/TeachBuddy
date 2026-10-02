# TeachBuddy 网页版运行与部署

网页端复用原项目的教案模板、文字处理、分类规则和 Word/PPT 导出，桌面版仍可从 main.py 启动。网页端使用 Python 3.11+（容器为 3.12）、FastAPI 和无 CDN 依赖的原生前端。无需安装 PyQt 或 Node，也无需前端构建。

## 本地运行

在项目目录建立独立 Python 环境：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-web.txt
.\.venv\Scripts\python.exe -m uvicorn web.server:app --host 127.0.0.1 --port 8765
```

打开 http://127.0.0.1:8765 。开发模式不配置 AI 也能生成离线模板、编辑教案、导入资料、导出文档和整理文件。直接 uvicorn 启动从进程环境读取配置；不会自动读取 .env。生产环境通过下面的 Docker Compose 读取 .env。

## 配置

```sh
python3 scripts/configure_web.py
```

脚本交互式创建权限为 600 的 .env，密码和 API Key 不回显，已有文件不会覆盖。也可复制 .env.example 并手工填写。

| 配置 | 用途 |
| --- | --- |
| TEACHBUDDY_PASSWORD | 网站访问密码；生产必填，建议至少 12 位 |
| TEACHBUDDY_SECRET | 至少 32 字符的随机会话签名密钥，生产必填，备份时保留 |
| TEACHBUDDY_DOMAIN | 已解析到服务器的域名，仅 HTTPS 配置需要 |
| TEACHBUDDY_PORT | 本机回环端口，默认 8765 |
| TEACHBUDDY_SECURE_COOKIE | 经 HTTPS 访问设 true，SSH 隧道本地 HTTP 设 false |
| AI_BASE_URL / AI_API_KEY / AI_MODEL | 服务端 AI 配置，网址为兼容 Chat Completions 的基地址 |
| AI_FALLBACK_BASE_URL / AI_FALLBACK_API_KEY / AI_FALLBACK_MODEL | 可选备用服务 |
| AI_TIMEOUT | 单次 AI 请求超时秒数，默认 90 |

AI 配置为空时页面明确显示离线状态。真实模型连通性需要服务器配置后验收。API Key 不下发到浏览器。访问密码是小范围共享入口，不是组织账号系统；每个浏览器的签名会话拥有独立资料、模板与历史，不支持跨设备账号同步。清除浏览器 Cookie 后无法找回该会话的资料，请及时导出。更换签名密钥会使已有会话失效。

## 服务器部署

先确认目标主机、安装目录、域名和现有反向代理。把本项目上传至独立目录（例如 ~/apps/teachbuddy），保留 .env 和命名卷。服务器需要 Docker Engine 与 Compose v2。

### 使用服务器现有 Nginx / Caddy

```sh
docker compose up -d --build
curl --fail http://127.0.0.1:8765/healthz
```

容器仅监听服务器 127.0.0.1:8765，通过现有 HTTPS 站点转发到此端口。在 .env 设置 TEACHBUDDY_SECURE_COOKIE=true。代理读取超时建议 180 秒，上传大小建议 55 MB。避免修改与 TeachBuddy 无关的站点。

Nginx location 示例：

```nginx
location / {
    proxy_pass http://127.0.0.1:8765;
    proxy_set_header Host $host;
    proxy_read_timeout 180s;
    client_max_body_size 55m;
}
```

### 新建独立 HTTPS 站点

仅当服务器 80/443 端口空闲时使用。域名 A/AAAA 记录须指向这台服务器，防火墙允许 80/443。

```sh
docker compose -f compose.yaml -f compose.https.yaml up -d --build
curl --fail https://YOUR_DOMAIN/healthz
```

Caddy 自动申请和续期证书，HTTPS 覆盖配置强制安全 Cookie。

### 没有域名

启动基础 compose 后，从本机建立 SSH 隧道（替换 user@host）：

```sh
ssh -N -L 8765:127.0.0.1:8765 user@host
```

浏览器打开 http://127.0.0.1:8765 。不要把包含访问密码的登录入口直接发布为公网明文 HTTP。

## 数据、更新与回滚

- 应用以非 root 用户运行，根文件系统只读，用户数据保存在 teachbuddy_teachbuddy_data 命名卷。临时文件在 /tmp，AI 与上传并发控制按单 worker 设计。
- 文件整理只处理主动上传的副本。先预览分类和重复，再下载 ZIP；不会移动或删除电脑原文件。默认保留重复文件，勾选后才排除。
- 导入支持 .txt / .md / .docx；自定义模板还支持结构化 .json。导出的 PPT 是基础结构化课件，建议下载后检查排版。
- 更新前保留上次镜像：docker image tag teachbuddy-web:local teachbuddy-web:previous；然后重新构建启动。需要回滚时将 previous 标回 local，再执行 docker compose up -d --no-build --force-recreate app。
- 备份需同时保留 .env（私密保存）和数据卷。先停止 app，再用 Docker 的卷备份方式归档；恢复后再启动。不要执行 docker compose down -v，它会删除持久数据。
- 运行状态：docker compose ps；日志：docker compose logs --tail=100 app。不要把含凭据的 .env 或 docker compose config 完整输出发到公开渠道。

## 验证

```sh
python -m pip install -r requirements-test.txt
python -m pytest -q
```

发布后验收：健康检查、密码登录、离线教案、Word/PPT 下载、知识库导入、分类 ZIP 下载、手机页面、刷新后历史恢复；AI 配置完成后再验证生成、讨论与备用服务。真实 AI 的内容质量与学校场景适配仍需使用者校对。
## 验证过的版本与容器镜像源

网页依赖已固定到本次通过测试的版本。本机 Python 3.14 完成 49 项接口测试及 Chrome 桌面/390px 手机交互测试，Linux Python 3.12 镜像完成启动、认证、模板生成和 Word 导出检查。

如网络无法拉取 Docker Hub 的官方 Python 镜像，可使用 AWS ECR 提供的同一 Docker 官方镜像：

```sh
docker compose build --build-arg PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.12-slim
docker compose up -d --no-build
```

高级验证（本机需已安装 Chrome，容器测试需 Docker）：

```sh
python tests/browser_smoke.py
python tests/container_smoke.py
```

浏览器检查使用临时密码和隔离测试数据，输出截图到 artifacts/；容器检查只创建并移除带随机名称的测试容器。