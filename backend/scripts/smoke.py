"""End-to-end smoke test against a running backend.

Usage (from backend/):
    uv run python scripts/smoke.py --pdf data/sample.pdf
    uv run python scripts/smoke.py --pdf data/sample.pdf --expect-unrelated

Flow: health check -> upload PDF -> poll until ready -> chat over SSE and
assert the frame contract (citations -> delta* -> [DONE]). With
--expect-unrelated the chat sends top_k=0 with an unrelated question and
asserts the no-hit contract (citations == [] and the not-found reply):
KNN has no similarity threshold, so top_k=0 is the only reliable way to
force zero hits.
"""

import argparse
import json
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "http://localhost:8000"
POLL_TIMEOUT_S = 300.0
POLL_INTERVAL_S = 2.0
SSE_TIMEOUT_S = 180.0

QUESTION = "这份文档的主要内容是什么？"
UNRELATED_QUESTION = "量子力学的薛定谔方程是什么？"
NOT_FOUND_REPLY = "知识库中未找到相关内容。"

# trust_env=False: the local system proxy must not intercept localhost traffic.
http = httpx.Client(timeout=30.0, trust_env=False)


class SmokeError(Exception):
    """Any assertion or protocol failure that should end the run as FAIL."""


def fail(message: str) -> SmokeError:
    return SmokeError(f"FAIL: {message}")


def check_health() -> None:
    try:
        resp = http.get("/api/health")
    except httpx.HTTPError as exc:
        raise fail(f"健康检查失败（无法连接后端）：{exc}") from exc
    if resp.status_code != 200:
        raise fail(f"健康检查失败：HTTP {resp.status_code}（期望 200）")
    if resp.json().get("status") != "ok":
        raise fail(f"健康检查失败：响应体 {resp.text!r} 不含 status=ok")
    print("[1/4] 健康检查通过 /api/health")


def upload_pdf(pdf_path: Path) -> str:
    if not pdf_path.is_file():
        raise fail(f"PDF 文件不存在：{pdf_path}")
    try:
        with pdf_path.open("rb") as f:
            resp = http.post(
                "/api/documents",
                files={"file": (pdf_path.name, f, "application/pdf")},
            )
    except httpx.HTTPError as exc:
        raise fail(f"上传失败（无法连接后端）：{exc}") from exc
    if resp.status_code != 201:
        raise fail(f"上传失败：HTTP {resp.status_code}（期望 201）：{resp.text}")
    doc_id = resp.json().get("id")
    if not doc_id:
        raise fail(f"上传响应缺少 id 字段：{resp.text}")
    print(f"[2/4] 上传成功 doc_id={doc_id}")
    return str(doc_id)


def poll_until_ready(doc_id: str) -> dict:
    deadline = time.monotonic() + POLL_TIMEOUT_S
    while time.monotonic() < deadline:
        try:
            resp = http.get(f"/api/documents/{doc_id}")
        except httpx.HTTPError as exc:
            raise fail(f"轮询失败（无法连接后端）：{exc}") from exc
        if resp.status_code != 200:
            raise fail(f"轮询失败：HTTP {resp.status_code}（期望 200）")
        doc = resp.json()
        status = doc.get("status")
        if status == "ready":
            waited = POLL_TIMEOUT_S - (deadline - time.monotonic())
            print(f"[3/4] 文档就绪 chunk_count={doc.get('chunk_count')}（耗时 {waited:.0f}s）")
            return doc
        if status == "error":
            raise fail(f"文档处理失败：{doc.get('error')}")
        time.sleep(POLL_INTERVAL_S)
    raise fail(f"轮询超时（{POLL_TIMEOUT_S:.0f}s）文档未达到 ready 状态")


def parse_sse(resp: httpx.Response) -> Iterator[tuple[str, str]]:
    """Yield (event, data) frames from a raw SSE byte stream, line by line."""
    event = ""
    data_lines: list[str] = []
    for raw_line in resp.iter_lines():
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                yield event, "\n".join(data_lines)
            event = ""
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[len("event:"):].strip()
        elif line.startswith("data:"):
            value = line[len("data:"):]
            data_lines.append(value[1:] if value.startswith(" ") else value)


