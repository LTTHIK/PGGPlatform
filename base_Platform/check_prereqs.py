#!/usr/bin/env python3
"""Windows 最小转写环境快速自检。"""
import argparse
import importlib
import sys
from pathlib import Path

import pkgutil


def configure_console_encoding():
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass


def check_python():
    major, minor = sys.version_info[:2]
    ok = (major, minor) >= (3, 8)
    return ok, f"检测到 Python {major}.{minor}（要求 >= 3.8）"


def check_virtual_env():
    if sys.prefix == sys.base_prefix:
        return False, "虚拟环境未激活，请启用 minimal_craft/.venv"
    return True, f"虚拟环境已激活：{Path(sys.prefix)}"


def check_module(name):
    if pkgutil.find_loader(name) is None:
        return False, f"缺少模块：{name}"
    try:
        importlib.import_module(name)
        return True, f"模块 '{name}' 导入成功"
    except Exception as exc:  # pragma: no cover
        return False, f"模块 '{name}' 导入失败：{exc}"


def check_audio():
    try:
        import sounddevice as sd
    except Exception as exc:
        return False, f"sounddevice 不可用：{exc}"
    try:
        devices = sd.query_devices()
    except Exception as exc:
        return False, f"无法查询音频设备：{exc}"
    inputs = [d for d in devices if d.get("max_input_channels", 0) > 0]
    if not inputs:
        return False, "未检测到可输入音频设备，请检查 Windows 麦克风权限。"
    preview = "; ".join(f"#{i} {d['name']}" for i, d in enumerate(inputs[:3]))
    extra = "" if len(inputs) <= 3 else f" (+{len(inputs)-3} more)"
    default_device = None
    default_pair = sd.default.device
    if isinstance(default_pair, (list, tuple)) and default_pair:
        default_device = default_pair[0]
    default_msg = "" if default_device is None else f" | default input index: {default_device}"
    return True, f"检测到输入设备：{preview}{extra}{default_msg}"


def check_model(model_dir: Path):
    if not model_dir:
        return False, "未提供 --model-dir，无法校验模型文件"
    resolved = model_dir.expanduser().resolve()
    required = ["train.yaml", "final.pt", "units.txt"]
    missing = [f for f in required if not (resolved / f).exists()]
    if missing:
        return False, f"模型目录缺少文件：{', '.join(missing)}"
    return True, f"模型目录检查通过：{resolved}"


def main():
    configure_console_encoding()
    parser = argparse.ArgumentParser(
        description="Inspect the minimal environment before running minimal_streaming.py"
    )
    default_model = Path(__file__).parent / "paraformer_model"
    parser.add_argument("--model-dir", type=Path, default=default_model)
    args = parser.parse_args()

    checks = []
    checks.append(check_python())
    checks.append(check_virtual_env())
    for module in ["numpy", "sounddevice", "soundfile", "torch", "torchaudio", "wenet"]:
        checks.append(check_module(module))
    checks.append(check_audio())
    checks.append(check_model(args.model_dir))

    print("Minimal Craft 环境检查报告：\n")
    failed = False
    for ok, message in checks:
        status = "[OK ]" if ok else "[FAIL]"
        print(f"{status} {message}")
        failed |= not ok

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
