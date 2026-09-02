# AGENTS.md

本地知识库 RAG：上传 PDF → 解析分块 → 向量入库（pgvector）→ 检索 + 流式问答（SSE）。后端 FastAPI(Python 3.12, uv)，前端 Vite+React 19+antd@6+@ant-design/x+Tailwind v4。

## 开发命令

```bash
# 数据库（Docker，端口 5433，库/用户/密码均为 kb）
docker-compose up -d postgres          # 注意：本机无 docker compose 子命令，用独立 docker-compose 二进制
cd backend && uv run python scripts/init_db.py   # 建表，幂等；仅清空数据卷后需重跑

# 后端（8000）
cd backend && uv run uvicorn app.main:app --reload --port 8000

# 前端（5173）
cd frontend && npm i && npm run dev

# 端到端冒烟（cwd 必须是 backend/，--pdf 用相对路径 data/sample.pdf）
cd backend && uv run python scripts/make_sample_pdf.py
cd backend && uv run python scripts/smoke.py --pdf data/sample.pdf
cd backend && uv run python scripts/smoke.py --pdf data/sample.pdf --expect-unrelated
```

**无单元测试是刻意设计**（用户明确选择）。验证靠真实冒烟：curl 真实调用、`smoke.py`、Playwright MCP（`skill_mcp mcp_name="playwright"`）。不要为代码补测试框架。

## 关键架构事实

- **数据库**: Postgres 跑在 **5433**（非 5432），镜像 `docker.m.daocloud.io/pgvector/pgvector:pg17`（国内镜像源，勿改回 docker.io）。schema：`documents`（status 三态 processing/ready/failed）+ `chunks`（`embedding vector(512)`，HNSW 索引 m=16/ef_construction=128，`ON DELETE CASCADE`）。`init.sql` 全 IF NOT EXISTS。
- **摄取链路**（`app/ingest/`）：`upload → documents.py 落盘 UPLOAD_DIR/{uuid}.pdf + INSERT processing → asyncio.create_task(pipeline)`。`pdf_parser`（PyMuPDF 主，pdfplumber 兜底，抛 ParseError）→ `chunker`（500 字符/80 重叠，逐页，纯 stdlib）→ `embedder`（fastembed bge-small-zh-v1.5，512 维）→ 批量 INSERT → status=ready/failed。
- **问答链路**（`app/api/chat.py`）：最后一条 user 消息 → `embed_query` → KNN（`ORDER BY embedding <=> %s::vector LIMIT top_k`）→ SSE：`event: citations`（index 从 1）→ 上游 delta 帧原样转发 → `data: [DONE]`。0 命中（含 top_k=0）→ `citations:[]` + "知识库中未找到相关内容。" + `[DONE]`，不调上游。
- **KNN 无相似度阈值**：任何问题都会返回 top_k 条。强制 0 命中唯一可靠方式是在请求体发 `top_k: 0`（smoke.py `--expect-unrelated` 即此用法）。不要靠"无关问题"期望 0 命中。

## 必须保持的边界（改坏会出事）

- **前端 `useRagChat.ts` 的 delta 守卫必须是 `if (delta)`**：上游是推理模型，delta 帧常只含 `reasoning_content` 而无 `content`，`extractDeltaContent` 返回 null。曾因写成 `delta !== ''` 导致回答拼出字面 "null"（已修复）。不要改回。
- **`embed_query = embed_texts([text])[0]`，不加 query 前缀**：必须与 ingest 侧编码完全对称（T7 种子 chunk 与 T6 摄取 chunk 同向量空间）。不要给 bge 加查询前缀。
- **httpx 客户端 `trust_env=False`**（chat.py 与 smoke.py 均已设）：本机有系统代理 127.0.0.1:7897，trust_env=True 会导致 LLM 调用走代理返回 502。勿去掉。
- **后台 task 必须存模块级 `set()` 并 `add_done_callback(tasks.discard)`**（documents.py 已实现）：无引用 task 会被 GC，文档永久卡 processing。新加后台任务照此模式。
- **config.py 的 env_file 与 UPLOAD_DIR 都锚定仓库根**（`Path(__file__).resolve().parents[2]`），与启动 CWD 无关。`.env` 在仓库根；真实 LLM_API_KEY 只在 `.env`（gitignored），`.env.example` 占位符**不得含 `sk-` 前缀**（否则命中代码扫描）。
- **pipelines/embedding 是 CPU 密集**：用 `asyncio.to_thread` 或批次间 `await asyncio.sleep(0)`，勿阻塞事件循环（已有实现，新增路径照做）。

## 前端约定

- 双 Tab 由 `App.tsx` antd `Tabs` 实现（无路由库）。`main.tsx` 层级固定：`StyleProvider layer → XProvider → ConfigProvider(zhCN) → AntdApp`。
- antd@6 + @ant-design/x@2.9 **原生支持 React 19，禁止装 `@ant-design/v5-patch-for-react-19`**。
- Tailwind v4 与 antd 共存靠 `index.css` 顶部的 `@layer theme, base, antd, antdx, components, utilities;` + `@import "tailwindcss";`（勿删/勿改序）。
- `src/api/client.ts` 的 `DocMeta.id` 是 **UUID 字符串**（不是 number）。字段名与后端 GET /api/documents 逐一对应（filename/chunk_count，非 name/chunks）。
- 消息历史仅前端 state（`useRagChat.ts`），无服务端会话持久化。
- 前端 `BASE_URL=http://localhost:8000` 直连（非 vite proxy），靠后端 CORS。

## 杂项

- 验证端口：后端 8000、前端 5173、Postgres 5433。起服务前 `lsof -i :PORT` 查占用；测完杀掉自己起的进程。
- 证据/日志存 `.omo/evidence/`（gitignored）。日志绝不回显 `.env` 内容或展开后的 API key。
- 提交用 conventional commits；`.env`、`backend/data/`、`node_modules/`、`.omo/` 均 gitignored，勿提交。
- `make_sample_pdf.py` 生成 3 页中文样例 PDF（含"监督学习需要标注数据"等固定句子），供 smoke/验收对齐。
- README.md 有完整启动步骤、后端目录结构与核心数据流说明——改架构时同步更新它。
