FROM docker.m.daocloud.io/library/python:3.12-slim

# 国内网络拉不到 ghcr.io，uv 从 PyPI 安装
RUN pip install --no-cache-dir uv

WORKDIR /app
COPY . .

RUN uv sync --frozen --no-dev

# 国内网络访问 huggingface.co 被阻断，fastembed 模型下载走 hf-mirror；
# Xet 存储后端（cas-server.xethub.hf.co）不经镜像且 401，需禁用回退普通 HTTPS
ENV HF_ENDPOINT=https://hf-mirror.com
ENV HF_HUB_DISABLE_XET=1

EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
