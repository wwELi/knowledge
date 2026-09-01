# 本地知识库 RAG

基于 FastAPI + React 的本地知识库问答系统：上传 PDF → 解析分块 → 向量入库（pgvector）→ 基于检索结果流式问答（SSE）。

## 前置要求

- Docker（推荐，用于运行 Postgres；本机也可用 Homebrew 安装的 postgres + pgvector 替代，见下文常见问题）
- [uv](https://docs.astral.sh/uv/)（Python 包管理）
- Node ≥ 20.19

## 启动步骤

### 1. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`，填入你的 `LLM_API_KEY`（其余变量保持默认即可）。

### 2. 启动 Postgres（含 pgvector）

```bash
docker-compose up -d postgres
```

容器映射到本机 5433 端口（对应 `.env` 中的 `DATABASE_URL=postgresql://kb:kb@localhost:5433/kb`）。

> 没有 Docker？也可以用 Homebrew 安装的 Postgres：`brew install pgvector` 后 `brew services start postgresql@17`，创建 `kb` 用户与数据库，并让 5433 端口可连接（或相应修改 `DATABASE_URL`）。本项目本机开发即采用此方案。

### 3. 启动后端

```bash
cd backend
uv sync
uv run python scripts/init_db.py
uv run uvicorn app.main:app --reload --port 8000
```

### 4. 启动前端

新开一个终端：

```bash
cd frontend
npm i
npm run dev
```

### 5. 访问

浏览器打开 http://localhost:5173 ，上传 PDF 并提问。

## 冒烟测试

后端运行中（端口 8000）时，可运行端到端冒烟脚本（生成样例 PDF、上传、等待解析、流式问答断言）：

```bash
cd backend
uv run python scripts/make_sample_pdf.py        # 生成 data/sample.pdf
uv run python scripts/smoke.py --pdf data/sample.pdf
# 无关问题回归（断言零命中路径）：
uv run python scripts/smoke.py --pdf data/sample.pdf --expect-unrelated
```

两个命令均以退出码 0 并打印 `PASS` 为通过。

## 常见问题

- **首次运行时模型下载慢**：嵌入模型从 HuggingFace 下载，可切换镜像：
  ```bash
  export HF_ENDPOINT=https://hf-mirror.com
  ```
- **5433 端口被占用**：修改 `docker-compose.yml` 的端口映射（如 `"5434:5432"`），并同步修改 `.env` 中的 `DATABASE_URL`。
- **本机代理导致 LLM 调用失败**：后端 httpx 客户端已设置 `trust_env=False`，不会走系统代理直连 LLM。如果你把它改回 `trust_env=True`，需注意本机代理可能对 LLM 域名返回 502。
