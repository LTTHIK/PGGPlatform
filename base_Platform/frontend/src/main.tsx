import React, { useEffect, useRef, useState } from 'react';
import ReactDOM from 'react-dom/client';
import { icons } from 'lucide';
import './style.css';



            const AUTH_TOKEN_KEY = "pgg_auth_token";

            const STAGES = [
                { id: 'capture', name: '需求采集', icon: 'mic' },
                { id: 'analysis', name: '需求分析', icon: 'layers' },
                { id: 'review', name: '需求评审', icon: 'clipboard-check' },
                { id: 'allocation', name: '需求分配', icon: 'git-branch-plus' },
                { id: 'production', name: '素材制作', icon: 'image' },
                { id: 'comm', name: '客户沟通', icon: 'message-square' },
                { id: 'delivery', name: '交付上线', icon: 'rocket' },
                { id: 'distro', name: '渠道分发', icon: 'share-2' },
                { id: 'feedback', name: '数据反馈', icon: 'bar-chart-3' },
                { id: 'ops', name: '运营维护', icon: 'shield-check' },
                { id: 'users', name: '用户管理', icon: 'users' },
            ];

            const TEMPLATES = [
                { id: 'task', name: '任务布置模板', icon: 'list-checks', desc: '聚焦执行人、事项及截止日期' },
                { id: 'meeting', name: '内部会议纪要', icon: 'briefcase', desc: '记录会议共识与决策结果' },
                { id: 'market', name: '市场分析报告', icon: 'trending-up', desc: '侧重竞品动态与趋势判断' },
            ];

            const FILE_TREE = [];

            const PROMPT_LIBRARY = [
                { id: 'refine', title: '营销需求细化', content: '请基于以上内容，将其转化为符合 PCG 标准的 PRD 方案。', category: '标准化' },
                { id: 'logic', title: '逻辑冲突检索', content: '分析内容中关于预算和周期的冲突点。', category: '审核' },
                { id: 'creative', title: '品牌视觉推演', content: '提炼视觉关键词、配色和字体建议。', category: '创意' }
            ];
            const LEVEL_BAR_HEIGHTS = [34, 58, 46, 72, 40, 66, 52, 60];

            type IconNode = [string, Record<string, unknown>];

            const resolveLucideIcon = (name: string) => {
                const registry = icons as Record<string, unknown>;
                if (registry[name]) return registry[name];
                const pascal = name
                    .split('-')
                    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
                    .join('');
                if (registry[pascal]) return registry[pascal];
                const compact = name.replace(/-/g, '').toLowerCase();
                const matchedKey = Object.keys(registry).find((k) => k.toLowerCase() === compact);
                return matchedKey ? registry[matchedKey] : null;
            };

            const parseIconNodes = (iconData: unknown): IconNode[] => {
                if (!Array.isArray(iconData)) return [];
                if (iconData.length === 0) return [];
                if (typeof iconData[0] === "string") {
                    const pairs: IconNode[] = [];
                    for (let i = 0; i < iconData.length; i += 2) {
                        const tag = iconData[i];
                        const attrs = iconData[i + 1];
                        if (typeof tag !== "string") continue;
                        if (!attrs || typeof attrs !== "object" || Array.isArray(attrs)) {
                            pairs.push([tag, {}]);
                            continue;
                        }
                        pairs.push([tag, attrs as Record<string, unknown>]);
                    }
                    return pairs;
                }
                return iconData
                    .filter((item) => Array.isArray(item) && item.length >= 2 && typeof item[0] === "string")
                    .map((item) => {
                        const tuple = item as [string, Record<string, unknown>];
                        return [tuple[0], tuple[1] && typeof tuple[1] === "object" && !Array.isArray(tuple[1]) ? tuple[1] : {}];
                    });
            };
            const Icon = ({ name, size = 24, className = "", ...rest }) => {
                const iconData = resolveLucideIcon(name);
                const nodes = parseIconNodes(iconData);
                if (!nodes.length) {
                    return (
                        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className={className} {...rest}>
                            <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
                        </svg>
                    );
                }
                return (
                    <svg
                        width={size}
                        height={size}
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        className={className}
                        {...rest}
                    >
                        {nodes.map(([tag, attrs], idx) => React.createElement(tag, { key: `${tag}-${idx}`, ...attrs }))}
                    </svg>
                );
            };

            const MicSolidIcon = ({ size = 32, className = "" }) => (
                <svg
                    width={size}
                    height={size}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={className}
                >
                    <rect x="9" y="3" width="6" height="11" rx="3"></rect>
                    <path d="M5 10a7 7 0 0 0 14 0"></path>
                    <line x1="12" y1="17" x2="12" y2="21"></line>
                    <line x1="8" y1="21" x2="16" y2="21"></line>
                </svg>
            );

            const FolderUploadIcon = ({ size = 30, className = "" }) => (
                <svg
                    width={size}
                    height={size}
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className={className}
                >
                    <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z"></path>
                    <path d="M12 16V10"></path>
                    <path d="M9.5 12.5 12 10l2.5 2.5"></path>
                </svg>
            );

            const App = () => {
                const [authToken, setAuthToken] = useState(() => localStorage.getItem(AUTH_TOKEN_KEY) || "");
                const authTokenRef = useRef(authToken);
                const [currentUser, setCurrentUser] = useState<{ id: number; username: string; role: string } | null>(null);
                const [authChecking, setAuthChecking] = useState(true);
                const [authScreen, setAuthScreen] = useState<"login" | "register">("login");
                const [authForm, setAuthForm] = useState({ username: "", password: "" });
                const [authError, setAuthError] = useState("");
                const [authNotice, setAuthNotice] = useState("");

                const [activeModule, setActiveModule] = useState('capture'); 
                const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
                const [isPromptPanelOpen, setIsPromptPanelOpen] = useState(true);
                const [selectedFile, setSelectedFile] = useState('');
                const [recordingPhase, setRecordingPhase] = useState<"idle" | "preparing" | "active">("idle");
                const recordingPhaseRef = useRef<"idle" | "preparing" | "active">("idle");
                const updateRecordingPhase = (phase: "idle" | "preparing" | "active") => {
                    recordingPhaseRef.current = phase;
                    setRecordingPhase(phase);
                };
                const isRecording = recordingPhase !== "idle";
                const prepareTimerRef = useRef<number | null>(null);
                const reconnectTimerRef = useRef<number | null>(null);
                const reconnectAttemptsRef = useRef(0);
                const reconnectPendingRef = useRef(false);
                const sampleRateRef = useRef<number | null>(null);
                const userStopRef = useRef(false);
                const MAX_RECONNECT_ATTEMPTS = 4;
                const RECONNECT_BASE_MS = 1200;
                const [selectedTemplate, setSelectedTemplate] = useState('task');
                const [captureMode, setCaptureMode] = useState<"audio" | "content">("audio");

                const [processState, setProcessState] = useState({
                    oral: "",
                    written: "",
                    minutes: ""
                });
                const [statusText, setStatusText] = useState("系统就绪");
                const [currentBucket, setCurrentBucket] = useState("");
                const [fileTreeData, setFileTreeData] = useState(FILE_TREE);
                const [expandedNodes, setExpandedNodes] = useState<Record<string, boolean>>({});
                const [selectedFileContent, setSelectedFileContent] = useState("请选择左侧文件查看内容...");
                const [chatMessages, setChatMessages] = useState([
                    { role: "assistant", content: "你好，我是 PCG 智能助手。已为你加载左侧上下文，可结合右侧 SOP 进行深度拆解。" }
                ]);
                const [chatInput, setChatInput] = useState("");
                const [manualForm, setManualForm] = useState({ source: "客户访谈", product: "", company: "", date: "", detail: "" });
                const [llmConfig, setLlmConfig] = useState({
                    base_url: "https://api.deepseek.com/v1",
                    model: "deepseek-chat",
                    api_key: "",
                });

                const wsRef = useRef(null);
                const audioContextRef = useRef(null);
                const mediaStreamRef = useRef(null);
                const sourceNodeRef = useRef(null);
                const processorNodeRef = useRef(null);
                const sessionIdRef = useRef("");
                const selectedObjectRef = useRef(null);
                const oralUploadInputRef = useRef(null);
                const writtenUploadInputRef = useRef(null);
                const minutesUploadInputRef = useRef(null);
                const imageUploadInputRef = useRef<HTMLInputElement | null>(null);
                const offlineAudioInputRef = useRef(null);
                const oralBufferRef = useRef<string[]>([]);
                const oralFlushTimerRef = useRef<number | null>(null);

                useEffect(() => {
                    authTokenRef.current = authToken;
                }, [authToken]);

                const api = async (url: string, options: RequestInit = {}) => {
                    const headers: Record<string, string> = {
                        ...(options.headers as Record<string, string> | undefined),
                    };
                    const isPublicAuth = url.includes("/api/auth/login") || url.includes("/api/auth/register");
                    if (authTokenRef.current && !isPublicAuth) {
                        headers.Authorization = `Bearer ${authTokenRef.current}`;
                    }
                    const resp = await fetch(url, { ...options, headers });
                    const body = await resp.json().catch(() => ({}));
                    if (!resp.ok) {
                        const d = body.detail;
                        let msg = `HTTP ${resp.status}`;
                        if (typeof d === "string") msg = d;
                        else if (Array.isArray(d)) msg = d.map((x: { msg?: string }) => x.msg || JSON.stringify(x)).join("; ");
                        throw new Error(msg);
                    }
                    return body;
                };

                const bootstrapAuth = async () => {
                    const t = localStorage.getItem(AUTH_TOKEN_KEY) || "";
                    if (!t) {
                        setAuthToken("");
                        setCurrentUser(null);
                        setAuthChecking(false);
                        return;
                    }
                    authTokenRef.current = t;
                    setAuthToken(t);
                    try {
                        const body = await api("/api/auth/me");
                        setCurrentUser(body.user || null);
                    } catch {
                        localStorage.removeItem(AUTH_TOKEN_KEY);
                        setAuthToken("");
                        setCurrentUser(null);
                    } finally {
                        setAuthChecking(false);
                    }
                };

                const login = async () => {
                    setAuthError("");
                    setAuthNotice("");
                    try {
                        const body = await api("/api/auth/login", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ username: authForm.username.trim(), password: authForm.password }),
                        });
                        const token = body.access_token || "";
                        localStorage.setItem(AUTH_TOKEN_KEY, token);
                        authTokenRef.current = token;
                        setAuthToken(token);
                        setCurrentUser(body.user || null);
                    } catch (e: unknown) {
                        setAuthError(e instanceof Error ? e.message : String(e));
                    }
                };

                const register = async () => {
                    setAuthError("");
                    setAuthNotice("");
                    try {
                        await api("/api/auth/register", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ username: authForm.username.trim(), password: authForm.password }),
                        });
                        setAuthScreen("login");
                        setAuthNotice("注册成功，请使用新账号登录");
                    } catch (e: unknown) {
                        setAuthError(e instanceof Error ? e.message : String(e));
                    }
                };

                const logout = () => {
                    localStorage.removeItem(AUTH_TOKEN_KEY);
                    authTokenRef.current = "";
                    setAuthToken("");
                    setCurrentUser(null);
                    setActiveModule("capture");
                    setAuthNotice("");
                    setAuthError("");
                };

                const loadLlmConfig = async () => {
                    try {
                        const body = await api("/api/llm/config");
                        setLlmConfig({
                            base_url: body.base_url || "https://api.deepseek.com/v1",
                            model: body.model || "deepseek-chat",
                            api_key: body.api_key || "",
                        });
                    } catch (err) {
                        setStatusText(`加载模型配置失败: ${err.message || err}`);
                    }
                };

                const saveLlmConfig = async () => {
                    try {
                        await api("/api/llm/config", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify(llmConfig),
                        });
                        setStatusText("大模型配置已更新");
                    } catch (err) {
                        setStatusText(`保存模型配置失败: ${err.message || err}`);
                    }
                };

                const arrayBufferToBase64 = (buffer) => {
                    let binary = "";
                    const bytes = new Uint8Array(buffer);
                    for (let i = 0; i < bytes.byteLength; i += 1) binary += String.fromCharCode(bytes[i]);
                    return btoa(binary);
                };

                const floatToPcm16 = (float32Array) => {
                    const pcm = new Int16Array(float32Array.length);
                    for (let i = 0; i < float32Array.length; i += 1) {
                        const s = Math.max(-1, Math.min(1, float32Array[i]));
                        pcm[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff);
                    }
                    return pcm;
                };

                const fileIconByKey = (key) => {
                    const ext = (key.split(".").pop() || "").toLowerCase();
                    if (["wav", "mp3", "flac", "m4a", "aif", "aiff"].includes(ext)) return "mic";
                    if (["txt", "md", "json", "csv", "log"].includes(ext)) return "file-text";
                    return "file";
                };

                const buildMinioTree = (items) => (items || []).map((b) => {
                    const root = {
                        id: `bucket:${b.bucket}`,
                        name: b.bucket,
                        type: "bucket",
                        bucket: b.bucket,
                        children: [],
                    };
                    const folderMap = new Map();
                    folderMap.set("", root);
                    for (const fullKey of (b.keys || [])) {
                        const parts = String(fullKey).split("/").filter(Boolean);
                        let parentPath = "";
                        let parentNode = root;
                        for (let i = 0; i < parts.length; i += 1) {
                            const part = parts[i];
                            const isLeaf = i === parts.length - 1;
                            const curPath = parentPath ? `${parentPath}/${part}` : part;
                            if (isLeaf) {
                                parentNode.children.push({
                                    id: `file:${b.bucket}:${fullKey}`,
                                    name: part,
                                    type: "file",
                                    icon: fileIconByKey(fullKey),
                                    bucket: b.bucket,
                                    key: fullKey,
                                });
                                continue;
                            }
                            if (!folderMap.has(curPath)) {
                                const folderNode = {
                                    id: `folder:${b.bucket}:${curPath}`,
                                    name: part,
                                    type: "folder",
                                    bucket: b.bucket,
                                    path: curPath,
                                    children: [],
                                };
                                parentNode.children.push(folderNode);
                                folderMap.set(curPath, folderNode);
                            }
                            parentNode = folderMap.get(curPath);
                            parentPath = curPath;
                        }
                    }
                    return root;
                });

                const appendOralLine = (line) => {
                    oralBufferRef.current.push(`[${new Date().toLocaleTimeString()}] ${line}`);
                    if (oralFlushTimerRef.current !== null) return;
                    oralFlushTimerRef.current = window.setTimeout(() => {
                        const lines = oralBufferRef.current.splice(0);
                        oralFlushTimerRef.current = null;
                        if (!lines.length) return;
                        setProcessState((prev) => ({
                            ...prev,
                            oral: prev.oral ? `${prev.oral}\n${lines.join("\n")}` : lines.join("\n"),
                        }));
                    }, 120);
                };

                                const resetReconnect = () => {
                    reconnectAttemptsRef.current = 0;
                    if (reconnectTimerRef.current !== null) {
                        window.clearTimeout(reconnectTimerRef.current);
                        reconnectTimerRef.current = null;
                    }
                };

                const scheduleReconnect = () => {
                    if (
                        reconnectAttemptsRef.current >= MAX_RECONNECT_ATTEMPTS ||
                        reconnectTimerRef.current !== null ||
                        reconnectPendingRef.current ||
                        userStopRef.current ||
                        recordingPhaseRef.current === "idle"
                    ) {
                        return;
                    }
                    const delay = RECONNECT_BASE_MS * Math.max(1, reconnectAttemptsRef.current);
                    reconnectTimerRef.current = window.setTimeout(async () => {
                        reconnectTimerRef.current = null;
                        reconnectAttemptsRef.current += 1;
                        reconnectPendingRef.current = true;
                        setStatusText(`尝试重新连接后端...(${reconnectAttemptsRef.current}/${MAX_RECONNECT_ATTEMPTS})`);
                        if (!sampleRateRef.current) {
                            setStatusText("缺少采样率信息，无法重连后端");
                            reconnectPendingRef.current = false;
                            return;
                        }
                        try {
                            await connectWebSocket(sampleRateRef.current);
                        } catch (err) {
                            console.warn('Reconnect failed', err);
                            reconnectPendingRef.current = false;
                            if (reconnectAttemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
                                scheduleReconnect();
                            } else {
                                setStatusText(`后端重连失败，已停止录音，请重新开始`);
                                stopRecording().catch(() => {});
                            }
                        }
                    }, delay);
                };

                const connectWebSocket = async (sampleRate: number) => {
                    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
                    const tok = authTokenRef.current ? `?token=${encodeURIComponent(authTokenRef.current)}` : "";
                    const wsUrl = `${protocol}://${window.location.host}/ws/asr${tok}`;
                    console.log("connectWebSocket", { wsUrl });
                    const ws = new WebSocket(wsUrl);
                    await new Promise((resolve, reject) => {
                        const timer = window.setTimeout(() => reject(new Error("socket timeout")), 8000);
                        ws.onopen = () => { window.clearTimeout(timer); resolve(); };
                        ws.onerror = () => { window.clearTimeout(timer); reject(new Error("socket error")); };
                    });
                    wsRef.current = ws;
                    resetReconnect();
                    ws.onmessage = (event) => {
                        const msg = JSON.parse(event.data || "{}");
                        if (msg.type === "started") {
                            sessionIdRef.current = msg.session_id || "";
                            setStatusText("后端已准备，正在开始识别");
                            if (recordingPhaseRef.current !== "active") {
                                updateRecordingPhase("active");
                            }
                        } else if (msg.type === "level" && typeof msg.rms === "number") {
                            setStatusText(`识别中，RMS ${msg.rms.toFixed(4)}`);
                        } else if (msg.type === "transcript" && msg.text) {
                            appendOralLine(msg.text);
                        } else if (msg.type === "status" && msg.text) {
                            setStatusText(msg.text);
                        } else if (msg.type === "error" && msg.text) {
                            setStatusText(`错误: ${msg.text}`);
                        } else if (msg.type === "stopped") {
                            setStatusText("录音已停止");
                        }
                    };
                    ws.onerror = (event) => {
                        console.error("WebSocket error", event);
                        setStatusText("WebSocket 连接错误，请查看控制台");
                    };
                    ws.onclose = (event) => {
                        console.warn("WebSocket closed", event);
                        if (recordingPhaseRef.current !== "idle" && !userStopRef.current) {
                            if (event.code === 1012) {
                                setStatusText(`连接已关闭(code=${event.code})，后端重启中，正在尝试恢复`);
                            } else {
                                setStatusText(`连接已关闭(code=${event.code})，麦克风仍保持开启，正在尝试恢复后端连接`);
                            }
                            scheduleReconnect();
                        } else {
                            setStatusText(`连接已关闭(code=${event.code} reason=${event.reason || "none"})`);
                        }
                    };
                    ws.send(JSON.stringify({ type: "start", config: { sample_rate: sampleRate, voice_threshold: 0.001, silence_ms: 800 } }));
                };

                const startRecording = async () => {
                    if (recordingPhase !== "idle") return;
                    try {
                        setStatusText("正在启动录音");
                        const getUserMedia = async (constraints) => {
                            const nav = window.navigator;
                            const hasMediaDevices = !!(nav.mediaDevices && typeof nav.mediaDevices.getUserMedia === "function");
                            const legacyGetUserMedia = nav.getUserMedia || nav.webkitGetUserMedia || nav.mozGetUserMedia || nav.msGetUserMedia;
                            const hasLegacy = typeof legacyGetUserMedia === "function";
                            console.log("getUserMedia check", {
                                url: window.location.href,
                                protocol: window.location.protocol,
                                host: window.location.host,
                                userAgent: nav.userAgent,
                                hasMediaDevices,
                                hasLegacy,
                                mediaDevices: !!nav.mediaDevices,
                            });
                            if (hasMediaDevices) {
                                return nav.mediaDevices.getUserMedia(constraints);
                            }
                            if (hasLegacy) {
                                return new Promise((resolve, reject) => {
                                    legacyGetUserMedia.call(nav, constraints, resolve, reject);
                                });
                            }
                            throw new Error(`当前浏览器环境不支持麦克风采集。
URL: ${window.location.href}
userAgent: ${nav.userAgent}
mediaDevices: ${String(!!nav.mediaDevices)}
请使用 Chrome/Edge 等现代浏览器，并在 HTTPS 安全页面（或通过浏览器安全策略）下打开页面。`);
                        };
                        const stream = await getUserMedia({ audio: true });
                        mediaStreamRef.current = stream;
                        const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                        audioContextRef.current = audioContext;
                        const source = audioContext.createMediaStreamSource(stream);
                        const processor = audioContext.createScriptProcessor(4096, 1, 1);
                        sourceNodeRef.current = source;
                        processorNodeRef.current = processor;
                        const sampleRate = audioContext.sampleRate;
                        sampleRateRef.current = sampleRate;
                        userStopRef.current = false;
                        resetReconnect();
                        await connectWebSocket(sampleRate);
                        updateRecordingPhase("preparing");
                        setStatusText("麦克风已打开，后端准备中...");
                        prepareTimerRef.current = window.setTimeout(() => {
                            if (recordingPhaseRef.current === "preparing") {
                                updateRecordingPhase("active");
                                setStatusText("录音识别中...");
                            }
                        }, 3400);
                        processor.onaudioprocess = (e) => {
                            if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
                                console.warn("WebSocket not open, audio chunk dropped");
                                return;
                            }
                            const input = e.inputBuffer.getChannelData(0);
                            const pcm16 = floatToPcm16(input);
                            wsRef.current.send(JSON.stringify({ type: "audio", pcm16: arrayBufferToBase64(pcm16.buffer) }));
                        };
                        source.connect(processor);
                        processor.connect(audioContext.destination);
                    } catch (err) {
                        setStatusText(`录音启动失败: ${err.message || err}`);
                        updateRecordingPhase("idle");
                    }
                };

                const stopRecording = async () => {
                    try {
                        userStopRef.current = true;
                        if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
                            wsRef.current.send(JSON.stringify({ type: "stop" }));
                        }
                        processorNodeRef.current?.disconnect();
                        sourceNodeRef.current?.disconnect();
                        mediaStreamRef.current?.getTracks()?.forEach((t) => t.stop());
                        if (audioContextRef.current) await audioContextRef.current.close();
                        wsRef.current?.close();
                        if (prepareTimerRef.current !== null) {
                            window.clearTimeout(prepareTimerRef.current);
                            prepareTimerRef.current = null;
                        }
                        resetReconnect();
                        updateRecordingPhase("idle");
                    } catch (err) {
                        setStatusText(`停止失败: ${err.message || err}`);
                    }
                };
