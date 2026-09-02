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

## 后端项目结构

```
backend/
├── app/                          # 核心应用代码
│   ├── main.py                   # FastAPI 入口：路由注册 /api/health + CORS
│   ├── config.py                 # 配置（pydantic-settings）：DATABASE_URL、LLM 参数、embedding 参数等
│   ├── db.py                     # 异步连接池：psycopg3 + pgvector (register_vector_async)
│   ├── api/                      # HTTP API 路由
│   │   ├── documents.py          # 文档管理 API：POST/GET/DELETE /api/documents
│   │   └── chat.py               # RAG 问答 API：POST /api/chat（SSE 流式，citations 首帧 + LLM 代理）
│   └── ingest/                   # 摄取管道（PDF → 分块 → 向量 → 入库）
│       ├── models.py             # 数据模型：Chunk(text, page) dataclass
│       ├── pdf_parser.py         # PDF 解析：PyMuPDF 主 + pdfplumber 兜底，抛 ParseError
│       ├── chunker.py            # 递归分块：500 字符/80 重叠，CJK 分隔符，逐页
│       ├── embedder.py           # 向量化：fastembed BAAI/bge-small-zh-v1.5（512 维）
│       └── pipeline.py           # 摄取编排：extract_pages → recursive_chunk → embed_texts → INSERT
├── db/
│   └── init.sql                  # 建表 DDL：documents + chunks + HNSW 索引 (vector_cosine_ops)
├── scripts/
│   ├── init_db.py                # 数据库初始化脚本（执行 init.sql，幂等）
│   ├── make_sample_pdf.py        # 生成 3 页中文样例 PDF（pymupdf 内置 CJK 字体）
│   └── smoke.py                  # 端到端冒烟测试（上传 → ready → 流式问答断言 + --expect-unrelated）
├── data/                         # 上传文件存储（gitignored）
│   ├── uploads/                  # 上传的 PDF 文件（uuid 命名）
│   └── sample.pdf                # make_sample_pdf.py 生成的样例 PDF
└── pyproject.toml                # 依赖管理（uv, requires-python>=3.12）
```

### 核心数据流

```
上传 PDF → POST /api/documents
  → documents.status = 'processing'
  → asyncio.create_task (后台管道)
    → extract_pages()       [PyMuPDF → pdfplumber 兜底]
    → recursive_chunk()     [500字符/80重叠，逐页]
    → embed_texts()         [fastembed bge-small-zh-v1.5 → 512维]
    → INSERT chunks         [批量入库]
    → UPDATE status='ready' [或 'failed' + error 信息]
  → 前端轮询 GET /api/documents/{id} 直至 ready

提问 → POST /api/chat {messages}
  → embed_query() 向量化最后一条 user 消息
  → KNN 检索：SELECT ... ORDER BY embedding <=> query LIMIT top_k
  → 0 命中 → citations:[] + "知识库中未找到相关内容" + [DONE]
  → 有命中 → citations 事件（含引用来源）→ 代理 LLM SSE 流式回答 → [DONE]
  → 上游异常 → event: error + 中文说明 + [DONE]
```
