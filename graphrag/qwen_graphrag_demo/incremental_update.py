import argparse
import shutil
import subprocess
from datetime import datetime
from pathlib import Path


def run_cmd(cmd: list[str], cwd: Path) -> None:
    print(f"$ {' '.join(cmd)}")
    proc = subprocess.run(cmd, cwd=str(cwd), check=False)
    if proc.returncode != 0:
        raise SystemExit(f"命令失败（退出码 {proc.returncode}）：{' '.join(cmd)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="保留旧库并执行增量建库（基于 graphrag update）。")
    parser.add_argument(
        "--source-dir",
        required=True,
        help="新增原始数据目录（例如 ./data_increment）",
    )
    parser.add_argument(
        "--run-update",
        action="store_true",
        help="执行 graphrag update（不加此参数则只做预处理）。",
    )
    parser.add_argument(
        "--enable-ocr",
        action="store_true",
        help="预处理时开启图片 OCR。",
    )
    parser.add_argument(
        "--enable-vision",
        action="store_true",
        help="预处理时对图片调用 OpenAI 兼容多模态接口（需 VISION_API_KEY 或 GRAPHRAG_API_KEY 等）。",
    )
    parser.add_argument(
        "--vision-model",
        default="",
        help="可选；非空则传给预处理覆盖默认视觉模型（如 glm-4v-plus）。",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="执行 update 时附带 --skip-validation。",
    )
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    source_dir = Path(args.source_dir).expanduser().resolve()
    if not source_dir.exists():
        raise SystemExit(f"source-dir 不存在：{source_dir}")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    inc_input_dir = root / "input" / "normalized" / f"increment_{stamp}"
    inc_output_dir = root / f"output_increment_{stamp}"

    print(f"项目目录: {root}")
    print(f"增量输入目录: {inc_input_dir}")

    convert_cmd = [
        "python",
        "ingest/convert_to_graphrag_input.py",
        "--source-dir",
        str(source_dir),
        "--target-dir",
        str(inc_input_dir),
    ]
    if args.enable_ocr:
        convert_cmd.append("--enable-ocr")
    if args.enable_vision:
        convert_cmd.append("--enable-vision")
    if args.vision_model.strip():
        convert_cmd.extend(["--vision-model", args.vision_model.strip()])
    run_cmd(convert_cmd, cwd=root)

    if not args.run_update:
        print("仅完成预处理（未执行 graphrag update）。")
        print("下一步可手动运行：graphrag update --skip-validation")
        return

    update_cmd = ["graphrag", "update"]
    if args.skip_validation:
        update_cmd.append("--skip-validation")
    run_cmd(update_cmd, cwd=root)

    update_output = root / "update_output"
    if not update_output.exists():
        raise SystemExit("未找到 update_output，graphrag update 可能未成功产出。")

    if inc_output_dir.exists():
        shutil.rmtree(inc_output_dir)
    shutil.move(str(update_output), str(inc_output_dir))

    print("增量建库完成：")
    print(f"- 保留原库: {root / 'output'}")
    print(f"- 新增库:   {inc_output_dir}")
    print("查询新增库示例：")
    print(
        f"  graphrag query \"你的问题\" --method basic -d {inc_output_dir}"
    )


if __name__ == "__main__":
    main()