const handleRecordToggle = () => {
                    if (recordingPhase === "idle") {
                        startRecording();
                    } else {
                        stopRecording();
                    }
                };

                const runPolish = async () => {
                    if (!processState.oral.trim()) return;
                    setStatusText("正在进行 AI 整理");
                    try {
                        const body = await api("/api/polish", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ text: processState.oral }),
                        });
                        setProcessState((prev) => ({ ...prev, written: body.text || "" }));
                        setStatusText("书面稿已生成");
                    } catch (err) {
                        setStatusText(`整理失败: ${err.message || err}`);
                    }
                };

                const runMinutes = async () => {
                    if (!processState.written.trim()) return;
                    setStatusText("正在生成纪要");
                    try {
                        const body = await api("/api/minutes", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ text: processState.written }),
                        });
                        setProcessState((prev) => ({ ...prev, minutes: body.text || "" }));
                        setStatusText("纪要已生成");
                    } catch (err) {
                        setStatusText(`纪要生成失败: ${err.message || err}`);
                    }
                };

                const uploadTextByKind = async (kind, content) => {
                    if (!content.trim()) throw new Error("内容为空，无法上传");
                    const body = await api("/api/upload/text", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({ kind, content }),
                    });
                    setCurrentBucket(body.bucket || "");
                    setStatusText(`上传成功: ${body.bucket}/${body.key}`);
                };

                const uploadRecording = async () => {
                    let body;
                    if (sessionIdRef.current) {
                        body = await api("/api/upload/recording", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ session_id: sessionIdRef.current }),
                        });
                    } else {
                        body = await api("/api/upload/recording/latest", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                        });
                    }
                    setCurrentBucket(body.bucket || "");
                    setStatusText(`录音上传成功: ${body.bucket}/${body.key}`);
                };

                const uploadAll = async () => {
                    const body = await api("/api/upload/all", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            session_id: sessionIdRef.current || null,
                            raw: processState.oral,
                            formal: processState.written,
                            minutes: processState.minutes,
                        }),
                    });
                    if (body.results && body.results.length > 0) setCurrentBucket(body.results[0].bucket || currentBucket);
                    if (body.errors && body.errors.length) setStatusText(`部分失败: ${body.errors.join("; ")}`);
                    else setStatusText("一键上传完成");
                };

                const uploadTypedFile = async (type, file) => {
                    if (!file) return;
                    const text = await file.text();
                    if (type === "oral") setProcessState((prev) => ({ ...prev, oral: text }));
                    if (type === "written") setProcessState((prev) => ({ ...prev, written: text }));
                    if (type === "minutes") setProcessState((prev) => ({ ...prev, minutes: text }));
                    if (type === "sop") setChatInput(text);
                    setStatusText(`已加载文件: ${file.name}`);
                };

                const transcribeOfflineAudio = async (file) => {
                    if (!file) return;
                    const fd = new FormData();
                    fd.append("audio", file);
                    setStatusText("正在转写离线音频");
                    try {
                        const body = await api("/api/transcribe", { method: "POST", body: fd });
                        setProcessState((prev) => ({ ...prev, oral: body.text || "" }));
                        setStatusText("离线音频转写完成");
                    } catch (err) {
                        setStatusText(`离线转写失败: ${err.message || err}`);
                    }
                };

                const submitManualNeed = () => {
                    const parts = [
                        `需求来源: ${manualForm.source || "-"}`,
                        `产品: ${manualForm.product || "-"}`,
                        `所属公司: ${manualForm.company || "-"}`,
                        `录入日期: ${manualForm.date || "-"}`,
                        `需求详情: ${manualForm.detail || "-"}`,
                    ];
                    setProcessState((prev) => ({ ...prev, oral: prev.oral ? `${prev.oral}\n\n${parts.join("\n")}` : parts.join("\n") }));
                    setStatusText("手动需求已加入口述稿");
                };

                const saveManualNeed = () => {
                    localStorage.setItem("pcg_manual_need_draft", JSON.stringify(manualForm));
                    setStatusText("手动录入内容已保存");
                };

                const insertImageReference = (file) => {
                    if (!file) return;
                    const line = `[${new Date().toLocaleTimeString()}] [图片文件] ${file.name} (${Math.round(file.size / 1024)} KB)`;
                    setProcessState((prev) => ({ ...prev, oral: prev.oral ? `${prev.oral}\n${line}` : line }));
                    setStatusText(`已导入图片引用: ${file.name}`);
                };

                const refreshTree = async () => {
                    try {
                        const body = await api("/api/minio/tree");
                        setCurrentBucket(body.current_bucket || currentBucket);
                        const built = buildMinioTree(body.items || []);
                        setFileTreeData(built);
                        setExpandedNodes((prev) => {
                            const next = { ...prev };
                            for (const bucketNode of built) {
                                if (next[bucketNode.id] === undefined) next[bucketNode.id] = true;
                                for (const child of bucketNode.children || []) {
                                    if (child.type !== "file" && next[child.id] === undefined) {
                                        next[child.id] = true;
                                    }
                                }
                            }
                            return next;
                        });
                        setStatusText("MinIO 树已刷新");
                    } catch (err) {
                        setStatusText(`刷新树失败: ${err.message || err}`);
                    }
                };

                const handleSelectObject = async (bucket, key) => {
                    try {
                        selectedObjectRef.current = { bucket, key };
                        setSelectedFile(`${bucket}/${key}`);
                        const body = await api(`/api/minio/object?bucket=${encodeURIComponent(bucket)}&key=${encodeURIComponent(key)}`);
                        setSelectedFileContent(body.preview || "");
                        setStatusText(`已选中文件: ${key}`);
                    } catch (err) {
                        setStatusText(`文件读取失败: ${err.message || err}`);
                    }
                };

                const sendChat = async () => {
                    const text = chatInput.trim();
                    if (!text) return;
                    const context = selectedObjectRef.current ? `\n\n【当前文件】 ${selectedObjectRef.current.bucket}/${selectedObjectRef.current.key}\n${selectedFileContent.slice(0, 12000)}` : "";
                    const nextMessages = [...chatMessages, { role: "user", content: text }];
                    setChatMessages(nextMessages);
                    setChatInput("");
                    try {
                        const body = await api("/api/chat", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                messages: [
                                    { role: "system", content: "你是会议内容加工助手，基于已有文件上下文进行结构化分析。" },
                                    ...nextMessages.map((m) => ({ role: m.role === "assistant" ? "assistant" : "user", content: m.content })),
                                    { role: "user", content: `${text}${context}` },
                                ],
                            }),
                        });
                        setChatMessages((prev) => [...prev, { role: "assistant", content: body.text || "" }]);
                    } catch (err) {
                        setChatMessages((prev) => [...prev, { role: "assistant", content: `抱歉，调用失败：${err.message || err}` }]);
                    }
                };

                useEffect(() => {
                    void bootstrapAuth();
                }, []);

                useEffect(() => {
                    if (authChecking || !currentUser) return;
                    refreshTree();
                    loadLlmConfig();
                    const draft = localStorage.getItem("pcg_manual_need_draft");
                    if (draft) {
                        try {
                            setManualForm(JSON.parse(draft));
                        } catch {
                            // ignore malformed local draft
                        }
                    }
                    return () => {
                        if (oralFlushTimerRef.current !== null) {
                            window.clearTimeout(oralFlushTimerRef.current);
                        }
                        stopRecording();
                    };
                }, [authChecking, currentUser]);

                const [adminUsers, setAdminUsers] = useState<Array<Record<string, unknown>>>([]);
                const [adminNew, setAdminNew] = useState({ username: "", password: "", role: "user" });
                const [adminBusy, setAdminBusy] = useState(false);

                const loadAdminUsers = async () => {
                    try {
                        const body = await api("/api/admin/users");
                        setAdminUsers(body.items || []);
                    } catch (err: unknown) {
                        setStatusText(`加载用户失败: ${err instanceof Error ? err.message : String(err)}`);
                    }
                };

                const adminCreateUser = async () => {
                    setAdminBusy(true);
                    try {
                        await api("/api/admin/users", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify(adminNew),
                        });
                        setAdminNew({ username: "", password: "", role: "user" });
                        await loadAdminUsers();
                        setStatusText("用户已创建");
                    } catch (err: unknown) {
                        setStatusText(`创建失败: ${err instanceof Error ? err.message : String(err)}`);
                    } finally {
                        setAdminBusy(false);
                    }
                };

                const patchUser = async (id: number, patch: Record<string, unknown>) => {
                    setAdminBusy(true);
                    try {
                        await api(`/api/admin/users/${id}`, {
                            method: "PATCH",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify(patch),
                        });
                        await loadAdminUsers();
                        const me = await api("/api/auth/me");
                        setCurrentUser(me.user || null);
                        setStatusText("用户已更新");
                    } catch (err: unknown) {
                        setStatusText(`更新失败: ${err instanceof Error ? err.message : String(err)}`);
                    } finally {
                        setAdminBusy(false);
                    }
                };

                useEffect(() => {
                    if (activeModule === "users" && currentUser?.role === "admin") {
                        void loadAdminUsers();
                    }
                    if (activeModule === "users" && currentUser && currentUser.role !== "admin") {
                        setActiveModule("capture");
                    }
                }, [activeModule, currentUser]);

                const UsersAdminModule = () => (
                    <div className="flex-1 overflow-auto p-8 bg-[#F4F4F2]">
                        <div className="max-w-4xl mx-auto space-y-8">
                            <div className="bg-white border border-[#D1D1C7] rounded-2xl p-6 shadow-sm">
                                <h2 className="text-sm font-bold text-[#1E272E] mb-4 flex items-center gap-2">
                                    <Icon name="user-plus" size={18} className="text-[#C8A064]" />
                                    新建用户（可指定管理员；公开注册页面无法获得管理员权限）
                                </h2>
                                <div className="grid grid-cols-1 md:grid-cols-4 gap-3 items-end">
                                    <div>
                                        <label className="text-[10px] text-gray-500 uppercase block mb-1">账号</label>
                                        <input
                                            value={adminNew.username}
                                            onChange={(e) => setAdminNew((p) => ({ ...p, username: e.target.value }))}
                                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-[#C8A064]"
                                            placeholder="登录名"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[10px] text-gray-500 uppercase block mb-1">密码</label>
                                        <input
                                            type="password"
                                            value={adminNew.password}
                                            onChange={(e) => setAdminNew((p) => ({ ...p, password: e.target.value }))}
                                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-[#C8A064]"
                                            placeholder="至少 6 位"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[10px] text-gray-500 uppercase block mb-1">角色</label>
                                        <select
                                            value={adminNew.role}
                                            onChange={(e) => setAdminNew((p) => ({ ...p, role: e.target.value }))}
                                            className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-[#C8A064]"
                                        >
                                            <option value="user">普通用户</option>
                                            <option value="admin">管理员</option>
                                        </select>
                                    </div>
                                    <button
                                        type="button"
                                        disabled={adminBusy}
                                        onClick={() => void adminCreateUser()}
                                        className="py-2.5 rounded-lg bg-[#1E272E] text-[#C8A064] text-xs font-bold disabled:opacity-40 hover:brightness-110"
                                    >
                                        创建
                                    </button>
                                </div>
                            </div>
                            <div className="bg-white border border-[#D1D1C7] rounded-2xl overflow-hidden shadow-sm">
                                <div className="px-6 py-3 border-b border-gray-200 flex justify-between items-center">
                                    <span className="text-sm font-bold text-[#1E272E]">用户列表</span>
                                    <button type="button" onClick={() => void loadAdminUsers()} className="text-xs text-gray-500 hover:text-[#C8A064] font-semibold">
                                        刷新
                                    </button>
                                </div>
                                <div className="overflow-x-auto">
                                    <table className="w-full text-left text-sm min-w-[640px]">
                                        <thead className="bg-gray-50 text-[10px] uppercase text-gray-500">
                                            <tr>
                                                <th className="px-4 py-2">ID</th>
                                                <th className="px-4 py-2">账号</th>
                                                <th className="px-4 py-2">角色</th>
                                                <th className="px-4 py-2">状态</th>
                                                <th className="px-4 py-2 w-[280px]">操作</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {adminUsers.map((u) => {
                                                const uid = Number(u.id);
                                                const isSelf = currentUser && Number(currentUser.id) === uid;
                                                return (
                                                    <tr key={String(u.id)} className="border-t border-gray-100 hover:bg-gray-50/80">
                                                        <td className="px-4 py-2 font-mono text-xs">{String(u.id)}</td>
                                                        <td className="px-4 py-2 font-medium">{String(u.username)}</td>
                                                        <td className="px-4 py-2">{u.role === "admin" ? "管理员" : "普通用户"}</td>
                                                        <td className="px-4 py-2">{u.is_active ? "启用" : "停用"}</td>
                                                        <td className="px-4 py-2 flex flex-wrap gap-2">
                                                            <button
                                                                type="button"
                                                                disabled={adminBusy || u.role === "admin"}
                                                                onClick={() => void patchUser(uid, { role: "admin" })}
                                                                className="px-2 py-1 rounded text-[10px] font-bold bg-[#FDF8E9] text-[#8B6E3F] border border-[#C8A064]/30 disabled:opacity-30"
                                                            >
                                                                设为管理员
                                                            </button>
                                                            <button
                                                                type="button"
                                                                disabled={adminBusy || u.role === "user"}
                                                                onClick={() => void patchUser(uid, { role: "user" })}
                                                                className="px-2 py-1 rounded text-[10px] font-bold bg-gray-100 text-gray-600 border border-gray-200 disabled:opacity-30"
                                                            >
                                                                设为普通用户
                                                            </button>
                                                            <button
                                                                type="button"
                                                                disabled={adminBusy || (isSelf && u.is_active)}
                                                                onClick={() => void patchUser(uid, { is_active: !u.is_active })}
                                                                className="px-2 py-1 rounded text-[10px] font-bold bg-white border border-gray-200 text-gray-600 disabled:opacity-30"
                                                            >
                                                                {u.is_active ? "停用" : "启用"}
                                                            </button>
                                                            <button
                                                                type="button"
                                                                disabled={adminBusy}
                                                                onClick={() => {
                                                                    const np = window.prompt("输入新密码（至少 6 位）", "");
                                                                    if (!np || np.length < 6) return;
                                                                    void patchUser(uid, { password: np });
                                                                }}
                                                                className="px-2 py-1 rounded text-[10px] font-bold text-[#2563EB] border border-blue-200 bg-blue-50/50 disabled:opacity-30"
                                                            >
                                                                重置密码
                                                            </button>
                                                        </td>
                                                    </tr>
                                                );
                                            })}
                                        </tbody>
                                    </table>
                                </div>
                            </div>
                        </div>
                    </div>
                );

                // --- 鐎涙劖膩閸ф绱伴棁鈧Ч鍌濆箯閸?(娑撱儲鐗搁柆闈涙儕閸ュ墽澧栫拋鎹愵吀) ---
                const CaptureModule = () => (
                    <div className="flex-1 flex flex-col relative h-full overflow-hidden">
                        {/* 1. 妞ゅ爼鍎撮崗銊╁櫤閹貉冨煑閹稿鎸?*/}
                        <div className="bg-white px-8 py-3 border-b border-[#D1D1C7] shadow-sm flex flex-wrap gap-4 items-center z-20 shrink-0">
                            <div className="flex flex-wrap gap-2">
                                <button onClick={async () => {
                                    try {
                                        setStatusText("正在上传录音到 MinIO");
                                        await uploadRecording();
                                        await refreshTree();
                                    } catch (err) {
                                        setStatusText(`录音上传失败: ${err.message || err}`);
                                    }
                                }} className="flex items-center gap-1.5 px-4 py-1.5 bg-white border border-gray-200 text-gray-600 text-[11px] font-semibold rounded-lg shadow-sm hover:border-[#C8A064] transition-all">
                                    <Icon name="phone-incoming" size={13} /> 现场录音导入
                                </button>
                                <button onClick={async () => {
                                    try {
                                        setStatusText("正在上传口述稿到 MinIO");
                                        await uploadTextByKind("raw", processState.oral);
                                        await refreshTree();
                                    } catch (err) {
                                        setStatusText(`口述稿上传失败: ${err.message || err}`);
                                    }
                                }} className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 text-gray-500 text-[11px] font-medium rounded-lg hover:border-[#C8A064] transition-all"><Icon name="upload" size={13} /> 导入口述稿</button>
                                <button onClick={async () => {
                                    try {
                                        setStatusText("正在上传书面稿到 MinIO");
                                        await uploadTextByKind("formal", processState.written);
                                        await refreshTree();
                                    } catch (err) {
                                        setStatusText(`书面稿上传失败: ${err.message || err}`);
                                    }
                                }} className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 text-gray-500 text-[11px] font-medium rounded-lg hover:border-[#C8A064] transition-all"><Icon name="upload" size={13} /> 导入书面稿</button>
                                <button onClick={async () => {
                                    try {
                                        setStatusText("正在上传纪要稿到 MinIO");
                                        await uploadTextByKind("minutes", processState.minutes);
                                        await refreshTree();
                                    } catch (err) {
                                        setStatusText(`纪要稿上传失败: ${err.message || err}`);
                                    }
                                }} className="flex items-center gap-1.5 px-3 py-1.5 bg-white border border-gray-200 text-gray-500 text-[11px] font-medium rounded-lg hover:border-[#C8A064] transition-all"><Icon name="upload" size={13} /> 导入纪要稿</button>
                                <button onClick={async () => {
                                    try {
                                        setStatusText("正在一键导入全部内容到 MinIO");
                                        await uploadAll();
                                        await refreshTree();
                                    } catch (err) {
                                        setStatusText(`SOP 一键导入失败: ${err.message || err}`);
                                    }
                                }} className="flex items-center gap-1.5 px-3 py-1.5 bg-[#C8A064] text-white text-[11px] font-bold rounded-lg shadow-md hover:brightness-110 transition-all"><Icon name="book-open" size={13} /> 导入 SOP</button>
                            </div>
                            <div className="ml-auto">
                                <button onClick={() => setProcessState({ oral: "", written: "", minutes: "" })} className="text-red-400 hover:bg-red-50 px-3 py-1.5 rounded-lg text-[11px] font-bold transition-all flex items-center gap-1">
                                    <Icon name="trash-2" size={14} /> 清空全部
                                </button>
                            </div>
                        </div>

                        <input ref={oralUploadInputRef} type="file" accept=".txt,.md,.json,.csv,.log" className="hidden" onChange={(e) => uploadTypedFile("oral", e.target.files && e.target.files[0])} />
                        <input ref={writtenUploadInputRef} type="file" accept=".txt,.md,.json,.csv,.log" className="hidden" onChange={(e) => uploadTypedFile("written", e.target.files && e.target.files[0])} />
                        <input ref={minutesUploadInputRef} type="file" accept=".txt,.md,.json,.csv,.log" className="hidden" onChange={(e) => uploadTypedFile("minutes", e.target.files && e.target.files[0])} />
                        <input ref={imageUploadInputRef} type="file" accept="image/*" className="hidden" onChange={(e) => insertImageReference(e.target.files && e.target.files[0])} />
                        <input ref={offlineAudioInputRef} type="file" accept="audio/*,.wav,.mp3,.flac,.m4a,.aif,.aiff" className="hidden" onChange={(e) => transcribeOfflineAudio(e.target.files && e.target.files[0])} />

                        {/* 娑撳楠囬崘鍛啇閸?*/}
                        <div className="flex-1 p-8 grid grid-cols-1 lg:grid-cols-3 gap-8 overflow-hidden bg-[#F4F4F2] bg-[url('https://www.transparenttextures.com/patterns/natural-paper.png')]">
                            
                            {/* 原始采集：双状态（录音 / 内容录入） */}
                            <section className="flex flex-col h-full animate-in relative overflow-hidden">
                                <div className="flex items-center gap-2 mb-4">
                                    <div className="w-1.5 h-6 bg-[#1E272E]"></div>
                                    <h3 className="text-sm font-serif font-bold tracking-widest text-[#1E272E] uppercase">1) 原始采集 / 口述稿</h3>
                                </div>

                                <div className="flex-1 flex flex-col overflow-hidden bg-white border border-[#D1D1C7] rounded-2xl shadow-sm">
                                    <div className="p-3 border-b border-[#E5E7EB] bg-[#fff5f5]">
                                        <div className="grid grid-cols-2 gap-2">
                                            <button
                                                onClick={() => setCaptureMode("audio")}
                                                className={`h-9 rounded-lg text-[12px] font-bold transition-all ${captureMode === "audio" ? "bg-[#2563EB] text-white shadow" : "bg-white text-[#1D4ED8] border border-[#93C5FD]"}`}
                                            >
                                                状态1：录音 + 转文字
                                            </button>
                                            <button
                                                onClick={() => setCaptureMode("content")}
                                                className={`h-9 rounded-lg text-[12px] font-bold transition-all ${captureMode === "content" ? "bg-[#2563EB] text-white shadow" : "bg-white text-[#1D4ED8] border border-[#93C5FD]"}`}
                                            >
                                                状态2：内容录入
                                            </button>
                                        </div>
                                    </div>

                                    {captureMode === "audio" ? (
                                        <div className="flex-1 flex flex-col overflow-hidden">
                                            <div className="bg-[#1E272E] p-8 flex flex-col items-center justify-center gap-6 shrink-0 h-[220px]">
                                                <div className="flex items-center gap-12">
                                                    <button onClick={handleRecordToggle} className="flex flex-col items-center gap-2 group">
                                                        <div className={`w-16 h-16 rounded-full flex items-center justify-center transition-all ${recordingPhase === 'active' ? 'bg-red-500 scale-110 shadow-lg shadow-red-500/40 animate-pulse' : recordingPhase === 'preparing' ? 'bg-blue-500/20 border border-blue-300/40 shadow-lg animate-pulse' : 'bg-white/5 border border-[#60A5FA]/30 text-[#2563EB] hover:bg-[#60A5FA] hover:text-white'}`}>
                                                            {recordingPhase === 'preparing' ? (
                                                                <div className="w-10 h-10 rounded-full border-4 border-white/20 border-t-[#C8A064] animate-spin" />
                                                            ) : recordingPhase === 'active' ? (
                                                                <div className="w-10 h-10 rounded-full bg-white animate-pulse shadow-[0_0_0_16px_rgba(255,255,255,0.1)]" />
                                                            ) : (
                                                                <MicSolidIcon size={32} />
                                                            )}
                                                        </div>
                                                        <span className="text-[10px] font-bold uppercase text-gray-400">现场录音</span>
                                                    </button>
                                                    <div className="h-14 w-px bg-white/10"></div>
                                                    <button onClick={() => offlineAudioInputRef.current && offlineAudioInputRef.current.click()} className="flex flex-col items-center gap-2 group transition-all">
                                                        <div className="w-16 h-16 rounded-full bg-white/5 border border-white/10 flex items-center justify-center text-gray-500 hover:text-[#C8A064] hover:bg-white/5 transition-all"><FolderUploadIcon size={30} /></div>
                                                        <span className="text-[10px] font-bold uppercase text-gray-400">离线音频导入</span>
                                                    </button>
                                                </div>
                                                {isRecording && <div className={`flex gap-1.5 h-5 items-center ${recordingPhase === 'active' ? 'animate-pulse' : ''}`}>{LEVEL_BAR_HEIGHTS.map((h, i) => <div key={i} className={`w-1 bg-[#C8A064] rounded-full ${recordingPhase === 'active' ? 'animate-pulse opacity-90' : ''}`} style={{ height: `${h}%` }}></div>)}</div>}
                                            </div>
                                            <div className="flex-1 p-4 overflow-hidden">
                                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest mb-2">音频转写窗口</p>
                                                <textarea
                                                    readOnly
                                                    value={processState.oral}
                                                    placeholder="录音转文字结果会实时显示在这里..."
                                                    className="w-full h-full bg-white border border-[#E5E7EB] rounded-xl p-3 text-[12px] leading-relaxed text-[#374151] resize-none outline-none"
                                                />
                                            </div>
                                        </div>
                                    ) : (
                                        <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6 scrollbar-hide">
                                            <div className="space-y-3">
                                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest border-l-2 border-[#C8A064] pl-2">内容导入（文本 / 图像）</p>
                                                <div className="grid grid-cols-3 gap-2">
                                                    <button onClick={() => oralUploadInputRef.current && oralUploadInputRef.current.click()} className="flex flex-col items-center gap-2 p-3 rounded-xl border border-dashed border-gray-200 hover:border-[#C8A064] hover:bg-[#FDF8E9]/50 transition-all group">
                                                        <Icon name="file-text" size={18} className="text-blue-500" /><span className="text-[9px] font-bold text-gray-500 uppercase">文本文件</span>
                                                    </button>
                                                    <button onClick={() => writtenUploadInputRef.current && writtenUploadInputRef.current.click()} className="flex flex-col items-center gap-2 p-3 rounded-xl border border-dashed border-gray-200 hover:border-[#C8A064] hover:bg-[#FDF8E9]/50 transition-all group">
                                                        <Icon name="file" size={18} className="text-red-500" /><span className="text-[9px] font-bold text-gray-500 uppercase">结构文档</span>
                                                    </button>
                                                    <button onClick={() => imageUploadInputRef.current && imageUploadInputRef.current.click()} className="flex flex-col items-center gap-2 p-3 rounded-xl border border-dashed border-gray-200 hover:border-[#C8A064] hover:bg-[#FDF8E9]/50 transition-all group">
                                                        <Icon name="image" size={18} className="text-purple-500" /><span className="text-[9px] font-bold text-gray-500 uppercase">图片内容</span>
                                                    </button>
                                                </div>
                                            </div>

                                            <div className="space-y-3 pb-4">
                                                <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest border-l-2 border-[#C8A064] pl-2">手动录入需求</p>
                                                <div className="grid grid-cols-2 gap-3">
                                                    <div className="col-span-1 space-y-1"><label className="text-[8px] font-bold text-gray-400 uppercase">需求来源</label><select value={manualForm.source} onChange={(e) => setManualForm((prev) => ({ ...prev, source: e.target.value }))} className="w-full bg-gray-50 border-none rounded-lg p-1.5 text-[11px] focus:ring-1 ring-[#C8A064] outline-none"><option>客户访谈</option><option>头脑风暴</option></select></div>
                                                    <div className="col-span-1 space-y-1"><label className="text-[8px] font-bold text-gray-400 uppercase">产品</label><input value={manualForm.product} onChange={(e) => setManualForm((prev) => ({ ...prev, product: e.target.value }))} type="text" placeholder="Product" className="w-full bg-gray-50 border-none rounded-lg p-1.5 text-[11px] focus:ring-1 ring-[#C8A064] outline-none" /></div>
                                                    <div className="col-span-1 space-y-1"><label className="text-[8px] font-bold text-gray-400 uppercase">所属公司</label><input value={manualForm.company} onChange={(e) => setManualForm((prev) => ({ ...prev, company: e.target.value }))} type="text" placeholder="Company" className="w-full bg-gray-50 border-none rounded-lg p-1.5 text-[11px] focus:ring-1 ring-[#C8A064] outline-none" /></div>
                                                    <div className="col-span-1 space-y-1"><label className="text-[8px] font-bold text-gray-400 uppercase">录入日期</label><input value={manualForm.date} onChange={(e) => setManualForm((prev) => ({ ...prev, date: e.target.value }))} type="date" className="w-full bg-gray-50 border-none rounded-lg p-1.5 text-[11px] focus:ring-1 ring-[#C8A064] outline-none" /></div>
                                                    <div className="col-span-2 space-y-1"><label className="text-[8px] font-bold text-gray-400 uppercase">需求详情</label><textarea value={manualForm.detail} onChange={(e) => setManualForm((prev) => ({ ...prev, detail: e.target.value }))} rows="3" placeholder="录入需求内容..." className="w-full bg-gray-50 border-none rounded-lg p-2 text-[11px] focus:ring-1 ring-[#C8A064] outline-none resize-none"></textarea></div>
                                                    <div className="col-span-2 grid grid-cols-2 gap-2">
                                                        <button onClick={submitManualNeed} className="py-2 bg-[#1E272E] text-[#C8A064] rounded-lg text-[10px] font-bold uppercase tracking-widest shadow-lg active:scale-95">提交手动需求</button>
                                                        <button onClick={saveManualNeed} className="py-2 bg-[#dc2626] text-white rounded-lg text-[10px] font-bold uppercase tracking-widest shadow-lg active:scale-95">保存</button>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            </section>

                            {/* 缁楊兛绨╅弽蹇ョ窗娑旓箓娼伴弫瀵告倞缁?*/}
                            <section className="flex flex-col h-full animate-in delay-100">
                                <div className="flex items-center gap-2 mb-4"><div className="w-1.5 h-6 bg-[#C8A064]"></div><h3 className="text-sm font-serif font-bold tracking-widest text-[#1E272E]">2) 书面整理稿（智能精炼）</h3></div>
                                <div className="flex-1 bg-white border border-[#C8A064]/20 rounded-2xl p-8 shadow-sm flex flex-col">
                                    <div className="flex-1 overflow-y-auto text-sm leading-loose text-[#2D3436] font-serif">
                                        {processState.written ? <p className="opacity-80 whitespace-pre-wrap">{processState.written}</p> : <div className="h-full flex flex-col items-center justify-center opacity-30 gap-4"><Icon name="wand-2" size={40} className="text-[#C8A064]" /><p className="text-[11px] uppercase font-bold tracking-widest">等待 AI 整理转换</p></div>}
                                    </div>
                                    <button onClick={runPolish} className="mt-6 w-full py-3 bg-[#FDF8E9] text-[#8B6E3F] text-[11px] font-bold border border-[#C8A064]/30 rounded-xl hover:bg-[#C8A064] hover:text-white transition-all uppercase tracking-widest shadow-sm active:scale-95">启动 AI 整理转换</button>
                                </div>
                            </section>

                            {/* 缁楊兛绗侀弽蹇ョ窗閽€钘夋勾缁绢亣顩?*/}
                            <section className="flex flex-col h-full animate-in delay-200">
                                <div className="flex items-center justify-between mb-4">
                                    <div className="flex items-center gap-2"><div className="w-1.5 h-5 bg-[#8B6E3F]"></div><h3 className="text-sm font-serif font-bold tracking-widest text-[#1E272E]">3) 落地纪要（执行看板）</h3></div>
                                    <div className="relative group">
                                        <div className="flex items-center gap-2 bg-[#FDF8E9] px-2 py-1 rounded border border-[#C8A064]/20 cursor-pointer text-[10px] font-bold text-[#8B6E3F]">{TEMPLATES.find(t => t.id === selectedTemplate)?.name} <Icon name="chevron-down" size={12} /></div>
                                        <div className="absolute right-0 top-full mt-2 w-60 bg-white border border-gray-100 rounded-xl shadow-2xl opacity-0 scale-95 pointer-events-none group-hover:opacity-100 group-hover:scale-100 transition-all z-20">
                                            {TEMPLATES.map(t => (
                                                <div key={t.id} onClick={() => setSelectedTemplate(t.id)} className="px-4 py-3 cursor-pointer hover:bg-[#FDF8E9] flex gap-3 transition-colors"><Icon name={t.icon} size={14} className="mt-0.5 text-gray-400" /><div><p className="text-xs font-bold">{t.name}</p><p className="text-[9px] text-gray-400 mt-0.5 leading-tight">{t.desc}</p></div></div>
                                            ))}
                                        </div>
                                    </div>
                                </div>
                                <div className="flex-1 bg-[#1E272E] rounded-2xl p-8 shadow-2xl flex flex-col border border-white/5 relative">
                                    <div className="flex-1 overflow-y-auto font-mono text-xs leading-loose text-white/70">
                                        {processState.minutes ? <div className="space-y-5 animate-in"><div className="p-4 bg-white/5 border-l-2 border-[#C8A064] rounded-lg"><p className="text-[#C8A064] mb-3 font-bold italic tracking-widest border-b border-white/5 pb-2">● PCG 执行清单</p><pre className="whitespace-pre-wrap font-mono text-xs leading-loose text-white/80">{processState.minutes}</pre></div></div> : <div className="h-full flex flex-col items-center justify-center opacity-10 text-white gap-4"><Icon name="clipboard-check" size={50} /><p className="text-[11px] font-bold uppercase tracking-widest">待生成结构化资产</p></div>}
                                    </div>
                                    <button onClick={runMinutes} disabled={!processState.written} className="mt-6 w-full py-3 rounded-xl text-[11px] font-bold uppercase tracking-widest flex items-center justify-center gap-2 bg-[#C8A064] text-[#1E272E] hover:brightness-110 shadow-lg active:scale-95 disabled:opacity-20 transition-all"><Icon name="rocket" size={14} /> 导出为结构化纪要</button>
                                </div>
                            </section>
                        </div>
                    </div>
                );

                const toggleTreeNode = (nodeId) => {
                    setExpandedNodes((prev) => ({ ...prev, [nodeId]: !prev[nodeId] }));
                };

                const renderTreeNodes = (nodes, depth = 0) => (nodes || []).map((node) => {
                    const hasChildren = !!(node.children && node.children.length);
                    const expanded = !!expandedNodes[node.id];
                    const rowPad = 8 + depth * 20;

                    if (node.type === "file") {
                        const selected = selectedFile === `${node.bucket}/${node.key}`;
                        return (
                            <div key={node.id} className="relative">
                                {depth > 0 && (
                                    <span
                                        className="pointer-events-none absolute top-0 bottom-0 border-l border-[#e6e6e6]"
                                        style={{ left: `${rowPad - 10}px` }}
                                    />
                                )}
                                <div
                                    onClick={() => handleSelectObject(node.bucket, node.key)}
                                    className={`relative flex h-9 items-center gap-2 pr-2 rounded-md cursor-pointer select-none ${selected ? 'bg-[#edf3ff] text-[#1f2937]' : 'text-[#374151] hover:bg-[#f5f5f5]'}`}
                                    style={{ paddingLeft: `${rowPad + 18}px` }}
                                >
                                    <Icon name="file-text" size={16} className="text-[#6b7280]" />
                                    <span className="truncate text-[15px]">{node.name}</span>
                                </div>
                            </div>
                        );
                    }

                    return (
                        <div key={node.id} className="relative">
                            {depth > 0 && (
                                <span
                                    className="pointer-events-none absolute top-0 bottom-0 border-l border-[#e6e6e6]"
                                    style={{ left: `${rowPad - 10}px` }}
                                />
                            )}
                            <div
                                onClick={() => hasChildren ? toggleTreeNode(node.id) : undefined}
                                className={`relative flex h-9 items-center gap-2 pr-2 rounded-md select-none text-[#1f2937] ${hasChildren ? "cursor-pointer hover:bg-[#f5f5f5]" : ""}`}
                                style={{ paddingLeft: `${rowPad}px` }}
                            >
                                {hasChildren ? (
                                    <Icon name={expanded ? "chevron-down" : "chevron-right"} size={14} className="text-[#8b8b8b]" />
                                ) : (
                                    <span className="w-[14px]" />
                                )}
                                <Icon name={expanded ? "folder-open" : "folder"} size={18} className="text-[#d4a72c]" />
                                <span className="truncate text-[15px]">{node.name}</span>
                            </div>
                            {hasChildren && expanded && (
                                <div>
                                    {renderTreeNodes(node.children, depth + 1)}
                                </div>
                            )}
                        </div>
                    );
                });

                // --- 濡€虫健娴滃矉绱伴棁鈧Ч鍌氬瀻閺?---
                const AnalysisModule = () => (
                    <div className="flex-1 flex overflow-hidden animate-in">
                        <div className="w-[340px] bg-[#f3f3f3] border-r border-[#d0d0d0] flex flex-col shrink-0">
                            <div className="px-4 py-3 border-b border-[#d0d0d0] flex justify-between items-center bg-[#efefef]">
                                <span className="text-[13px] font-semibold text-[#4b5563]">Documents</span>
                                <button onClick={refreshTree} className="h-6 w-6 inline-flex items-center justify-center rounded hover:bg-[#e2e2e2]">
                                    <Icon name="refresh-cw" size={14} className="text-[#6b7280]" />
                                </button>
                            </div>
                            <div className="flex-1 overflow-y-auto p-2 bg-white">
                                {renderTreeNodes(fileTreeData, 0)}
                            </div>
                        </div>
                        <div className="flex-1 bg-white flex flex-col min-w-[300px] border-r border-[#D1D1C7] relative shadow-inner">
                            <div className="h-12 border-b border-[#D1D1C7] flex items-center px-6 justify-between bg-white/50 backdrop-blur-sm shrink-0">
                                <div className="flex items-center gap-2"><Icon name="file-text" size={16} className="text-[#C8A064]" /><span className="text-sm font-serif font-bold text-[#1E272E]">{selectedFile || "未选择文件"}</span></div>
                                <div className="flex gap-4"><button className="text-[10px] text-gray-400 font-bold uppercase hover:text-[#1E272E] transition-colors"><Icon name="copy" size={12} className="inline mr-1" /> Copy</button><button className="text-[10px] text-gray-400 font-bold uppercase hover:text-[#1E272E] transition-colors"><Icon name="maximize-2" size={12} className="inline mr-1" /> Fullscreen</button></div>
                            </div>
                            <div className="flex-1 overflow-y-auto p-10 font-serif leading-relaxed bg-[url('https://www.transparenttextures.com/patterns/natural-paper.png')]">
                                <div className="max-w-2xl mx-auto space-y-8 animate-in text-[#1E272E]">
                                    <h2 className="text-2xl font-bold border-b-2 border-[#C8A064]/20 pb-4 tracking-tight">PCG 策划方案深度细化分析</h2>
                                    <div className="space-y-4 text-sm opacity-80 leading-loose"><h3 className="font-bold text-[#8B6E3F] text-lg border-l-4 border-[#C8A064] pl-3 italic">战略目标执行逻辑</h3><pre className="whitespace-pre-wrap font-serif text-sm leading-loose">{selectedFileContent}</pre></div>
                                </div>
                            </div>
                        </div>
                        <div className="w-[420px] bg-[#F4F4F2] flex flex-col shrink-0 border-l border-[#D1D1C7] shadow-2xl relative z-10">
                            <div className="h-12 border-b border-[#D1D1C7] bg-[#1E272E] text-white flex items-center px-4 justify-between shrink-0">
                                <div className="flex items-center gap-2"><Icon name="sparkles" size={16} className="text-[#C8A064]" /><span className="text-xs font-bold uppercase tracking-widest">Intelligence Agent</span></div>
                                <button onClick={() => setIsPromptPanelOpen(!isPromptPanelOpen)} className={`p-1.5 rounded transition-all ${isPromptPanelOpen ? 'bg-[#C8A064] text-[#1E272E]' : 'text-white/50'}`}><Icon name="book-open" size={16} /></button>
                            </div>
                            <div className="flex-1 p-6 space-y-6 overflow-y-auto bg-[url('https://www.transparenttextures.com/patterns/cubes.png')] bg-fixed">
                                {chatMessages.map((m, idx) => (
                                    <div key={idx} className="flex gap-3 animate-in">
                                        <div className={`w-8 h-8 rounded-full flex items-center justify-center shadow-lg font-bold text-xs ${m.role === 'user' ? 'bg-[#1E272E] text-[#C8A064]' : 'bg-[#C8A064] text-[#1E272E]'}`}>{m.role === 'user' ? 'U' : 'P'}</div>
                                        <div className="bg-white p-4 rounded-2xl rounded-tl-none text-sm text-[#2D3436] shadow-sm border border-gray-100 leading-relaxed whitespace-pre-wrap">{m.content}</div>
                                    </div>
                                ))}
                            </div>
                            <div className="p-4 bg-white border-t border-[#D1D1C7] shrink-0">
                                <div className="relative group"><textarea value={chatInput} onChange={(e) => setChatInput(e.target.value)} placeholder="输入细化指令..." className="w-full bg-gray-50 border-none rounded-2xl p-4 pr-12 text-sm focus:ring-1 ring-[#C8A064] outline-none min-h-[100px] resize-none transition-all"></textarea><button onClick={sendChat} className="absolute right-3 bottom-3 p-2 bg-[#1E272E] text-[#C8A064] rounded-full shadow-lg"><Icon name="send" size={16} /></button></div>
                            </div>
                        </div>
                        <div className={`bg-white border-l border-[#D1D1C7] transition-all duration-500 flex flex-col overflow-hidden ${isPromptPanelOpen ? 'w-64' : 'w-0'}`}>
                            <div className="w-64 flex flex-col h-full shrink-0">
                                <div className="h-12 border-b border-[#D1D1C7] flex items-center px-4 justify-between bg-gray-50 shrink-0"><span className="text-xs font-bold text-gray-500 tracking-widest uppercase italic border-l-2 border-[#C8A064] pl-2">SOP Library</span><Icon name="x" size={16} className="text-gray-400 cursor-pointer hover:text-red-500" onClick={() => setIsPromptPanelOpen(false)} /></div>
                                <div className="flex-1 overflow-y-auto p-4 space-y-4">
                                    {PROMPT_LIBRARY.map(p => (<div key={p.id} onClick={() => setChatInput(p.content)} className="group border border-gray-100 p-4 rounded-xl hover:bg-[#FDF8E9]/50 cursor-pointer transition-all shadow-sm"><span className="text-[9px] font-bold text-[#C8A064] uppercase">{p.category}</span><h5 className="text-xs font-bold text-[#1E272E] mt-1">{p.title}</h5><p className="text-[10px] text-gray-400 italic line-clamp-3 leading-relaxed">"{p.content}"</p></div>))}
                                </div>
                            </div>
                        </div>
                    </div>
                );

                if (authChecking) {
                    return (
                        <div className="h-screen w-full flex items-center justify-center bg-[#F4F4F2]">
                            <div className="text-sm text-[#1E272E] font-serif tracking-widest animate-pulse">正在验证登录…</div>
                        </div>
                    );
                }
                if (!currentUser) {
                    return (
                        <div className="h-screen w-full flex items-center justify-center bg-[#1E272E] p-6">
                            <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl p-8 border border-[#C8A064]/30">
                                <div className="flex items-center gap-3 mb-6">
                                    <div className="w-10 h-10 bg-[#C8A064] rounded-md flex items-center justify-center font-bold text-[#1E272E]">P</div>
                                    <div>
                                        <h1 className="text-lg font-serif font-bold text-[#1E272E]">PCG 平台登录</h1>
                                        <p className="text-[10px] text-gray-500 mt-0.5">初始管理员由服务端环境变量配置</p>
                                    </div>
                                </div>
                                <div className="flex gap-2 mb-4">
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setAuthScreen("login");
                                            setAuthError("");
                                            setAuthNotice("");
                                        }}
                                        className={`flex-1 py-2 rounded-lg text-xs font-bold ${authScreen === "login" ? "bg-[#1E272E] text-[#C8A064]" : "bg-gray-100 text-gray-500"}`}
                                    >
                                        登录
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setAuthScreen("register");
                                            setAuthError("");
                                            setAuthNotice("");
                                        }}
                                        className={`flex-1 py-2 rounded-lg text-xs font-bold ${authScreen === "register" ? "bg-[#1E272E] text-[#C8A064]" : "bg-gray-100 text-gray-500"}`}
                                    >
                                        注册
                                    </button>
                                </div>
                                {authNotice ? <p className="text-xs text-green-600 mb-3 font-medium">{authNotice}</p> : null}
                                {authError ? <p className="text-xs text-red-600 mb-3 font-medium">{authError}</p> : null}
                                <div className="space-y-3">
                                    <div>
                                        <label className="text-[10px] font-bold text-gray-400 uppercase">账号</label>
                                        <input
                                            value={authForm.username}
                                            onChange={(e) => setAuthForm((p) => ({ ...p, username: e.target.value }))}
                                            className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-[#C8A064]"
                                            placeholder="用户名"
                                            autoComplete="username"
                                        />
                                    </div>
                                    <div>
                                        <label className="text-[10px] font-bold text-gray-400 uppercase">密码</label>
                                        <input
                                            type="password"
                                            value={authForm.password}
                                            onChange={(e) => setAuthForm((p) => ({ ...p, password: e.target.value }))}
                                            className="mt-1 w-full border border-gray-200 rounded-lg px-3 py-2 text-sm outline-none focus:border-[#C8A064]"
                                            placeholder={authScreen === "register" ? "至少 6 位" : "密码"}
                                            autoComplete={authScreen === "register" ? "new-password" : "current-password"}
                                        />
                                    </div>
                                    {authScreen === "login" ? (
                                        <button
                                            type="button"
                                            onClick={() => void login()}
                                            className="w-full py-2.5 mt-2 rounded-lg bg-[#C8A064] text-[#1E272E] text-sm font-bold hover:brightness-110"
                                        >
                                            进入系统
                                        </button>
                                    ) : (
                                        <button
                                            type="button"
                                            onClick={() => void register()}
                                            className="w-full py-2.5 mt-2 rounded-lg bg-[#C8A064] text-[#1E272E] text-sm font-bold hover:brightness-110"
                                        >
                                            注册普通账号
                                        </button>
                                    )}
                                </div>
                                <p className="text-[10px] text-gray-400 mt-6 leading-relaxed">
                                    公开注册仅创建普通用户。管理员须由已有管理员在「用户管理」中指定。
                                </p>
                            </div>
                        </div>
                    );
                }

                return (
                    <div className="flex h-screen w-full overflow-hidden bg-[#F4F4F2]">
                        {/* 娓氀嗙珶鐎佃壈鍩?- PCG 鐎规艾鍩?*/}
                        <nav className={`bg-[#1E272E] text-white flex flex-col transition-all duration-500 ease-in-out relative ${sidebarCollapsed ? 'w-16' : 'w-64'} shrink-0 z-30 shadow-2xl`}>
                            <div className={`p-6 flex items-center border-b border-white/10 h-24 ${sidebarCollapsed ? 'justify-center px-0' : 'justify-between'}`}>
                                <div className="flex items-center gap-3">
                                    <div className="w-9 h-9 bg-[#C8A064] rounded-sm flex items-center justify-center shadow-lg shrink-0"><span className="text-[#1E272E] font-bold text-lg leading-none">P</span></div>
                                    {!sidebarCollapsed && <div className="flex flex-col animate-in"><span className="font-serif italic text-lg tracking-widest font-bold text-[#E5E5E5] leading-none uppercase">PCG</span><span className="text-[10px] font-medium text-[#C8A064] tracking-[0.2em] mt-1 whitespace-nowrap font-serif">朴睿铂尔营销数字化平台</span></div>}
                                </div>
                                <button onClick={() => setSidebarCollapsed(!sidebarCollapsed)} className={`p-1.5 rounded-lg bg-white/5 text-[#C8A064] hover:bg-white/10 transition-colors ${sidebarCollapsed ? 'absolute -right-3 top-20 bg-[#1E272E] border border-white/10 shadow-xl' : ''}`}>{sidebarCollapsed ? <Icon name="chevron-last" size={18} /> : <Icon name="chevron-first" size={18} />}</button>
                            </div>
                            <div className="flex-1 py-2 overflow-y-auto scrollbar-hide">
                                {STAGES.filter((stage) => stage.id !== "users" || currentUser.role === "admin").map((stage) => (
                                    <div key={stage.id} onClick={() => setActiveModule(stage.id)} className={`flex items-center gap-4 py-4 cursor-pointer hover:bg-white/5 transition-all group relative ${sidebarCollapsed ? 'justify-center' : 'px-6'} ${activeModule === stage.id ? 'bg-white/10 border-r-4 border-[#C8A064] text-white font-bold' : 'text-white/40 hover:text-white/70'}`}><div className={`${activeModule === stage.id ? 'text-[#C8A064]' : ''} group-hover:scale-110 transition-transform`}><Icon name={stage.icon} size={20} /></div>{!sidebarCollapsed && <span className="text-sm tracking-wide">{stage.name}</span>}{sidebarCollapsed && <div className="absolute left-full ml-4 px-2 py-1 bg-[#1E272E] text-[#C8A064] text-[10px] rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap shadow-xl border border-white/10 z-50 font-bold">{stage.name}</div>}</div>
                                ))}
                            </div>
                            <div className={`p-6 border-t border-white/10 opacity-40 hover:opacity-100 transition-all cursor-pointer flex items-center gap-4 ${sidebarCollapsed ? 'justify-center px-0' : ''}`}><Icon name="settings" size={18} />{!sidebarCollapsed && <span className="text-xs uppercase tracking-tighter">系统控制中心</span>}</div>
                        </nav>
                        
                        <main className="flex-1 flex flex-col relative overflow-hidden shadow-inner h-screen">
                            <header className="h-16 bg-white/90 backdrop-blur-md border-b border-[#D1D1C7] flex flex-wrap items-center gap-x-6 gap-y-2 justify-between px-8 z-20 shrink-0">
                                <div className="flex items-center gap-6 min-w-0 flex-1">
                                    <div className="flex items-center gap-4 text-[#1E272E] font-bold min-w-0">
                                        <h1 className="text-lg font-serif tracking-tight truncate">
                                            {STAGES.find((s) => s.id === activeModule)?.name}{" "}
                                            <span className="text-[#C8A064] ml-2 text-[10px] font-normal tracking-[0.3em] uppercase opacity-50 italic">
                                                Operational Strategy Unit
                                            </span>
                                        </h1>
                                    </div>
                                    <div className="flex items-center gap-3 shrink-0 text-[11px] text-[#1E272E] border-l border-gray-200 pl-4">
                                        <span className="font-semibold max-w-[100px] truncate">{currentUser.username}</span>
                                        <span className="text-gray-400 hidden sm:inline">
                                            {currentUser.role === "admin" ? "管理员" : "普通用户"}
                                        </span>
                                        <button type="button" onClick={logout} className="text-red-500 hover:underline font-bold px-1">
                                            退出
                                        </button>
                                    </div>
                                </div>
                                <div className="flex items-center gap-4 shrink-0">
                                    <div className="flex items-center gap-2 text-[10px]">
                                        <input
                                            value={llmConfig.base_url}
                                            onChange={(e) => setLlmConfig((prev) => ({ ...prev, base_url: e.target.value }))}
                                            placeholder="LLM URL"
                                            className="w-[220px] h-8 rounded-md border border-[#D1D1C7] px-2 text-[10px] text-[#1E272E] outline-none focus:border-[#C8A064]"
                                        />
                                        <input
                                            value={llmConfig.model}
                                            onChange={(e) => setLlmConfig((prev) => ({ ...prev, model: e.target.value }))}
                                            placeholder="Model"
                                            className="w-[130px] h-8 rounded-md border border-[#D1D1C7] px-2 text-[10px] text-[#1E272E] outline-none focus:border-[#C8A064]"
                                        />
                                        <input
                                            type="password"
                                            value={llmConfig.api_key}
                                            onChange={(e) => setLlmConfig((prev) => ({ ...prev, api_key: e.target.value }))}
                                            placeholder="Secret Key"
                                            className="w-[160px] h-8 rounded-md border border-[#D1D1C7] px-2 text-[10px] text-[#1E272E] outline-none focus:border-[#C8A064]"
                                        />
                                        <button
                                            onClick={saveLlmConfig}
                                            className="h-8 px-3 rounded-md bg-[#C8A064] text-white text-[10px] font-bold hover:brightness-110 transition-all"
                                        >
                                            保存配置
                                        </button>
                                    </div>
                                    <div className="flex items-center gap-6 text-[10px] font-mono text-gray-400 uppercase">
                                        <span className="flex items-center gap-1.5"><span className="w-1.5 h-1.5 bg-green-500 rounded-full animate-pulse"></span> {statusText}</span>
                                        <div className="h-4 w-px bg-gray-200"></div>
                                        <span className="italic">PCG Engine v4.0</span>
                                    </div>
                                </div>
                            </header>
                            
                            <div className="flex-1 flex overflow-hidden">
                                {activeModule === "capture" && CaptureModule()}
                                {activeModule === "analysis" && AnalysisModule()}
                                {activeModule === "users" && currentUser.role === "admin" && UsersAdminModule()}
                                {activeModule === "users" && currentUser.role !== "admin" && (
                                    <div className="flex-1 flex items-center justify-center text-gray-500 text-sm bg-[#F4F4F2]">无权访问用户管理</div>
                                )}
                            </div>

                            <footer className="h-10 bg-[#E8E8E1] border-t border-[#D1D1C7] flex items-center px-8 justify-between text-[10px] text-gray-400 font-mono shrink-0">
                                <div className="flex gap-8 items-center"><div className="flex items-center gap-2"><Icon name="hard-drive" size={12} /> STORAGE: {currentBucket || "PCG_VAULT_S1"}</div><div className="flex items-center gap-2 font-bold text-[#C8A064]/60">PREMIERE CONSULTING GROUP</div></div>
                                <div className="uppercase tracking-widest opacity-60 font-bold underline decoration-[#C8A064]/30 italic font-serif">A Multi-Agent Intelligent Platform</div>
                            </footer>
                        </main>
                    </div>
                );
            };
            const root = ReactDOM.createRoot(document.getElementById('root')!);
root.render(<App />);



