#!/usr/bin/env python3
"""
最小化实时录音 + WeNet 转写示例。

脚本设计为单文件，可直接在 Windows 目录中运行。
你可以指定一个 WeNet 模型目录（`train.yaml`、`final.pt`、`units.txt` 等），并选择：

1. 实时采集麦克风音频，验证本机采集和转写链路。
2. 跳过录音，直接转写已有的 WAV/FLAC/AIFF 文件。

推荐将依赖安装在 `minimal_craft/.venv` 中，避免污染系统环境。
录音过程中按 Ctrl+C 即可结束并触发转写。
"""

from __future__ import annotations

import argparse
import os
import queue
import shutil
import sys
import tempfile
from pathlib import Path
from typing import List

import numpy as np
import sounddevice as sd
import soundfile as sf

import wenet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="最小化实时录音或离线音频转写（WeNet）"
    )
    default_model_dir = Path(__file__).parent / "paraformer_model"
    parser.add_argument(
        "--model-dir",
        default=str(default_model_dir),
        help=(
            "包含 WeNet 模型文件的目录（train.yaml、final.pt、units.txt）。"
            "默认使用 ./paraformer_model（若存在）。"
        ),
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="WeNet 运行设备，如 'cpu'、'cuda:0'",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="麦克风采样率（Hz）",
    )
    parser.add_argument(
        "--chunk-ms",
        type=int,
        default=250,
        help="采集分块时长（毫秒）",
    )
    parser.add_argument(
        "--channels",
        type=int,
        default=1,
        help="录音通道数",
    )
    parser.add_argument(
        "--input-device",
        type=int,
        default=None,
        help=(
            "Optional sounddevice input index. Use 'python -m sounddevice' "
            "查看设备列表后填入。"
        ),
    )
    parser.add_argument(
        "--save-wav",
        default=None,
        help="可选：保存录音到指定文件路径",
    )
    parser.add_argument(
        "--wav-path",
        default=None,
        help=(
            "直接转写已有 WAV/FLAC/AIFF 文件。"
            "提供后将跳过麦克风采集。"
        ),
    )
    parser.add_argument(
        "--silence-threshold",
        type=float,
        default=1e-3,
        help="RMS 阈值（0-1），仅用于控制台音量显示",
    )
    return parser.parse_args()


def load_recognizer(model_dir: str, device: str):
    model_path = os.path.abspath(model_dir)
    print(f"[WeNet] 正在加载模型：{model_path}，设备：{device} ...", flush=True)
    model = wenet.load_model(model_path, device=device)
    model.eval()
    print("[WeNet] 模型加载完成。")
    return model


def log_meter(chunk: np.ndarray, idx: int, chunk_ms: int, silence_threshold: float) -> None:
    rms = float(np.sqrt(np.mean(np.square(chunk))))
    status = "静音" if rms < silence_threshold else "语音"
    duration = (idx + 1) * (chunk_ms / 1000.0)
    bar = "#" * min(20, int(rms * 50))
    print(
        f"\r[采集] {duration:6.2f}s | {status} | RMS={rms:.4f} {bar:20s}",
        end="",
        flush=True,
    )


def capture_audio(args: argparse.Namespace) -> np.ndarray:
    audio_queue: queue.Queue[np.ndarray] = queue.Queue()
    collected: List[np.ndarray] = []
    blocksize = max(1, int(args.sample_rate * args.chunk_ms / 1000))

    def callback(indata, frames, time_info, status):
        if status:
            print(f"\n[采集] 警告：{status}", file=sys.stderr, flush=True)
        audio_queue.put(indata.copy())

    print("[采集] 麦克风开始录音，按 Ctrl+C 结束...")
    if args.input_device is not None:
        print(f"[采集] 使用输入设备 #{args.input_device}")
    try:
        stream = sd.InputStream(
            samplerate=args.sample_rate,
            device=args.input_device,
            channels=args.channels,
            dtype="float32",
            blocksize=blocksize,
            callback=callback,
        )
    except Exception as exc:
        raise RuntimeError(f"无法打开麦克风：{exc}") from exc

    with stream:
        chunk_index = 0
        try:
            while True:
                chunk = audio_queue.get(timeout=0.5)
                collected.append(chunk)
                log_meter(chunk, chunk_index, args.chunk_ms, args.silence_threshold)
                chunk_index += 1
        except KeyboardInterrupt:
            print("\n[采集] 已由用户停止。")
        except queue.Empty:
            print("\n[采集] 未收到音频数据，请检查麦克风权限和设备设置。")

    if not collected:
        raise RuntimeError("未采集到音频，请检查麦克风权限。")
    audio = np.concatenate(collected, axis=0)
    if audio.ndim == 2 and audio.shape[1] > 1:
        audio = np.mean(audio, axis=1, keepdims=True)
    audio = audio.squeeze(-1)
    print(f"[采集] 已录制 {audio.shape[0] / args.sample_rate:.2f} 秒。")
    return audio


def run_transcription(model, audio: np.ndarray, sample_rate: int, save_wav: str | None):
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
        sf.write(tmp_path, audio, sample_rate)
    try:
        result = model.transcribe(tmp_path)
    finally:
        if save_wav:
            sf.write(save_wav, audio, sample_rate)
            print(f"[输出] 录音已保存到：{save_wav}")
        os.unlink(tmp_path)
    text = getattr(result, "text", "")
    print(f"[结果] {text}")
    return text


def transcribe_existing(model, wav_path: str, save_wav: str | None):
    path = Path(wav_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"未找到输入音频文件：{path}")
    print(f"[转写] 使用现有音频文件：{path}")
    result = model.transcribe(str(path))
    text = getattr(result, "text", "")
    print(f"[结果] {text}")
    if save_wav:
        shutil.copyfile(path, save_wav)
        print(f"[输出] 已复制源音频到：{save_wav}")
    return text


def main():
    args = parse_args()
    model = load_recognizer(args.model_dir, args.device)
    if args.wav_path:
        transcribe_existing(model, args.wav_path, args.save_wav)
    else:
        audio = capture_audio(args)
        run_transcription(model, audio, args.sample_rate, args.save_wav)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:  # pragma: no cover - user feedback path
        print(f"[错误] {exc}", file=sys.stderr)
        sys.exit(1)
