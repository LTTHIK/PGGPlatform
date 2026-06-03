#!/usr/bin/env python3
"""
Convert mixed file types into GraphRAG text inputs.

Supported by default:
- txt, md, csv, xls, xlsx, html, htm
- pdf, pptx, docx (via markitdown if available)
- images (png/jpg/jpeg/webp) with optional OCR (pytesseract + Pillow)
  and/or optional multimodal captioning（OpenAI 兼容 chat/completions；默认读 .env 中 VISION_* / LOCAL_CHAT_*，否则 DashScope）
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import os
from io import BytesIO
from pathlib import Path
from typing import Iterable

import httpx

# 演示工程根目录（ingest/ 的上一级；目录改名后仍正确）
_DEMO_ROOT = Path(__file__).resolve().parents[1]

TEXT_EXTS = {".txt", ".md"}
HTML_EXTS = {".html", ".htm"}
CSV_EXTS = {".csv"}
EXCEL_EXTS = {".xlsx", ".xls"}
MARKITDOWN_EXTS = {".pdf", ".pptx", ".docx"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}

# 默认：DashScope OpenAI 兼容多模态（与 GraphRAG 补全同一套 Key/Base）；其它网关请 CLI 覆盖。
_DEFAULT_VISION_API_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_VISION_MODEL = "qwen3.5-omni-plus-2026-03-15"
_DEFAULT_VISION_TEMPERATURE = 0.1
_DEFAULT_VISION_MAX_TOKENS = 32
# 与 max_tokens=32 对齐：要求极短输出，避免被截断；需要长描述请调大 --vision-max-tokens 并改写 prompt。
_DEFAULT_VISION_PROMPT = "用中文一句话概括图中要点，含关键实体或数字；尽量不超过30字。"

_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _load_env_file(path: Path) -> None:
    """从项目根 .env 注入未设置的环境变量（不依赖 python-dotenv）。"""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


def _safe_read_text(path: Path) -> str:
    # 尽量按常见编码读取文本，最大化兼容不同来源文件。
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return path.read_text(encoding=enc)
        except Exception:
            continue
    return path.read_text(errors="ignore")


def _convert_csv(path: Path) -> str:
    # 将 CSV 行转成 “key=value” 文本，便于后续向量化与实体关系抽取。
    rows: list[str] = []
    with path.open("r", encoding="utf-8", errors="ignore", newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=1):
            compact = "; ".join(f"{k}={v}" for k, v in row.items())
            rows.append(f"row={i} | {compact}")
    return "\n".join(rows)


def _convert_excel(path: Path) -> str:
    import pandas as pd  # lazy import

    # 每个 sheet 单独加标题，再逐行转为文本记录。
    blocks: list[str] = []
    sheets = pd.read_excel(path, sheet_name=None)
    for sheet, df in sheets.items():
        blocks.append(f"# sheet: {sheet}")
        for i, row in enumerate(df.fillna("").to_dict(orient="records"), start=1):
            compact = "; ".join(f"{k}={v}" for k, v in row.items())
            blocks.append(f"row={i} | {compact}")
    return "\n".join(blocks)


def _convert_html(path: Path) -> str:
    from bs4 import BeautifulSoup  # lazy import

    # 仅提取页面可见文本，去掉 HTML 标签结构。
    html = _safe_read_text(path)
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text("\n", strip=True)


def _convert_with_markitdown(path: Path) -> str:
    from markitdown import MarkItDown  # lazy import

    # 复用 markitdown 统一处理 office/pdf 等复杂格式。
    md = MarkItDown()
    result = md.convert(str(path))
    return getattr(result, "text_content", "") or ""


def _convert_image_with_ocr(path: Path) -> str:
    import pytesseract  # lazy import
    from PIL import Image  # lazy import

    # OCR: 默认中英双语识别。需要系统安装 tesseract 与中文语言包。
    img = Image.open(path)
    return pytesseract.image_to_string(img, lang="chi_sim+eng")


def _vision_bearer_token() -> str:
    """Authorization: Bearer … 优先 VISION_API_KEY，否则 DASHSCOPE_API_KEY，再否则 ZAI / GRAPHRAG。"""
    return (
        os.environ.get("VISION_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
        or os.environ.get("ZAI_API_KEY")
        or os.environ.get("GRAPHRAG_API_KEY")
        or ""
    ).strip()


def _image_bytes_for_vision(path: Path, max_edge: int, jpeg_quality: int) -> tuple[str, bytes]:
    """供多模态 data URL 使用：max_edge>0 时用 Pillow 等比缩小并转 JPEG，减轻上传与推理耗时。"""
    if max_edge <= 0:
        ext = path.suffix.lower()
        return _IMAGE_MIME.get(ext, "image/jpeg"), path.read_bytes()

    from PIL import Image, ImageOps  # lazy import

    img = Image.open(path)
    img = ImageOps.exif_transpose(img)
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if max(w, h) > max_edge:
        scale = max_edge / float(max(w, h))
        nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
        try:
            resample = Image.Resampling.LANCZOS
        except AttributeError:
            resample = Image.LANCZOS  # type: ignore[attr-defined]
        img = img.resize((nw, nh), resample)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=jpeg_quality, optimize=True)
    return "image/jpeg", buf.getvalue()


def _convert_image_with_vision(
    path: Path,
    *,
    model: str,
    api_base: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    timeout: float,
    max_retries: int,
    max_edge: int,
    jpeg_quality: int,
) -> str:
    from openai import OpenAI  # lazy import

    api_key = _vision_bearer_token()
    if not api_key:
        raise RuntimeError(
            "启用 --enable-vision 需要 Bearer：请设置 VISION_API_KEY 或 DASHSCOPE_API_KEY（或 ZAI_API_KEY 等）"
        )

    mime, raw = _image_bytes_for_vision(path, max_edge=max_edge, jpeg_quality=jpeg_quality)
    b64 = base64.standard_b64encode(raw).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    # 大图上传易触发 httpx 默认 write 超时；read 与网关推理也需单独放宽。
    t_read = max(timeout, 30.0)
    t_write = max(timeout, 120.0)
    t_connect = min(60.0, max(10.0, timeout / 10.0))
    timeout_cfg = httpx.Timeout(connect=t_connect, read=t_read, write=t_write, pool=60.0)
    client = OpenAI(
        api_key=api_key,
        base_url=api_base.rstrip("/"),
        timeout=timeout_cfg,
        max_retries=max_retries,
    )
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    choice = resp.choices[0].message
    text = getattr(choice, "content", None) or ""
    if isinstance(text, list):
        # 少数网关返回 content 为分段结构
        parts: list[str] = []
        for block in text:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            else:
                parts.append(str(block))
        text = "".join(parts)
    return str(text).strip()


def convert_one(
    path: Path,
    enable_ocr: bool,
    enable_vision: bool,
    vision_model: str,
    vision_api_base: str,
    vision_prompt: str,
    vision_temperature: float,
    vision_max_tokens: int,
    vision_timeout: float,
    vision_max_retries: int,
    vision_max_edge: int,
    vision_jpeg_quality: int,
) -> str:
    # 按扩展名分流到对应转换器，未支持或空内容返回空字符串。
    ext = path.suffix.lower()
    if ext in TEXT_EXTS:
        return _safe_read_text(path)
    if ext in CSV_EXTS:
        return _convert_csv(path)
    if ext in EXCEL_EXTS:
        return _convert_excel(path)
    if ext in HTML_EXTS:
        return _convert_html(path)
    if ext in MARKITDOWN_EXTS:
        return _convert_with_markitdown(path)
    if ext in IMAGE_EXTS:
        blocks: list[str] = []
        if enable_vision:
            blocks.append(
                "## 视觉模型描述\n"
                + _convert_image_with_vision(
                    path,
                    model=vision_model,
                    api_base=vision_api_base,
                    prompt=vision_prompt,
                    temperature=vision_temperature,
                    max_tokens=vision_max_tokens,
                    timeout=vision_timeout,
                    max_retries=vision_max_retries,
                    max_edge=vision_max_edge,
                    jpeg_quality=vision_jpeg_quality,
                )
            )
        if enable_ocr:
            blocks.append("## OCR 识别文本\n" + _convert_image_with_ocr(path))
        if not blocks:
            return ""
        return "\n\n".join(b.strip() for b in blocks).strip()


def build_output_text(src: Path, content: str) -> str:
    # 输出统一结构：metadata + content，方便追溯来源与后续审计。
    header = {
        "source_file": str(src),
        "filename": src.name,
        "suffix": src.suffix.lower(),
    }
    return f"---metadata---\n{json.dumps(header, ensure_ascii=False)}\n---content---\n{content.strip()}\n"


def iter_files(root: Path, patterns: Iterable[str]) -> Iterable[Path]:
    # 支持多个 glob 模式，递归扫描来源目录。
    for pattern in patterns:
        yield from root.rglob(pattern)


def _default_vision_api_base() -> str:
    """优先 .env：VISION_API_BASE → LOCAL_CHAT_API_BASE → 内置 DashScope。"""
    for key in ("VISION_API_BASE", "LOCAL_CHAT_API_BASE"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    return _DEFAULT_VISION_API_BASE


def _default_vision_model() -> str:
    """优先 .env：VISION_MODEL → LOCAL_CHAT_MODEL → 内置 DashScope 模型名。"""
    for key in ("VISION_MODEL", "LOCAL_CHAT_MODEL"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    return _DEFAULT_VISION_MODEL


def main() -> int:
    # 先加载演示根目录 .env，再解析参数，这样 vision 默认值可与 GraphRAG 本地网关一致。
    _load_env_file(_DEMO_ROOT / ".env")

    vb = _default_vision_api_base()
    vm = _default_vision_model()

    # CLI 参数：source-dir 必填；target-dir 默认写到 GraphRAG input/normalized。
    parser = argparse.ArgumentParser(description="Convert mixed files to GraphRAG input text files.")
    parser.add_argument("--source-dir", required=True, help="Directory containing source files.")
    parser.add_argument(
        "--target-dir",
        default=str(_DEMO_ROOT / "input" / "normalized"),
        help="Directory to write normalized .txt files.",
    )
    parser.add_argument(
        "--enable-ocr",
        action="store_true",
        help="Enable OCR for image files (requires pytesseract + Pillow + system tesseract).",
    )
    parser.add_argument(
        "--enable-vision",
        action="store_true",
        help="对 png/jpg/jpeg/webp 调用 OpenAI 兼容多模态 chat/completions（密钥：VISION_API_KEY 等；base/model 默认读 .env）。",
    )
    parser.add_argument(
        "--vision-model",
        default=vm,
        help=f"视觉模型名（默认：来自环境变量或 {_DEFAULT_VISION_MODEL}）。当前默认={vm!r}。",
    )
    parser.add_argument(
        "--vision-api-base",
        default=vb,
        help=(
            "OpenAI 兼容 base_url（默认：环境变量 VISION_API_BASE / LOCAL_CHAT_API_BASE，"
            f"否则 {_DEFAULT_VISION_API_BASE}）。当前默认={vb!r}。"
        ),
    )
    parser.add_argument(
        "--vision-prompt",
        default=_DEFAULT_VISION_PROMPT,
        help="发给视觉模型的中文指令。",
    )
    parser.add_argument(
        "--vision-temperature",
        type=float,
        default=_DEFAULT_VISION_TEMPERATURE,
        help=f"采样温度（默认 {_DEFAULT_VISION_TEMPERATURE}）。",
    )
    parser.add_argument(
        "--vision-max-tokens",
        type=int,
        default=_DEFAULT_VISION_MAX_TOKENS,
        help=f"最大输出 token（默认 {_DEFAULT_VISION_MAX_TOKENS}；建索引长描述请调大）。",
    )
    parser.add_argument(
        "--vision-timeout",
        type=float,
        default=300.0,
        help="视觉接口单次请求超时（秒，默认 300；大图或慢网关可调大）。",
    )
    parser.add_argument(
        "--vision-max-retries",
        type=int,
        default=3,
        help="OpenAI SDK 对可重试错误的最大重试次数（默认 3）。",
    )
    parser.add_argument(
        "--vision-max-edge",
        type=int,
        default=1536,
        help="视觉请求前图片最长边像素上限，等比缩小并转 JPEG（默认 1536；设为 0 表示不缩放、原图上传）。",
    )
    parser.add_argument(
        "--vision-jpeg-quality",
        type=int,
        default=85,
        help="缩放后 JPEG 质量 1–95（默认 85）。",
    )
    args = parser.parse_args()

    source = Path(args.source_dir).resolve()
    target = Path(args.target_dir).resolve()
    target.mkdir(parents=True, exist_ok=True)

    # 统一可处理的文件后缀；新增格式时在这里追加即可。
    patterns = ["*.txt", "*.md", "*.csv", "*.xlsx", "*.xls", "*.html", "*.htm", "*.pdf", "*.pptx", "*.docx", "*.png", "*.jpg", "*.jpeg", "*.webp"]
    files = sorted(set(iter_files(source, patterns)))

    converted = 0
    skipped = 0
    for f in files:
        try:
            content = convert_one(
                f,
                enable_ocr=args.enable_ocr,
                enable_vision=args.enable_vision,
                vision_model=args.vision_model,
                vision_api_base=args.vision_api_base,
                vision_prompt=args.vision_prompt,
                vision_temperature=args.vision_temperature,
                vision_max_tokens=args.vision_max_tokens,
                vision_timeout=args.vision_timeout,
                vision_max_retries=args.vision_max_retries,
                vision_max_edge=args.vision_max_edge,
                vision_jpeg_quality=args.vision_jpeg_quality,
            )
            if not content.strip():
                # 无内容（或未对图片开启 OCR/视觉）视为跳过，不中断全局流程。
                skipped += 1
                continue
            # 用 “文件名 + 路径哈希” 命名，避免同名文件覆盖。
            out_name = f"{f.stem}_{abs(hash(str(f))) % (10**8)}.txt"
            (target / out_name).write_text(build_output_text(f, content), encoding="utf-8")
            converted += 1
        except Exception as e:
            # 单文件失败只告警并继续，避免批处理被一个脏文件阻塞。
            skipped += 1
            print(f"[WARN] skip {f}: {e}")

    print(f"done: converted={converted}, skipped={skipped}, output={target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

