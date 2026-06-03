#!/usr/bin/env python3
"""Realtime transcription + meeting content processing GUI."""

from __future__ import annotations

import argparse
import json
import os
import queue
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import boto3
import numpy as np
import requests
import sounddevice as sd
import soundfile as sf
import torch
import tkinter as tk
from botocore.exceptions import ClientError
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import wenet


def load_env_file(env_path: Path) -> None:
    if not env_path.exists():
        return
    try:
        content = env_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        content = env_path.read_text(encoding="utf-16")
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def env_flag(name: str, default: bool = True) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class EngineConfig:
    model_dir: str
    device: str
    sample_rate: int = 16000
    block_ms: int = 100
    channels: int = 1
    voice_threshold: float = 0.001
    silence_ms: int = 800
    min_utter_ms: int = 300
    emit_ms: int = 700
    max_utter_s: float = 8.0


class DeepSeekClient:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: int = 120,
        verify_ssl: bool = True,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self.verify_ssl = verify_ssl

    def chat(self, system_prompt: str, user_prompt: str, messages: Optional[list[dict]] = None) -> str:
        if not self.api_key.strip():
            raise ValueError("DeepSeek API 瀵嗛挜涓虹┖")
        endpoint = f"{self.base_url}/chat/completions"
        req_messages = (
            messages
            if messages is not None
            else [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ]
        )
        payload = {"model": self.model, "temperature": 0.2, "messages": req_messages}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        resp = requests.post(
            endpoint,
            data=json.dumps(payload),
            headers=headers,
            timeout=self.timeout_s,
            verify=self.verify_ssl,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"DeepSeek 鎺ュ彛鎶ラ敊 {resp.status_code}: {resp.text[:240]}")
        body = resp.json()
        choices = body.get("choices") or []
        if not choices:
            raise RuntimeError("DeepSeek 杩斿洖缁撴灉涓虹┖锛坈hoices锛?)
        content = (choices[0].get("message") or {}).get("content")
        if not content:
            raise RuntimeError("DeepSeek 杩斿洖鍐呭涓虹┖锛坈ontent锛?)
        return str(content).strip()


class MinioClient:
    def __init__(self, endpoint: str, access_key: str, secret_key: str):
        self.s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
        )

    def ensure_bucket(self, bucket: str) -> None:
        try:
            self.s3.head_bucket(Bucket=bucket)
            return
        except ClientError:
            pass
        self.s3.create_bucket(Bucket=bucket)

    def list_buckets(self) -> list[str]:
        body = self.s3.list_buckets()
        return [b.get("Name", "") for b in body.get("Buckets", []) if b.get("Name")]

    def list_objects(self, bucket: str) -> list[str]:
        keys: list[str] = []
        continuation = None
        while True:
            kwargs = {"Bucket": bucket, "MaxKeys": 1000}
            if continuation:
                kwargs["ContinuationToken"] = continuation
            resp = self.s3.list_objects_v2(**kwargs)
            for item in resp.get("Contents", []):
                key = item.get("Key")
                if key:
                    keys.append(key)
            if not resp.get("IsTruncated"):
                break
            continuation = resp.get("NextContinuationToken")
        return keys

    def get_object_bytes(self, bucket: str, key: str) -> bytes:
        resp = self.s3.get_object(Bucket=bucket, Key=key)
        return resp["Body"].read()

    def upload_file(self, bucket: str, key: str, path: str, content_type: str) -> None:
        self.s3.upload_file(
            Filename=path,
            Bucket=bucket,
            Key=key,
            ExtraArgs={"ContentType": content_type},
        )

    def upload_bytes(self, bucket: str, key: str, data: bytes, content_type: str) -> None:
        self.s3.put_object(Bucket=bucket, Key=key, Body=data, ContentType=content_type)


class RealtimeAsrEngine:
    def __init__(self, cfg: EngineConfig):
        self.cfg = cfg
        self.model = None
        self.stream: Optional[sd.InputStream] = None
        self.running = False
        self.audio_queue: queue.Queue[np.ndarray] = queue.Queue()
        self.result_queue: queue.Queue[str] = queue.Queue()
        self.status_queue: queue.Queue[str] = queue.Queue()
        self.level_queue: queue.Queue[float] = queue.Queue()
        self.session_chunks: list[np.ndarray] = []
        self.last_recording_path: Optional[str] = None
        self._worker: Optional[threading.Thread] = None

    def _set_status(self, text: str) -> None:
        self.status_queue.put(text)

    def _load_model(self) -> None:
        model_path = os.path.abspath(self.cfg.model_dir)
        self._set_status(f"姝ｅ湪鍔犺浇妯″瀷锛歿model_path}")
        if self.cfg.device.startswith("cuda") and not torch.cuda.is_available():
            self._set_status("CUDA 涓嶅彲鐢紝宸插洖閫€鍒?CPU")
            self.cfg.device = "cpu"
        self.model = wenet.load_model(model_path, device=self.cfg.device)
        self.model.eval()
        self._set_status(f"妯″瀷鍔犺浇瀹屾垚锛坽self.cfg.device}锛?)

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            self.status_queue.put(f"闊抽璀﹀憡锛歿status}")
        chunk = indata.copy()
        if chunk.ndim == 2 and chunk.shape[1] > 1:
            chunk = np.mean(chunk, axis=1, keepdims=True)
        mono = chunk.squeeze(-1)
        rms = float(np.sqrt(np.mean(np.square(mono))))
        self.level_queue.put(rms)
        self.audio_queue.put(mono)
        self.session_chunks.append(mono)

    def start(self) -> None:
        if self.running:
            return
        if self.model is None:
            self._load_model()
        self.running = True
        self.session_chunks = []
        self.last_recording_path = None
        blocksize = max(1, int(self.cfg.sample_rate * self.cfg.block_ms / 1000))
        self.stream = sd.InputStream(
            samplerate=self.cfg.sample_rate,
            channels=self.cfg.channels,
            dtype="float32",
            blocksize=blocksize,
            callback=self._audio_callback,
        )
        self.stream.start()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        self._set_status("姝ｅ湪鐩戝惉")

    def stop(self) -> None:
        if not self.running:
            return
        self.running = False
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            finally:
                self.stream = None
        if self._worker is not None:
            self._worker.join(timeout=2.0)
            self._worker = None
        self._save_full_recording()
        self._set_status("宸插仠姝?)

    def _save_full_recording(self) -> None:
        if not self.session_chunks:
            return
        audio = np.concatenate(self.session_chunks, axis=0)
        if audio.size == 0:
            return
        out_dir = Path(__file__).parent / "recordings"
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"recording_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}.wav"
        out_path = out_dir / filename
        sf.write(str(out_path), audio, self.cfg.sample_rate)
        self.last_recording_path = str(out_path)
        self._set_status(f"褰曢煶宸蹭繚瀛橈細{out_path}")

    def _worker_loop(self) -> None:
        assert self.model is not None
        silence_samples_target = int(self.cfg.sample_rate * self.cfg.silence_ms / 1000)
        min_samples = int(self.cfg.sample_rate * self.cfg.min_utter_ms / 1000)
        emit_samples_target = int(self.cfg.sample_rate * self.cfg.emit_ms / 1000)
        max_samples = int(self.cfg.sample_rate * self.cfg.max_utter_s)
        utter_chunks = []
        spoken_samples = 0
        trailing_silence_samples = 0

        while self.running:
            try:
                chunk = self.audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            rms = float(np.sqrt(np.mean(np.square(chunk))))
            voiced = rms >= self.cfg.voice_threshold or (
                bool(utter_chunks) and rms >= self.cfg.voice_threshold * 0.5
            )
            if voiced:
                utter_chunks.append(chunk)
                spoken_samples += len(chunk)
                trailing_silence_samples = 0
            elif utter_chunks:
                utter_chunks.append(chunk)
                trailing_silence_samples += len(chunk)
            should_flush = False
            if utter_chunks and trailing_silence_samples >= silence_samples_target:
                should_flush = True
            if spoken_samples >= emit_samples_target:
                should_flush = True
            if spoken_samples >= max_samples:
                should_flush = True
            if should_flush:
                self._transcribe_utterance(utter_chunks, spoken_samples, min_samples)
                utter_chunks = []
                spoken_samples = 0
                trailing_silence_samples = 0
        if utter_chunks:
            self._transcribe_utterance(utter_chunks, spoken_samples, min_samples)

    def _transcribe_utterance(self, chunks, spoken_samples: int, min_samples: int) -> None:
        if spoken_samples < min_samples:
            return
        audio = np.concatenate(chunks, axis=0)
        wav_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                wav_path = tmp.name
            sf.write(wav_path, audio, self.cfg.sample_rate)
            result = self.model.transcribe(wav_path)
            text = getattr(result, "text", "").strip()
            if text:
                self.result_queue.put(text)
        except Exception as exc:
            self.status_queue.put(f"杞啓澶辫触锛歿exc}")
        finally:
            if wav_path:
                try:
                    os.unlink(wav_path)
                except Exception:
                    pass


class RealtimeAsrGui:
    def __init__(self, root: tk.Tk, default_model_dir: str):
        self.root = root
        self.root.title("瀹炴椂璇煶杞啓 + DeepSeek 鏁寸悊")
        self.root.geometry("1500x920")

        self.engine: Optional[RealtimeAsrEngine] = None
        self.engine_thread: Optional[threading.Thread] = None

        self.model_var = tk.StringVar(value=default_model_dir)
        default_device = "cuda:0" if torch.cuda.is_available() else "cpu"
        self.device_var = tk.StringVar(value=default_device)
        self.threshold_var = tk.StringVar(value="0.001")
        self.silence_var = tk.StringVar(value="800")

        self.deepseek_url_var = tk.StringVar(value=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"))
        self.deepseek_key_var = tk.StringVar(value=os.getenv("DEEPSEEK_API_KEY", ""))
        self.deepseek_model_var = tk.StringVar(value=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"))
        self.deepseek_verify_ssl_var = tk.BooleanVar(value=env_flag("DEEPSEEK_VERIFY_SSL", True))
        self.bucket_var = tk.StringVar(value="鏈垱寤?)

        self.auto_polish_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="绌洪棽")
        self.level_var = tk.StringVar(value="闊抽噺 RMS: 0.0000")
        self.cuda_var = tk.StringVar(value=f"CUDA: {'鍙敤' if torch.cuda.is_available() else '涓嶅彲鐢?}")

        self.ai_queue: queue.Queue[tuple[str, str]] = queue.Queue()
        self.minio_client: Optional[MinioClient] = None
        self.current_bucket: Optional[str] = None
        self.object_map: dict[str, tuple[str, str]] = {}
        self.current_file_text = ""
        self.current_file_desc = ""
        self.chat_current_messages: list[dict] = []
        self.chat_history_records: list[str] = []
        self._last_level_update_ts = 0.0
        self._last_level_value: Optional[float] = None

        self._build_ui()
        self._poll_queues()

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root)
        top.pack(fill=tk.BOTH, expand=True)
        self.notebook = ttk.Notebook(top)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        self.tab_record = ttk.Frame(self.notebook)
        self.tab_process = ttk.Frame(self.notebook)
        self.notebook.add(self.tab_record, text="褰曢煶涓庝笂浼?)
        self.notebook.add(self.tab_process, text="浼氳鍐呭浜屾鍔犲伐")
        self._build_record_tab(self.tab_record)
        self._build_process_tab(self.tab_process)

    def _build_record_tab(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)
        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X)

        ttk.Label(controls, text="妯″瀷鐩綍").grid(row=0, column=0, sticky=tk.W)
        ttk.Entry(controls, textvariable=self.model_var, width=62).grid(
            row=0, column=1, columnspan=3, sticky=tk.EW, padx=6
        )
        ttk.Label(controls, text="杩愯璁惧").grid(row=0, column=4, sticky=tk.W)
        ttk.Entry(controls, textvariable=self.device_var, width=12).grid(
            row=0, column=5, sticky=tk.W, padx=6
        )

        ttk.Label(controls, text="璇煶闃堝€?RMS").grid(row=1, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.threshold_var, width=12).grid(
            row=1, column=1, sticky=tk.W, padx=6, pady=(8, 0)
        )
        ttk.Label(controls, text="闈欓煶鍒ゅ仠姣").grid(row=1, column=2, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.silence_var, width=12).grid(
            row=1, column=3, sticky=tk.W, padx=6, pady=(8, 0)
        )

        ttk.Label(controls, text="DeepSeek 鍦板潃").grid(row=2, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.deepseek_url_var, width=40).grid(
            row=2, column=1, columnspan=2, sticky=tk.EW, padx=6, pady=(8, 0)
        )
        ttk.Label(controls, text="澶фā鍨嬪悕绉?).grid(row=2, column=3, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.deepseek_model_var, width=18).grid(
            row=2, column=4, sticky=tk.W, padx=6, pady=(8, 0)
        )

        ttk.Label(controls, text="API 瀵嗛挜").grid(row=3, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.deepseek_key_var, width=70, show="*").grid(
            row=3, column=1, columnspan=5, sticky=tk.EW, padx=6, pady=(8, 0)
        )
        ttk.Checkbutton(
            controls,
            text="楠岃瘉 SSL 璇佷功",
            variable=self.deepseek_verify_ssl_var,
        ).grid(row=4, column=4, columnspan=2, sticky=tk.W, pady=(8, 0))
        ttk.Label(controls, text="褰撳墠 MinIO 妗?).grid(row=4, column=0, sticky=tk.W, pady=(8, 0))
        ttk.Entry(controls, textvariable=self.bucket_var, width=40, state="readonly").grid(
            row=4, column=1, columnspan=2, sticky=tk.EW, padx=6, pady=(8, 0)
        )

        controls.columnconfigure(1, weight=1)
        controls.columnconfigure(2, weight=1)

        button_row = ttk.Frame(frame)
        button_row.pack(fill=tk.X, pady=(10, 8))
        self.start_btn = ttk.Button(button_row, text="寮€濮嬪綍闊?, command=self.start)
        self.start_btn.pack(side=tk.LEFT)
        self.stop_btn = ttk.Button(button_row, text="鍋滄褰曢煶", command=self.stop, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.polish_btn = ttk.Button(button_row, text="鍙ｈ绋?-> 涔﹂潰绋?, command=self.run_polish)
        self.polish_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.minutes_btn = ttk.Button(button_row, text="涔﹂潰绋?-> 浼氳绾", command=self.run_minutes)
        self.minutes_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.upload_audio_btn = ttk.Button(button_row, text="涓婁紶褰曢煶", command=self.upload_recording)
        self.upload_audio_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.upload_raw_btn = ttk.Button(button_row, text="涓婁紶鍙ｆ按绋?, command=self.upload_raw)
        self.upload_raw_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.upload_formal_btn = ttk.Button(button_row, text="涓婁紶涔﹂潰绋?, command=self.upload_formal)
        self.upload_formal_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.upload_minutes_btn = ttk.Button(button_row, text="涓婁紶浼氳绾", command=self.upload_minutes)
        self.upload_minutes_btn.pack(side=tk.LEFT, padx=(8, 0))
        self.upload_all_btn = ttk.Button(button_row, text="涓€閿笂浼犲洓椤?, command=self.upload_all)
        self.upload_all_btn.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(button_row, text="娓呯┖鍏ㄩ儴", command=self.clear_all).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(button_row, text="鍋滄鍚庤嚜鍔ㄦ暣鐞嗕功闈㈢", variable=self.auto_polish_var).pack(
            side=tk.LEFT, padx=(12, 0)
        )
        ttk.Label(button_row, textvariable=self.status_var).pack(side=tk.RIGHT)
        ttk.Label(button_row, textvariable=self.level_var).pack(side=tk.RIGHT, padx=(0, 12))
        ttk.Label(button_row, textvariable=self.cuda_var).pack(side=tk.RIGHT, padx=(0, 12))

        panes = ttk.Panedwindow(frame, orient=tk.VERTICAL)
        panes.pack(fill=tk.BOTH, expand=True)
        raw_wrap = ttk.Labelframe(panes, text="1锛夊疄鏃跺師濮嬭浆鍐欙紙鍙ｈ绋匡級")
        self.raw_text = ScrolledText(raw_wrap, wrap=tk.WORD, font=("Consolas", 11))
        self.raw_text.pack(fill=tk.BOTH, expand=True)
        panes.add(raw_wrap, weight=1)

        formal_wrap = ttk.Labelframe(panes, text="2锛変功闈㈡暣鐞嗙锛堝ぇ妯″瀷鐢熸垚锛?)
        self.formal_text = ScrolledText(formal_wrap, wrap=tk.WORD, font=("Consolas", 11))
        self.formal_text.pack(fill=tk.BOTH, expand=True)
        panes.add(formal_wrap, weight=1)

        minutes_wrap = ttk.Labelframe(panes, text="3锛変細璁邯瑕侊紙澶фā鍨嬬敓鎴愶級")
        self.minutes_text = ScrolledText(minutes_wrap, wrap=tk.WORD, font=("Consolas", 11))
        self.minutes_text.pack(fill=tk.BOTH, expand=True)
        panes.add(minutes_wrap, weight=1)

    def _build_process_tab(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent, padding=8)
        frame.pack(fill=tk.BOTH, expand=True)
        top_bar = ttk.Frame(frame)
        top_bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(top_bar, text="鍒锋柊 MinIO 鏍?, command=self.refresh_minio_tree).pack(side=tk.LEFT)
        ttk.Label(top_bar, text="鐐瑰嚮宸︿晶鏂囦欢鍚庯紝涓棿鏄剧ず鍐呭锛屽彸渚у彲瀵硅瘽鍔犲伐").pack(side=tk.LEFT, padx=(12, 0))

        body = ttk.Panedwindow(frame, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        left_wrap = ttk.Labelframe(body, text="MinIO 鏂囦欢鏍?)
        left_inner = ttk.Frame(left_wrap)
        left_inner.pack(fill=tk.BOTH, expand=True)
        self.tree = ttk.Treeview(left_inner, show="tree")
        tree_scroll = ttk.Scrollbar(left_inner, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        body.add(left_wrap, weight=1)

        mid_wrap = ttk.Labelframe(body, text="鏂囦欢娴忚")
        mid_inner = ttk.Frame(mid_wrap)
        mid_inner.pack(fill=tk.BOTH, expand=True)
        self.file_info_var = tk.StringVar(value="鏈€夋嫨鏂囦欢")
        ttk.Label(mid_inner, textvariable=self.file_info_var).pack(anchor=tk.W, padx=6, pady=(4, 2))
        self.file_view = ScrolledText(mid_inner, wrap=tk.WORD, font=("Consolas", 11))
        self.file_view.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        body.add(mid_wrap, weight=2)

        right_wrap = ttk.Labelframe(body, text="瀵硅瘽绐楀彛")
        right_inner = ttk.Frame(right_wrap)
        right_inner.pack(fill=tk.BOTH, expand=True)
        self.chat_tabs = ttk.Notebook(right_inner)
        self.chat_tabs.pack(fill=tk.BOTH, expand=True)
        current_tab = ttk.Frame(self.chat_tabs)
        history_tab = ttk.Frame(self.chat_tabs)
        self.chat_tabs.add(current_tab, text="姝ｅ湪杩涜鐨勪細璇?)
        self.chat_tabs.add(history_tab, text="鍘嗗彶浼氳瘽")

        self.chat_current_view = ScrolledText(current_tab, wrap=tk.WORD, font=("Consolas", 11))
        self.chat_current_view.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        input_row = ttk.Frame(current_tab)
        input_row.pack(fill=tk.X, padx=4, pady=(0, 4))
        self.chat_input = tk.Text(input_row, height=4)
        self.chat_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        btn_col = ttk.Frame(input_row)
        btn_col.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(btn_col, text="鍙戦€?, command=self.send_chat).pack(fill=tk.X)
        ttk.Button(btn_col, text="褰掓。浼氳瘽", command=self.archive_chat_session).pack(fill=tk.X, pady=(6, 0))
        ttk.Button(btn_col, text="娓呯┖褰撳墠", command=self.clear_current_chat).pack(fill=tk.X, pady=(6, 0))

        self.chat_history_view = ScrolledText(history_tab, wrap=tk.WORD, font=("Consolas", 11))
        self.chat_history_view.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)
        body.add(right_wrap, weight=2)

    def _build_config(self) -> EngineConfig:
        model_dir = self.model_var.get().strip()
        if not model_dir:
            raise ValueError("妯″瀷鐩綍涓嶈兘涓虹┖")
        if not Path(model_dir).exists():
            raise ValueError(f"妯″瀷鐩綍涓嶅瓨鍦細{model_dir}")
        return EngineConfig(
            model_dir=model_dir,
            device=self.device_var.get().strip() or "cpu",
            voice_threshold=float(self.threshold_var.get()),
            silence_ms=int(self.silence_var.get()),
        )

    def _build_llm_client(self) -> DeepSeekClient:
        return DeepSeekClient(
            base_url=self.deepseek_url_var.get().strip() or "https://api.deepseek.com/v1",
            api_key=self.deepseek_key_var.get().strip(),
            model=self.deepseek_model_var.get().strip() or "deepseek-chat",
            verify_ssl=self.deepseek_verify_ssl_var.get(),
        )

    def _build_minio_client(self) -> MinioClient:
        if self.minio_client is None:
            self.minio_client = MinioClient(
                endpoint="http://111.228.12.207:9000",
                access_key="minioadmin",
                secret_key="Minio@123456",
            )
        return self.minio_client

    def _ensure_bucket(self) -> str:
        if self.current_bucket:
            return self.current_bucket
        client = self._build_minio_client()
        base = time.strftime("asr-%Y%m%d-%H%M%S")
        bucket = base
        for _ in range(5):
            try:
                client.ensure_bucket(bucket)
                self.current_bucket = bucket
                self.bucket_var.set(bucket)
                return bucket
            except Exception:
                bucket = f"{base}-{uuid.uuid4().hex[:4]}"
        raise RuntimeError("鍒涘缓 MinIO 妗跺け璐ワ紝璇风◢鍚庨噸璇?)

    @staticmethod
    def _new_object_key(prefix: str, ext: str) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        return f"{prefix}/{ts}_{uuid.uuid4().hex[:8]}.{ext}"

    def start(self) -> None:
        try:
            cfg = self._build_config()
        except Exception as exc:
            messagebox.showerror("閰嶇疆閿欒", str(exc))
            return
        self.start_btn.configure(state=tk.DISABLED)
        self.stop_btn.configure(state=tk.NORMAL)
        self.status_var.set("姝ｅ湪鍚姩")
        self.engine = RealtimeAsrEngine(cfg)

        def _run_start():
            try:
                assert self.engine is not None
                self.engine.start()
            except Exception as exc:
                if self.engine is not None:
                    self.engine.status_queue.put(f"鍚姩澶辫触锛歿exc}")
                self.root.after(0, self._reset_buttons)

        self.engine_thread = threading.Thread(target=_run_start, daemon=True)
        self.engine_thread.start()

    def stop(self) -> None:
        if self.engine is not None:
            self.engine.stop()
        self._reset_buttons()
        if self.auto_polish_var.get():
            self.run_polish()

    def _reset_buttons(self) -> None:
        self.start_btn.configure(state=tk.NORMAL)
        self.stop_btn.configure(state=tk.DISABLED)

    def clear_all(self) -> None:
        self.raw_text.delete("1.0", tk.END)
        self.formal_text.delete("1.0", tk.END)
        self.minutes_text.delete("1.0", tk.END)

    def _run_ai_task(self, task_name: str, text_input: str) -> None:
        try:
            client = self._build_llm_client()
        except Exception as exc:
            self.ai_queue.put(("error", f"瀹㈡埛绔厤缃敊璇細{exc}"))
            return
        if task_name == "polish":
            system_prompt = (
                "浣犳槸涓枃缂栬緫涓撳銆傝鎶婂彛璇浆鍐欑鏁寸悊鎴愬繝瀹炲師鏂囩殑涔﹂潰涓枃銆?
                "鍘绘帀璇皵璇嶅拰閲嶅鍙ｅご绂咃紙濡傚晩銆佸棷銆佽繖涓級锛屼繚鎸佷簨瀹炪€佹暟瀛椼€佷汉鍚嶃€佹椂闂淬€佸喅绛栦笉鍙橈紝"
                "涓嶅厑璁告柊澧炰簨瀹炪€?
            )
            user_prompt = f"璇峰皢浠ヤ笅鍙ｈ绋挎暣鐞嗕负閫氶『銆佹寮忋€佸繝瀹炲師鏂囩殑涔﹂潰鍐呭锛歕n\n{text_input}"
            target = "formal"
            done_status = "涔﹂潰绋垮凡鐢熸垚"
        else:
            system_prompt = (
                "浣犳槸楂樼骇浼氳绉樹功銆傝鍩轰簬杈撳叆鏂囨湰鐢熸垚缁撴瀯鍖栦腑鏂囦細璁邯瑕併€?
                "蹇呴』鍖呭惈锛氫細璁劍鐐逛笌璁ㄨ瑕佺偣銆佺粨璁轰笌鍐崇瓥銆佸緟鎵ц浜嬮」锛堣礋璐ｄ汉涓庢埅姝㈡椂闂达紝鑻ュ師鏂囨湁锛夈€?
                "閬楃暀闂涓庨闄╂彁绀恒€傚唴瀹硅蹇犲疄銆佸叿浣撱€佸彲鎵ц銆?
            )
            user_prompt = f"璇锋牴鎹互涓嬩功闈㈢鐢熸垚浼氳绾锛歕n\n{text_input}"
            target = "minutes"
            done_status = "浼氳绾宸茬敓鎴?
        try:
            output = client.chat(system_prompt, user_prompt)
            self.ai_queue.put((target, output))
            self.ai_queue.put(("status", done_status))
        except Exception as exc:
            self.ai_queue.put(("error", str(exc)))

    def run_polish(self) -> None:
        raw = self.raw_text.get("1.0", tk.END).strip()
        if not raw:
            messagebox.showwarning("娌℃湁鍘熷杞啓", "鍘熷杞啓鍐呭涓虹┖")
            return
        self.status_var.set("姝ｅ湪璋冪敤 DeepSeek 鐢熸垚涔﹂潰绋?)
        threading.Thread(target=self._run_ai_task, args=("polish", raw), daemon=True).start()

    def run_minutes(self) -> None:
        formal = self.formal_text.get("1.0", tk.END).strip()
        if not formal:
            messagebox.showwarning("娌℃湁涔﹂潰绋?, "涔﹂潰绋垮唴瀹逛负绌?)
            return
        self.status_var.set("姝ｅ湪璋冪敤 DeepSeek 鐢熸垚浼氳绾")
        threading.Thread(target=self._run_ai_task, args=("minutes", formal), daemon=True).start()

    def _upload_task(self, upload_type: str) -> None:
        try:
            bucket = self._ensure_bucket()
            client = self._build_minio_client()
        except Exception as exc:
            self.ai_queue.put(("error", f"MinIO 鍒濆鍖栧け璐ワ細{exc}"))
            return
        try:
            if upload_type == "recording":
                if self.engine is None or not self.engine.last_recording_path:
                    raise ValueError("褰撳墠娌℃湁鍙笂浼犵殑褰曢煶鏂囦欢锛岃鍏堝綍闊冲苟鍋滄")
                key = self._new_object_key("recordings", "wav")
                client.upload_file(bucket, key, self.engine.last_recording_path, "audio/wav")
                self.ai_queue.put(("status", f"褰曢煶涓婁紶鎴愬姛锛歿bucket}/{key}"))
                return
            if upload_type == "raw":
                content = self.raw_text.get("1.0", tk.END).strip()
                prefix = "raw_transcript"
            elif upload_type == "formal":
                content = self.formal_text.get("1.0", tk.END).strip()
                prefix = "formal_text"
            else:
                content = self.minutes_text.get("1.0", tk.END).strip()
                prefix = "meeting_minutes"
            if not content:
                raise ValueError("鍐呭涓虹┖锛屾棤娉曚笂浼?)
            key = self._new_object_key(prefix, "txt")
            client.upload_bytes(bucket, key, content.encode("utf-8"), "text/plain; charset=utf-8")
            self.ai_queue.put(("status", f"鏂囨湰涓婁紶鎴愬姛锛歿bucket}/{key}"))
        except Exception as exc:
            self.ai_queue.put(("error", f"涓婁紶澶辫触锛歿exc}"))

    def upload_recording(self) -> None:
        self.status_var.set("姝ｅ湪涓婁紶褰曢煶鍒?MinIO")
        threading.Thread(target=self._upload_task, args=("recording",), daemon=True).start()

    def upload_raw(self) -> None:
        self.status_var.set("姝ｅ湪涓婁紶鍙ｆ按绋垮埌 MinIO")
        threading.Thread(target=self._upload_task, args=("raw",), daemon=True).start()

    def upload_formal(self) -> None:
        self.status_var.set("姝ｅ湪涓婁紶涔﹂潰绋垮埌 MinIO")
        threading.Thread(target=self._upload_task, args=("formal",), daemon=True).start()

    def upload_minutes(self) -> None:
        self.status_var.set("姝ｅ湪涓婁紶浼氳绾鍒?MinIO")
        threading.Thread(target=self._upload_task, args=("minutes",), daemon=True).start()

    def _upload_all_task(self) -> None:
        for item in ("recording", "raw", "formal", "minutes"):
            self._upload_task(item)
            time.sleep(0.05)
        self.ai_queue.put(("status", "鍥涢」鍐呭涓婁紶娴佺▼鎵ц瀹屾垚"))

    def upload_all(self) -> None:
        self.status_var.set("姝ｅ湪涓€閿笂浼犲洓椤瑰唴瀹瑰埌 MinIO")
        threading.Thread(target=self._upload_all_task, daemon=True).start()

    def refresh_minio_tree(self) -> None:
        def _task():
            try:
                buckets = self._build_minio_client().list_buckets()
                self.ai_queue.put(("tree", json.dumps({"buckets": buckets}, ensure_ascii=False)))
            except Exception as exc:
                self.ai_queue.put(("error", f"鍒锋柊 MinIO 鏍戝け璐ワ細{exc}"))
        threading.Thread(target=_task, daemon=True).start()

    def _fill_tree(self, buckets: list[str]) -> None:
        self.tree.delete(*self.tree.get_children())
        self.object_map.clear()
        client = self._build_minio_client()
        for bucket in buckets:
            bucket_node = self.tree.insert("", tk.END, text=bucket, open=False)
            try:
                keys = client.list_objects(bucket)
            except Exception:
                continue
            path_nodes: dict[str, str] = {"": bucket_node}
            for key in keys:
                parts = [p for p in key.split("/") if p]
                cur_path = ""
                parent_node = bucket_node
                for i, part in enumerate(parts):
                    cur_path = f"{cur_path}/{part}" if cur_path else part
                    map_key = f"{bucket}:{cur_path}"
                    if map_key not in path_nodes:
                        path_nodes[map_key] = self.tree.insert(parent_node, tk.END, text=part, open=False)
                    parent_node = path_nodes[map_key]
                    if i == len(parts) - 1:
                        self.object_map[parent_node] = (bucket, key)

    def on_tree_select(self, _event) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        item_id = selected[0]
        meta = self.object_map.get(item_id)
        if not meta:
            return
        bucket, key = meta
        def _task():
            try:
                data = self._build_minio_client().get_object_bytes(bucket, key)
                preview = self._decode_preview(data, key)
                self.ai_queue.put(("file", json.dumps({"bucket": bucket, "key": key, "preview": preview}, ensure_ascii=False)))
            except Exception as exc:
                self.ai_queue.put(("error", f"璇诲彇瀵硅薄澶辫触锛歿exc}"))
        threading.Thread(target=_task, daemon=True).start()

    @staticmethod
    def _decode_preview(data: bytes, key: str) -> str:
        lower_key = key.lower()
        if lower_key.endswith((".txt", ".md", ".json", ".csv", ".log")):
            for enc in ("utf-8", "gbk", "utf-16"):
                try:
                    return data.decode(enc)
                except Exception:
                    continue
            return data.decode("utf-8", errors="replace")
        if lower_key.endswith((".wav", ".mp3", ".flac", ".m4a")):
            return f"闊抽鏂囦欢锛歿key}\n澶у皬锛歿len(data)} 瀛楄妭\n锛堝綋鍓嶇晫闈粎灞曠ず鏂囨湰锛屼笉鎾斁闊抽锛?
        if lower_key.endswith((".png", ".jpg", ".jpeg", ".gif", ".bmp")):
            return f"鍥剧墖鏂囦欢锛歿key}\n澶у皬锛歿len(data)} 瀛楄妭\n锛堝綋鍓嶇晫闈粎灞曠ず鏂囨湰锛屼笉娓叉煋鍥剧墖锛?
        snippet = data[:2000]
        return f"浜岃繘鍒舵枃浠讹細{key}\n澶у皬锛歿len(data)} 瀛楄妭\n鍓?2000 瀛楄妭棰勮锛歕n{snippet!r}"

    def send_chat(self) -> None:
        user_text = self.chat_input.get("1.0", tk.END).strip()
        if not user_text:
            return
        self.chat_input.delete("1.0", tk.END)
        self._append_chat_current("鐢ㄦ埛", user_text)
        if not self.chat_current_messages:
            self.chat_current_messages.append(
                {"role": "system", "content": "浣犳槸浼氳鍐呭鍔犲伐鍔╂墜銆傝鍩轰簬鐢ㄦ埛闂涓庡凡閫夋枃浠跺唴瀹硅繘琛屽洖绛旓紝杈撳嚭灏介噺缁撴瀯鍖栥€佸彲鎵ц銆?}
            )
        context_text = ""
        if self.current_file_text:
            context_text = f"\n\n銆愬綋鍓嶉€変腑鏂囦欢銆慭n{self.current_file_desc}\n銆愭枃浠跺唴瀹广€慭n{self.current_file_text[:12000]}"
        self.chat_current_messages.append({"role": "user", "content": user_text + context_text})
        def _task():
            try:
                answer = self._build_llm_client().chat("", "", messages=self.chat_current_messages)
                self.chat_current_messages.append({"role": "assistant", "content": answer})
                self.ai_queue.put(("chat_reply", answer))
            except Exception as exc:
                self.ai_queue.put(("error", f"浼氳瘽澶辫触锛歿exc}"))
        threading.Thread(target=_task, daemon=True).start()

    def _append_chat_current(self, role: str, text: str) -> None:
        ts = time.strftime("%H:%M:%S")
        self.chat_current_view.insert(tk.END, f"[{ts}] {role}锛歕n{text}\n\n")
        self.chat_current_view.see(tk.END)

    def clear_current_chat(self) -> None:
        self.chat_current_view.delete("1.0", tk.END)
        self.chat_current_messages = []

    def archive_chat_session(self) -> None:
        content = self.chat_current_view.get("1.0", tk.END).strip()
        if not content:
            messagebox.showwarning("鏃犳硶褰掓。", "褰撳墠浼氳瘽涓虹┖")
            return
        header = f"==== 浼氳瘽褰掓。 {time.strftime('%Y-%m-%d %H:%M:%S')} ====\n"
        block = header + content + "\n\n"
        self.chat_history_records.append(block)
        self.chat_history_view.insert(tk.END, block)
        self.chat_history_view.see(tk.END)
        self.clear_current_chat()

    def _poll_queues(self) -> None:
        if self.engine is not None:
            transcript_batch: list[str] = []
            while True:
                try:
                    text = self.engine.result_queue.get_nowait()
                except queue.Empty:
                    break
                transcript_batch.append(text)
            if transcript_batch:
                ts = time.strftime("%H:%M:%S")
                self.raw_text.insert(tk.END, "".join(f"[{ts}] {text}\n" for text in transcript_batch))
                self.raw_text.see(tk.END)
            latest_status = None
            while True:
                try:
                    latest_status = self.engine.status_queue.get_nowait()
                except queue.Empty:
                    break
            if latest_status:
                self.status_var.set(latest_status)
            latest_level = None
            while True:
                try:
                    latest_level = self.engine.level_queue.get_nowait()
                except queue.Empty:
                    break
            if latest_level is not None:
                now = time.time()
                should_refresh = (
                    self._last_level_value is None
                    or abs(latest_level - self._last_level_value) >= 0.0015
                    or (now - self._last_level_update_ts) >= 0.25
                )
                if should_refresh:
                    self.level_var.set(f"音量 RMS: {latest_level:.4f}")
                    self._last_level_value = latest_level
                    self._last_level_update_ts = now

        while True:
            try:
                channel, payload = self.ai_queue.get_nowait()
            except queue.Empty:
                break
            if channel == "formal":
                self.formal_text.delete("1.0", tk.END)
                self.formal_text.insert("1.0", payload)
            elif channel == "minutes":
                self.minutes_text.delete("1.0", tk.END)
                self.minutes_text.insert("1.0", payload)
            elif channel == "status":
                self.status_var.set(payload)
            elif channel == "error":
                self.status_var.set("澶辫触")
                messagebox.showerror("閿欒", payload)
            elif channel == "tree":
                self._fill_tree(json.loads(payload).get("buckets", []))
            elif channel == "file":
                info = json.loads(payload)
                desc = f"妗讹細{info['bucket']} | 閿細{info['key']}"
                preview = info["preview"]
                self.file_info_var.set(desc)
                self.file_view.delete("1.0", tk.END)
                self.file_view.insert("1.0", preview)
                self.current_file_desc = desc
                self.current_file_text = preview
            elif channel == "chat_reply":
                self._append_chat_current("鍔╂墜", payload)

        self.root.after(120, self._poll_queues)

    def on_close(self) -> None:
        try:
            self.stop()
        finally:
            self.root.destroy()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="瀹炴椂 WeNet 杞啓涓庝細璁簩娆″姞宸ョ晫闈?)
    parser.add_argument(
        "--model-dir",
        default=str(Path(__file__).parent / "paraformer_model"),
        help="鍖呭惈 train.yaml/final.pt/units.txt 鐨勬ā鍨嬬洰褰?,
    )
    return parser.parse_args()


def main() -> None:
    load_env_file(Path(__file__).parent / ".env")
    args = parse_args()
    root = tk.Tk()
    app = RealtimeAsrGui(root, args.model_dir)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()

