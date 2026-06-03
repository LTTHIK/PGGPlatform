# Mixed Format Ingest for GraphRAG

This folder converts mixed file formats into GraphRAG-ready text files under `input/normalized/`.

## 1) Install dependencies

在 GraphRAG 仓库根目录（与 `qwen_graphrag_demo/` 同级）执行：

```bash
cd qwen_graphrag_demo
pip install -r ingest/requirements.txt
```

For OCR on images, also install system tesseract:

```bash
sudo apt-get update && sudo apt-get install -y tesseract-ocr tesseract-ocr-chi-sim
```

For **vision captioning** (OpenAI-compatible chat completions), set `VISION_API_KEY` or `DASHSCOPE_API_KEY` in `.env`. Defaults: DashScope `https://dashscope.aliyuncs.com/compatible-mode/v1`, model `qwen3.5-omni-plus-2026-03-15`, `temperature=0.1`, `max_tokens=32` (short captions; increase via `--vision-max-tokens` if needed). Override with `--vision-api-base` / `--vision-model` if needed.

`requirements.txt` includes `httpx`, `pyarrow`, `PyYAML`, etc., for conversion and optional tooling; GraphRAG indexing still uses your main `graphrag` conda environment.

## 2) Convert mixed files

Example source directory:

```bash
python ingest/convert_to_graphrag_input.py \
  --source-dir ./data \
  --target-dir ./input/normalized \
  --enable-ocr \
  --enable-vision
```

Remove `--enable-ocr` / `--enable-vision` if not needed. You can combine both: OCR for exact text, vision for layout/charts/scene description.

## 3) Re-index with GraphRAG

```bash
cd qwen_graphrag_demo
graphrag index
```

## Notes

- `pdf/pptx/docx` are converted by `markitdown`.
- `csv/xlsx` are flattened into row-wise text records.
- `html` is converted via visible text extraction.
- Output file format includes source metadata header and content body.