def run_chat(payload: dict) -> tuple[list, str]:
    """POST /api/chat and parse the SSE stream.

    Returns (citations, answer_text). Enforces the shared frame contract:
    exactly one citations frame, stream ends with [DONE], no error frames.
    """
    try:
        with http.stream(
            "POST", "/api/chat", json=payload, timeout=SSE_TIMEOUT_S
        ) as resp:
            if resp.status_code != 200:
                raise fail(f"chat 请求失败：HTTP {resp.status_code}（期望 200）")
            citations: list | None = None
            answer_parts: list[str] = []
            done = False
            for event, data in parse_sse(resp):
                if data == "[DONE]":
                    done = True
                    break
                if event == "error":
                    raise fail(f"chat 返回 error 帧：{data}")
                if event == "citations":
                    if citations is not None:
                        raise fail("chat 返回了多个 citations 帧")
                    try:
                        citations = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise fail(f"citations 帧不是合法 JSON：{exc}") from exc
                elif event == "":
                    try:
                        frame = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    choices = frame.get("choices") or []
                    delta = choices[0].get("delta", {}).get("content") if choices else None
                    if isinstance(delta, str):
                        answer_parts.append(delta)
    except httpx.HTTPError as exc:
        raise fail(f"chat 流中断（无法连接后端）：{exc}") from exc

    if not done:
        raise fail("SSE 流未以 [DONE] 结束")
    if citations is None:
        raise fail("SSE 流缺少 citations 帧")
    return citations, "".join(answer_parts)


def run_default(doc: dict) -> None:
    citations, answer = run_chat({"messages": [{"role": "user", "content": QUESTION}]})
    if not citations:
        raise fail("期望 citations 非空，实际为空")
    if not answer:
        raise fail("期望至少 1 个 delta 帧，实际回答为空")
    print(
        f"[4/4] PASS：chunk_count={doc.get('chunk_count')}，"
        f"引用 {len(citations)} 条，回答 {len(answer)} 字，流以 [DONE] 结束"
    )
    print(f"回答摘要：{answer[:120]}{'…' if len(answer) > 120 else ''}")


def run_expect_unrelated() -> None:
    # top_k=0 是让检索零命中的唯一可靠方式：KNN 没有相似度阈值，
    # 仅靠无关问题仍可能返回 top_k 条近邻。
    citations, answer = run_chat(
        {"messages": [{"role": "user", "content": UNRELATED_QUESTION}], "top_k": 0}
    )
    if citations:
        raise fail(f"期望 citations 为空，实际 {len(citations)} 条：{citations}")
    if answer != NOT_FOUND_REPLY:
        raise fail(f"期望回复 {NOT_FOUND_REPLY!r}，实际 {answer!r}")
    print(f"[4/4] PASS（未找到）：citations=[]，回复={NOT_FOUND_REPLY}，流以 [DONE] 结束")


def main() -> None:
    parser = argparse.ArgumentParser(description="知识库 RAG 端到端冒烟测试")
    parser.add_argument("--pdf", required=True, type=Path, help="待上传的 PDF 路径")
    parser.add_argument(
        "--expect-unrelated",
        action="store_true",
        help="发送 top_k=0 与无关问题，断言 citations 为空且回复为未找到",
    )
    parser.add_argument(
        "--base-url", default=DEFAULT_BASE_URL, help=f"后端地址（默认 {DEFAULT_BASE_URL}）"
    )
    args = parser.parse_args()
    http.base_url = args.base_url

    check_health()
    doc_id = upload_pdf(args.pdf)
    doc = poll_until_ready(doc_id)
    if args.expect_unrelated:
        run_expect_unrelated()
    else:
        run_default(doc)


if __name__ == "__main__":
    try:
        main()
    except SmokeError as exc:
        print(exc)
        sys.exit(1)
