"""Deterministically generate a 3-page Chinese sample PDF at backend/data/sample.pdf."""

from pathlib import Path

import pymupdf

PAGE_SIZE = (595, 842)  # A4 points

PAGES: list[list[str]] = [
    [
        "机器学习是人工智能的一个分支。",
        "机器学习通过数据训练模型。",
        "模型可以从数据中学习规律。",
        "机器学习广泛应用于推荐系统。",
    ],
    [
        "监督学习需要标注数据。",
        "监督学习通过标签训练模型。",
        "常见的监督学习任务包括分类和回归。",
        "监督学习在图像识别中表现出色。",
    ],
    [
        "无监督学习无需标注。",
        "无监督学习自动发现数据结构。",
        "聚类是无监督学习的典型方法。",
        "降维也属于无监督学习范畴。",
    ],
]


FIXED_DATE = "D:20260101000000Z"


def make_sample_pdf(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open()
    doc.set_metadata({
        "producer": "make_sample_pdf",
        "creationDate": FIXED_DATE,
        "modDate": FIXED_DATE,
    })
    for lines in PAGES:
        page = doc.new_page(width=PAGE_SIZE[0], height=PAGE_SIZE[1])
        rect = pymupdf.Rect(72, 72, PAGE_SIZE[0] - 72, PAGE_SIZE[1] - 72)
        page.insert_textbox(rect, "\n".join(lines), fontname="china-s", fontsize=12)
    doc.save(str(out_path), no_new_id=True)
    doc.close()


def main() -> None:
    out_path = Path(__file__).resolve().parents[1] / "data" / "sample.pdf"
    make_sample_pdf(out_path)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
