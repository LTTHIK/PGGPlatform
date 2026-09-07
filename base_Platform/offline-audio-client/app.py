from __future__ import annotations

import json
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import sounddevice as sd
import soundfile as sf
import tkinter as tk
from tkinter import messagebox, ttk
try:
    import winsound
except Exception:  # pragma: no cover
    winsound = None

# 可由环境变量或 data/client_config.json 覆盖
DEFAULT_API_BASE = os.getenv("PGG_API_BASE", "https://127.0.0.1:5174")


def _resolve_app_dir() -> Path:
    """源码运行用脚本目录；PyInstaller 打包后用 exe 所在目录，便于 data/ 与 exe 同目录分发。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = _resolve_app_dir()
DATA_DIR = APP_DIR / "data"
RECORDINGS_DIR = DATA_DIR / "recordings"
MANIFEST_PATH = DATA_DIR / "manifest.json"
CONFIG_PATH = DATA_DIR / "client_config.json"

DEFAULT_SAMPLE_RATE = 16000

# 与 Web 前端主色一致（朴睿铂尔 / PCG）
COLOR_BG = "#F4F4F2"
COLOR_NAV = "#1E272E"
COLOR_ACCENT = "#C8A064"
COLOR_TEXT = "#1E272E"
COLOR_CARD = "#FFFFFF"
COLOR_BORDER = "#D1D1C7"
COLOR_PANEL_DARK = "#1F2A37"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def atomic_write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def tls_verify_for_base(base: str) -> bool:
    if base.startswith("https://127.0.0.1") or base.startswith("https://localhost"):
        return False
    return True


class ManifestStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self.data = safe_read_json(
            self.path,
            {
                "version": 1,
                "device_id": uuid.uuid4().hex[:12],
                "updated_at": now_iso(),
                "items": [],
            },
        )
        self._save()

    def _save(self) -> None:
        self.data["updated_at"] = now_iso()
        atomic_write_json(self.path, self.data)

    def list_items(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self.data.get("items", []))

    def upsert_item(self, item: dict[str, Any]) -> None:
        with self._lock:
            items = self.data.setdefault("items", [])
            for idx, old in enumerate(items):
                if old.get("id") == item.get("id"):
                    items[idx] = item
                    self._save()
                    return
            items.append(item)
            self._save()

    def update_item(self, rec_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        with self._lock:
            items = self.data.setdefault("items", [])
            for idx, old in enumerate(items):
                if old.get("id") == rec_id:
                    merged = dict(old)
                    merged.update(patch)
                    items[idx] = merged
                    self._save()
                    return merged
        return None

    def reset_stale_uploading(self) -> None:
        with self._lock:
            items = self.data.setdefault("items", [])
            changed = False
            for idx, old in enumerate(items):
                if old.get("status") == "uploading":
                    items[idx] = {**old, "status": "pending", "last_error": ""}
                    changed = True
            if changed:
                self._save()

    def has_pending_or_failed(self) -> bool:
        with self._lock:
            for it in self.data.get("items", []):
                if it.get("status") in {"pending", "failed"}:
                    return True
        return False


@dataclass
class RecorderState:
    recording_id: str
    file_path: Path
    rel_path: str
    started_ts: float
    sample_rate: int


class AudioRecorder:
    def __init__(self) -> None:
        self._stream: sd.InputStream | None = None
        self._sf: sf.SoundFile | None = None
        self.state: RecorderState | None = None
        self._lock = threading.Lock()

    def start(self, file_path: Path, rel_path: str, sample_rate: int = DEFAULT_SAMPLE_RATE) -> RecorderState:
        with self._lock:
            if self._stream is not None:
                raise RuntimeError("already recording")
            file_path.parent.mkdir(parents=True, exist_ok=True)
            self._sf = sf.SoundFile(
                str(file_path),
                mode="w",
                samplerate=sample_rate,
                channels=1,
                subtype="PCM_16",
            )

            def callback(indata, frames, _time_info, status):
                if status:
                    print(f"[recorder] status={status}", flush=True)
                if self._sf is not None:
                    self._sf.write(indata.copy())

            self._stream = sd.InputStream(
                samplerate=sample_rate,
                channels=1,
                dtype="float32",
                callback=callback,
                blocksize=2048,
            )
            self._stream.start()
            rec_id = f"rec_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            self.state = RecorderState(
                recording_id=rec_id,
                file_path=file_path,
                rel_path=rel_path,
                started_ts=time.time(),
                sample_rate=sample_rate,
            )
            return self.state

    def stop(self) -> tuple[str, float, Path, str, int]:
        with self._lock:
            if self._stream is None or self._sf is None or self.state is None:
                raise RuntimeError("not recording")
            self._stream.stop()
            self._stream.close()
            self._stream = None
            self._sf.flush()
            self._sf.close()
            self._sf = None
            st = self.state
            self.state = None
            duration = max(0.1, time.time() - st.started_ts)
            return st.recording_id, duration, st.file_path, st.rel_path, st.sample_rate


class ClientApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PCG 离线音频采集")
        self.root.geometry("920x580")
        self.root.minsize(800, 480)
        self.root.configure(bg=COLOR_BG)

        self.api_base = DEFAULT_API_BASE
        self._sync_lock = threading.Lock()

        DATA_DIR.mkdir(parents=True, exist_ok=True)
        RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        self.manifest = ManifestStore(MANIFEST_PATH)
        self.manifest.reset_stale_uploading()
        self.recorder = AudioRecorder()

        self.config = safe_read_json(
            CONFIG_PATH,
            {"token": "", "username": "", "auto_upload": True},
        )
        self.token = str(self.config.get("token") or "")

        self.username_var = tk.StringVar(value=str(self.config.get("username") or ""))
        self.password_var = tk.StringVar(value="")
        self.auto_upload_var = tk.BooleanVar(value=bool(self.config.get("auto_upload", True)))
        self.status_var = tk.StringVar(value="离线就绪（录音与列表无需网络）")
        self.record_var = tk.StringVar(value="录音状态：待机")
        self.net_var = tk.StringVar(value="网络：未检测")
        self.auth_var = tk.StringVar(value="登录：未验证")

        self._setup_styles()
        self._build_ui()
        self.refresh_table()

        self.root.after(400, self._bootstrap_async)
        self.root.after(2000, self._schedule_periodic_sync)

    def _setup_styles(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("PCG.TFrame", background=COLOR_BG)
        style.configure("PCG.Card.TLabelframe", background=COLOR_CARD, foreground=COLOR_TEXT, bordercolor=COLOR_BORDER)
        style.configure("PCG.Card.TLabelframe.Label", background=COLOR_CARD, foreground=COLOR_TEXT, font=("Microsoft YaHei UI", 9, "bold"))
        style.configure("PCG.TLabel", background=COLOR_CARD, foreground=COLOR_TEXT, font=("Microsoft YaHei UI", 9))
        style.configure("PCG.Treeview", background=COLOR_CARD, fieldbackground=COLOR_CARD, foreground=COLOR_TEXT, rowheight=28)
        style.configure("PCG.Treeview.Heading", background=COLOR_NAV, foreground=COLOR_ACCENT, font=("Microsoft YaHei UI", 9, "bold"))
        style.map("PCG.Treeview", background=[("selected", "#EDF3FF")])
        style.configure("PCG.TEntry", fieldbackground="#FAFAF8", bordercolor=COLOR_BORDER, padding=4)

    def _btn(
        self,
        parent: tk.Misc,
        text: str,
        command,
        *,
        primary: bool = False,
        danger: bool = False,
        font_override: tuple[str, int] | tuple[str, int, str] | None = None,
    ) -> tk.Button:
        bg = COLOR_CARD
        fg = COLOR_TEXT
        active_bg = "#FDF8E9"
        font = ("Microsoft YaHei UI", 9)
        if primary:
            bg = COLOR_ACCENT
            fg = COLOR_NAV
            active_bg = "#D4B87A"
            font = ("Microsoft YaHei UI", 9, "bold")
        if danger:
            bg = "#9F1239"
            fg = "#FFFFFF"
            active_bg = "#BE123C"
            font = ("Microsoft YaHei UI", 9, "bold")
        button_font = font_override or font
        return tk.Button(
            parent,
            text=text,
            command=command,
            font=button_font,
            bg=bg,
            fg=fg,
            activebackground=active_bg,
            activeforeground=fg,
            relief=tk.FLAT,
            padx=12,
            pady=6,
            highlightbackground=COLOR_BORDER,
            highlightthickness=1,
            cursor="hand2",
        )

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, style="PCG.TFrame", padding=0)
        outer.pack(fill=tk.BOTH, expand=True)

        body = tk.Frame(outer, bg=COLOR_BG)
        body.pack(fill=tk.BOTH, expand=True)

        side_nav = tk.Frame(body, bg=COLOR_NAV, width=190)
        side_nav.pack(side=tk.LEFT, fill=tk.Y)
        side_nav.pack_propagate(False)
        self._build_side_nav(side_nav)

        work_area = tk.Frame(body, bg=COLOR_BG)
        work_area.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self._build_work_area(work_area)

    def _build_side_nav(self, parent: tk.Frame) -> None:
        logo = tk.Frame(parent, bg=COLOR_NAV, height=72)
        logo.pack(fill=tk.X, padx=14, pady=(10, 8))
        logo.pack_propagate(False)
        tk.Label(logo, text="P", bg=COLOR_ACCENT, fg=COLOR_NAV, font=("Times New Roman", 12, "bold"), width=2, height=1).pack(side=tk.LEFT, padx=(0, 10), pady=12)
        tk.Label(logo, text="PCG", bg=COLOR_NAV, fg=COLOR_ACCENT, font=("Times New Roman", 16, "bold")).pack(side=tk.LEFT, pady=12)

        tk.Label(parent, text="离线音频采集客户端", bg=COLOR_NAV, fg="#AEB5BD", font=("Microsoft YaHei UI", 8)).pack(anchor=tk.W, padx=16, pady=(0, 12))

        nav_items = [
            ("需求获取", False),
            ("需求分析", False),
            ("需求分配", False),
            ("素材制作", False),
            ("客户沟通", False),
            ("交付上线", False),
            ("数据反馈", False),
            ("用户管理", False),
            ("离线音频采集", True),
        ]
        for label, active in nav_items:
            self._build_nav_item(parent, label, active=active)

        tk.Label(
            parent,
            text="仅“离线音频采集”可用",
            bg=COLOR_NAV,
            fg="#7A818A",
            font=("Microsoft YaHei UI", 8),
        ).pack(side=tk.BOTTOM, anchor=tk.W, padx=14, pady=12)

    def _build_nav_item(self, parent: tk.Frame, text: str, *, active: bool) -> None:
        item_bg = "#233140" if active else COLOR_NAV
        item_fg = COLOR_ACCENT if active else "#E5E7EB"
        item = tk.Label(
            parent,
            text=f"  {text}",
            bg=item_bg,
            fg=item_fg,
            font=("Microsoft YaHei UI", 10, "bold" if active else "normal"),
            anchor=tk.W,
            padx=10,
            pady=8,
            cursor="arrow" if active else "hand2",
        )
        item.pack(fill=tk.X, padx=10, pady=2)

    def _build_work_area(self, parent: tk.Frame) -> None:
        top_bar = tk.Frame(parent, bg=COLOR_CARD, height=58, highlightbackground=COLOR_BORDER, highlightthickness=1)
        top_bar.pack(fill=tk.X, padx=12, pady=(12, 8))
        top_bar.pack_propagate(False)
        tk.Label(top_bar, text="离线音频采集", bg=COLOR_CARD, fg=COLOR_TEXT, font=("Microsoft YaHei UI", 12, "bold")).pack(side=tk.LEFT, padx=14, pady=12)
        tk.Label(top_bar, textvariable=self.auth_var, bg=COLOR_CARD, fg=COLOR_ACCENT, font=("Microsoft YaHei UI", 9, "bold")).pack(side=tk.RIGHT, padx=12, pady=12)
        tk.Label(top_bar, textvariable=self.net_var, bg=COLOR_CARD, fg="#6B7280", font=("Microsoft YaHei UI", 9)).pack(side=tk.RIGHT, padx=(0, 10), pady=12)

        content = tk.Frame(parent, bg=COLOR_BG)
        content.pack(fill=tk.BOTH, expand=True, padx=12, pady=(0, 12))

        self._build_login_card(content)
        self._build_action_card(content)
        self._build_table_card(content)
        self._build_footer(content)

    def _build_login_card(self, parent: tk.Frame) -> None:
        login_card = ttk.LabelFrame(parent, text="联网后登录（上传需要）", style="PCG.Card.TLabelframe", padding=10)
        login_card.pack(fill=tk.X, pady=(0, 10))
        inner_login = tk.Frame(login_card, bg=COLOR_CARD)
        inner_login.pack(fill=tk.X)
        ttk.Label(inner_login, text="账号", style="PCG.TLabel").grid(row=0, column=0, padx=(0, 6), pady=4, sticky=tk.W)
        ttk.Entry(inner_login, textvariable=self.username_var, width=22, style="PCG.TEntry").grid(row=0, column=1, padx=4, pady=4, sticky=tk.W)
        ttk.Label(inner_login, text="密码", style="PCG.TLabel").grid(row=0, column=2, padx=(16, 6), pady=4, sticky=tk.W)
        ttk.Entry(inner_login, textvariable=self.password_var, width=22, show="*", style="PCG.TEntry").grid(row=0, column=3, padx=4, pady=4, sticky=tk.W)
        self._btn(inner_login, "登录", self.login, primary=True).grid(row=0, column=4, padx=(20, 0), pady=4, sticky=tk.E)
        tk.Checkbutton(
            inner_login,
            text="登录后自动上传",
            variable=self.auto_upload_var,
            command=self.on_toggle_auto_upload,
            bg=COLOR_CARD,
            fg=COLOR_TEXT,
            activebackground=COLOR_CARD,
            activeforeground=COLOR_TEXT,
            selectcolor=COLOR_CARD,
            font=("Microsoft YaHei UI", 9),
            cursor="hand2",
        ).grid(row=0, column=5, padx=(14, 0), pady=4, sticky=tk.W)
        tk.Label(
            inner_login,
            text="说明：录音与本地列表可完全离线；上传走主站代理。可勾选「登录后自动上传」让程序在联网且已登录时自动处理待传记录。",
            font=("Microsoft YaHei UI", 8),
            fg="#6B7280",
            bg=COLOR_CARD,
            wraplength=900,
            justify=tk.LEFT,
        ).grid(row=1, column=0, columnspan=6, sticky=tk.W, pady=(8, 0))

    def _build_action_card(self, parent: tk.Frame) -> None:
        action_card = ttk.LabelFrame(parent, text="离线采集", style="PCG.Card.TLabelframe", padding=10)
        action_card.pack(fill=tk.X, pady=(0, 10))
        inner_act = tk.Frame(action_card, bg=COLOR_CARD)
        inner_act.pack(fill=tk.X)

        status_row = tk.Frame(inner_act, bg=COLOR_CARD)
        status_row.pack(fill=tk.X, pady=(0, 8))
        tk.Label(
            status_row,
            text="状态1：录音 + 转文字",
            bg="#2563EB",
            fg="#FFFFFF",
            font=("Microsoft YaHei UI", 9, "bold"),
            padx=14,
            pady=4,
        ).pack(side=tk.LEFT, padx=(0, 8))
        tk.Label(
            status_row,
            text="状态2：内容录入",
            bg="#EEF2FF",
            fg="#1F2937",
            font=("Microsoft YaHei UI", 9),
            padx=14,
            pady=4,
        ).pack(side=tk.LEFT)

        panel = tk.Frame(inner_act, bg=COLOR_PANEL_DARK, height=128)
        panel.pack(fill=tk.X)
        panel.pack_propagate(False)

        left_tile = tk.Frame(panel, bg=COLOR_PANEL_DARK)
        left_tile.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        divider = tk.Frame(panel, bg="#374151", width=1)
        divider.pack(side=tk.LEFT, fill=tk.Y, pady=22)
        right_tile = tk.Frame(panel, bg=COLOR_PANEL_DARK)
        right_tile.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.start_btn = tk.Button(
            left_tile,
            text="🎤\n\n开始录音",
            command=self.start_recording,
            font=("Segoe UI Emoji", 13, "bold"),
            bg=COLOR_PANEL_DARK,
            fg="#93C5FD",
            activebackground="#253447",
            activeforeground="#BFDBFE",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            justify=tk.CENTER,
        )
        self.start_btn.pack(expand=True)

        self.upload_btn_panel = tk.Button(
            right_tile,
            text="⤴\n\n上传待传记录",
            command=self.upload_pending_in_thread,
            font=("Segoe UI Emoji", 12),
            bg=COLOR_PANEL_DARK,
            fg="#D1D5DB",
            activebackground="#253447",
            activeforeground="#F3F4F6",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            justify=tk.CENTER,
        )
        self.upload_btn_panel.pack(expand=True)

        toolbar = tk.Frame(inner_act, bg=COLOR_CARD)
        toolbar.pack(fill=tk.X, pady=(8, 0))
        self.stop_btn = self._btn(toolbar, "停止录音", self.stop_recording, danger=True)
        self.stop_btn.pack(side=tk.LEFT, padx=(0, 8), pady=2)
        self.stop_btn.configure(state=tk.DISABLED)
        self._btn(toolbar, "刷新列表", self.refresh_table).pack(side=tk.LEFT, padx=4, pady=2)
        self._btn(toolbar, "上传待传记录", self.upload_pending_in_thread, primary=True).pack(side=tk.LEFT, padx=(12, 0), pady=2)
        tk.Label(toolbar, textvariable=self.record_var, font=("Microsoft YaHei UI", 9, "bold"), fg="#B91C1C", bg=COLOR_CARD).pack(side=tk.LEFT, padx=(16, 0), pady=2)

    def _build_table_card(self, parent: tk.Frame) -> None:
        table_card = ttk.LabelFrame(parent, text="本地清单", style="PCG.Card.TLabelframe", padding=6)
        table_card.pack(fill=tk.BOTH, expand=True)
        columns = ("created_at", "id", "file_name", "duration_sec", "status", "uploaded_at", "retry_count", "last_error")
        self.table = ttk.Treeview(table_card, columns=columns, show="headings", height=16, style="PCG.Treeview")
        for col, title, width in [
            ("created_at", "创建时间", 180),
            ("id", "ID", 210),
            ("file_name", "文件", 280),
            ("duration_sec", "时长(s)", 80),
            ("status", "状态", 90),
            ("uploaded_at", "上传时间", 175),
            ("retry_count", "重试", 55),
            ("last_error", "错误", 260),
        ]:
            self.table.heading(col, text=title)
            self.table.column(col, width=width, anchor=tk.W)
        self.table.tag_configure("success", foreground="#15803D")
        sb = ttk.Scrollbar(table_card, orient=tk.VERTICAL, command=self.table.yview)
        self.table.configure(yscrollcommand=sb.set)
        self.table.bind("<Double-1>", self.open_selected_recording)
        self.table.bind("<Return>", self.open_selected_recording)
        self.table.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=4, pady=4)
        sb.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

    def _build_footer(self, parent: tk.Frame) -> None:
        foot = tk.Frame(parent, bg=COLOR_BG)
        foot.pack(fill=tk.X, pady=(8, 0))
        tk.Label(foot, textvariable=self.status_var, font=("Microsoft YaHei UI", 9), fg=COLOR_TEXT, bg=COLOR_BG, anchor=tk.W).pack(fill=tk.X)

    def _set_recording_ui(self, recording: bool) -> None:
        if recording:
            self.record_var.set("录音状态：录音中")
            self.start_btn.configure(
                state=tk.DISABLED,
                text="●\n\n录音中",
                bg="#7F1D1D",
                fg="#FEE2E2",
                activebackground="#7F1D1D",
                activeforeground="#FEE2E2",
            )
            self.stop_btn.configure(state=tk.NORMAL)
            return
        self.record_var.set("录音状态：待机")
        self.start_btn.configure(
            state=tk.NORMAL,
            text="🎤\n\n开始录音",
            bg=COLOR_PANEL_DARK,
            fg="#93C5FD",
            activebackground="#253447",
            activeforeground="#BFDBFE",
        )
        self.stop_btn.configure(state=tk.DISABLED)

    def set_status(self, text: str) -> None:
        self.status_var.set(text)
        self.root.update_idletasks()

    def save_config(self) -> None:
        self.config["username"] = self.username_var.get().strip()
        self.config["token"] = self.token
        self.config["auto_upload"] = bool(self.auto_upload_var.get())
        atomic_write_json(CONFIG_PATH, self.config)

    def on_toggle_auto_upload(self) -> None:
        enabled = bool(self.auto_upload_var.get())
        self.save_config()
        self.set_status("已开启自动上传（联网且已登录时生效）" if enabled else "已关闭自动上传（可手动点击上传）")

    def _url(self, path: str) -> str:
        return f"{self.api_base}{path}"

    def api_get(self, path: str, **kwargs: Any) -> requests.Response:
        url = self._url(path)
        headers = dict(kwargs.pop("headers", {}))
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return requests.get(url, headers=headers, timeout=12, verify=tls_verify_for_base(self.api_base), **kwargs)

    def api_post(self, path: str, **kwargs: Any) -> requests.Response:
        url = self._url(path)
        headers = dict(kwargs.pop("headers", {}))
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return requests.post(url, headers=headers, timeout=30, verify=tls_verify_for_base(self.api_base), **kwargs)

    def check_network(self) -> bool:
        # 能连上服务端并返回任意 HTTP 响应（含 401/404）就视为网络可用
        for path in ("/api/health", "/api/auth/me", "/"):
            try:
                r = requests.get(
                    self._url(path),
                    timeout=6,
                    verify=tls_verify_for_base(self.api_base),
                )
                if r.status_code > 0:
                    return True
            except requests.exceptions.SSLError:
                # 出现证书错误时，尝试关闭校验再探测一次，避免误判网络断开
                try:
                    r = requests.get(self._url(path), timeout=6, verify=False)
                    if r.status_code > 0:
                        return True
                except Exception:
                    pass
            except Exception:
                continue
        return False

    def refresh_network_ui(self) -> None:
        ok = self.check_network()
        self.net_var.set("网络：已连接" if ok else "网络：不可用")
        return ok

    def validate_saved_token(self) -> bool:
        if not self.token.strip():
            self.auth_var.set("登录：未登录")
            return False
        try:
            r = self.api_get("/api/auth/me")
            if r.status_code == 200:
                body = r.json() if r.content else {}
                user = body.get("user") or {}
                name = user.get("username") or self.config.get("username") or "已登录"
                self.auth_var.set(f"登录：{name}（Token 有效）")
                return True
            self.token = ""
            self.save_config()
            self.auth_var.set("登录：已失效，请重新登录")
            return False
        except Exception:
            self.auth_var.set("登录：校验失败（检查网络）")
            return False

    def _bootstrap_async(self) -> None:
        def work() -> None:
            online = self.check_network()

            def on_main() -> None:
                self.net_var.set("网络：已连接" if online else "网络：不可用")
                if online and self.token:
                    if self.validate_saved_token() and self.auto_upload_var.get() and self.manifest.has_pending_or_failed():
                        self.upload_pending(silent=True)
                elif online and self.manifest.has_pending_or_failed() and not self.token:
                    self.set_status("网络已通，有待上传记录，请点击「登录」后上传")

            self.root.after(0, on_main)

        threading.Thread(target=work, daemon=True).start()

    def _schedule_periodic_sync(self) -> None:
        def tick() -> None:
            try:
                if not self.refresh_network_ui():
                    return
                if not self.token:
                    return
                if not self.validate_saved_token():
                    return
                if self.auto_upload_var.get() and self.manifest.has_pending_or_failed():
                    self.upload_pending(silent=True)
            finally:
                self.root.after(60_000, tick)

        self.root.after(60_000, tick)

    def login(self) -> None:
        if not self.refresh_network_ui():
            messagebox.showwarning("提示", "当前无网络，无法登录。请连接网络后再试。")
            return
        username = self.username_var.get().strip()
        password = self.password_var.get().strip()
        if not username or not password:
            messagebox.showwarning("提示", "请输入账号和密码")
            return
        self.set_status("登录中...")
        try:
            resp = requests.post(
                self._url("/api/auth/login"),
                json={"username": username, "password": password},
                headers={"Content-Type": "application/json"},
                timeout=20,
                verify=tls_verify_for_base(self.api_base),
            )
            body = resp.json() if resp.content else {}
            if resp.status_code >= 400:
                raise RuntimeError(str(body.get("detail") or f"HTTP {resp.status_code}"))
            self.token = str(body.get("access_token") or "")
            if not self.token:
                raise RuntimeError("登录失败：未返回 token")
            self.save_config()
            self.validate_saved_token()
            self.set_status("登录成功（Token 已保存，约 7 天内自动复用）")
            if self.auto_upload_var.get() and self.manifest.has_pending_or_failed():
                self.upload_pending_in_thread()
        except Exception as exc:
            self.set_status(f"登录失败: {exc}")
            messagebox.showerror("错误", f"登录失败: {exc}")

    def start_recording(self) -> None:
        try:
            try:
                input_devices = [d for d in sd.query_devices() if int(d.get("max_input_channels", 0)) > 0]
            except Exception as exc:
                raise RuntimeError(f"无法检测录音设备: {exc}") from exc
            if not input_devices:
                raise RuntimeError("未检测到可用麦克风设备")
            date_dir = datetime.now().strftime("%Y-%m-%d")
            rec_id = f"rec_{time.strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
            rel_path = f"{date_dir}/{rec_id}.wav"
            path = RECORDINGS_DIR / rel_path
            self.recorder.start(path, rel_path, DEFAULT_SAMPLE_RATE)
            if winsound is not None:
                winsound.Beep(1200, 180)
            self._set_recording_ui(True)
            self.set_status(f"录音中: {rel_path}")
        except Exception as exc:
            messagebox.showerror("错误", f"启动录音失败: {exc}")

    def stop_recording(self) -> None:
        try:
            rec_id, duration, path, rel_path, sample_rate = self.recorder.stop()
            item = {
                "id": rec_id,
                "file_name": rel_path,
                "created_at": now_iso(),
                "duration_sec": round(duration, 2),
                "sample_rate": sample_rate,
                "channels": 1,
                "status": "pending",
                "retry_count": 0,
                "last_error": "",
                "uploaded_at": "",
                "server_bucket": "",
                "server_key": "",
            }
            self.manifest.upsert_item(item)
            self.refresh_table()
            self._set_recording_ui(False)
            self.set_status(f"录音已保存: {path}")
            if self.auto_upload_var.get() and self.refresh_network_ui() and self.token and self.validate_saved_token():
                self.upload_pending_in_thread()
        except Exception as exc:
            self._set_recording_ui(False)
            messagebox.showerror("错误", f"停止录音失败: {exc}")

    def refresh_table(self) -> None:
        items = sorted(
            self.manifest.list_items(),
            key=lambda x: str(x.get("created_at") or ""),
            reverse=True,
        )
        for i in self.table.get_children():
            self.table.delete(i)
        for item in items:
            status_raw = str(item.get("status", "") or "")
            status_text = {
                "pending": "待上传",
                "uploading": "上传中",
                "success": "上传成功",
                "failed": "上传失败",
            }.get(status_raw, status_raw)
            tag = ("success",) if status_raw == "success" else ()
            self.table.insert(
                "",
                tk.END,
                values=(
                    item.get("created_at", ""),
                    item.get("id", ""),
                    item.get("file_name", ""),
                    item.get("duration_sec", ""),
                    status_text,
                    item.get("uploaded_at", ""),
                    item.get("retry_count", 0),
                    item.get("last_error", ""),
                ),
                tags=tag,
            )

    def open_selected_recording(self, _event=None) -> None:
        selected = self.table.selection()
        if not selected:
            return
        row = self.table.item(selected[0], "values")
        if len(row) < 3:
            return
        rel_path = str(row[2] or "").strip()
        if not rel_path:
            self.set_status("未找到录音文件路径")
            return
        local_path = (RECORDINGS_DIR / rel_path).resolve()
        if not local_path.exists():
            self.set_status(f"文件不存在: {local_path}")
            messagebox.showwarning("提示", f"文件不存在：\n{local_path}")
            return
        try:
            os.startfile(str(local_path))
            self.set_status(f"已打开录音文件: {local_path.name}")
        except Exception as exc:
            messagebox.showerror("错误", f"打开录音文件失败: {exc}")

    def upload_pending_in_thread(self) -> None:
        self._run_upload_on_main_thread(silent=False)

    def _run_upload_on_main_thread(self, *, silent: bool) -> None:
        """Tk 变量与 Treeview 仅在主线程安全；统一排队到主线程执行上传。"""
        if threading.current_thread() is not threading.main_thread():
            self.root.after(0, lambda: self._run_upload_on_main_thread(silent=silent))
            return
        self.upload_pending(silent=silent)

    def upload_pending(self, *, silent: bool) -> None:
        if not self._sync_lock.acquire(blocking=False):
            return
        try:
            if not self.refresh_network_ui():
                if not silent:
                    self.set_status("无网络，无法上传")
                return
            if not self.token:
                if not silent:
                    messagebox.showinfo("提示", "请先登录后再上传。")
                self.set_status("请先登录后再上传")
                return
            if not self.validate_saved_token():
                if not silent:
                    messagebox.showinfo("提示", "登录已失效，请重新登录后再上传。")
                return
            items = self.manifest.list_items()
            todo = [x for x in items if x.get("status") in {"pending", "failed"}]
            if not todo:
                if not silent:
                    self.set_status("没有待上传记录")
                return
            ok = 0
            fail = 0
            for item in todo:
                rec_id = str(item.get("id"))
                rel_path = str(item.get("file_name") or "")
                local_path = RECORDINGS_DIR / rel_path
                if not local_path.exists():
                    self.manifest.update_item(rec_id, {"status": "failed", "last_error": "文件不存在"})
                    fail += 1
                    continue
                self.manifest.update_item(rec_id, {"status": "uploading", "last_error": ""})
                self.root.after(0, self.refresh_table)
                try:
                    with local_path.open("rb") as f:
                        files = {"audio": (local_path.name, f, "audio/wav")}
                        data = {"client_recording_id": rec_id}
                        resp = self.api_post("/api/client/upload/audio", files=files, data=data)
                    body = resp.json() if resp.content else {}
                    if resp.status_code == 401:
                        self.token = ""
                        self.save_config()
                        self.auth_var.set("登录：已失效")
                        raise RuntimeError("登录已过期，请重新登录")
                    if resp.status_code >= 400:
                        raise RuntimeError(str(body.get("detail") or f"HTTP {resp.status_code}"))
                    self.manifest.update_item(
                        rec_id,
                        {
                            "status": "success",
                            "uploaded_at": now_iso(),
                            "last_error": "",
                            "server_bucket": body.get("bucket", ""),
                            "server_key": body.get("key", ""),
                        },
                    )
                    ok += 1
                except Exception as exc:
                    self.manifest.update_item(
                        rec_id,
                        {
                            "status": "failed",
                            "retry_count": int(item.get("retry_count") or 0) + 1,
                            "last_error": str(exc),
                        },
                    )
                    fail += 1
                self.root.after(0, self.refresh_table)
            msg = f"上传完成: 成功 {ok}，失败 {fail}"
            self.root.after(0, lambda: self.set_status(msg))
        finally:
            self._sync_lock.release()


def main() -> None:
    root = tk.Tk()
    ClientApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
