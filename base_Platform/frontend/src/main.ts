import "./style.css";

type ChatMessage = { role: "system" | "user" | "assistant"; content: string };
type TreeItem = { bucket: string; keys: string[] };

const app = document.querySelector<HTMLDivElement>("#app");
if (!app) throw new Error("Missing #app");

app.innerHTML = `
<main class="layout">
  <header class="top">
    <h1>Realtime ASR + AI 会议加工</h1>
    <div class="top-right">
      <span id="status">空闲</span>
      <span id="level">音量 RMS: 0.0000</span>
      <span id="device">设备: -</span>
    </div>
  </header>

  <nav class="tabs">
    <button id="tab-record" class="tab active">录音与上传</button>
    <button id="tab-process" class="tab">会议内容二次加工</button>
  </nav>

  <section id="panel-record" class="panel active">
    <div class="controls">
      <label>语音阈值 RMS <input id="voice-threshold" value="0.001" /></label>
      <label>静音判停毫秒 <input id="silence-ms" value="800" /></label>
      <label><input id="auto-polish" type="checkbox" checked /> 停止后自动整理书面稿</label>
    </div>
    <div class="buttons">
      <button id="start-btn">开始录音</button>
      <button id="stop-btn" disabled>停止录音</button>
      <button id="polish-btn">口语稿 -> 书面稿</button>
      <button id="minutes-btn">书面稿 -> 会议纪要</button>
      <button id="upload-recording-btn">上传录音</button>
      <button id="upload-raw-btn">上传口语稿</button>
      <button id="upload-formal-btn">上传书面稿</button>
      <button id="upload-minutes-btn">上传会议纪要</button>
      <button id="upload-all-btn">一键上传四项</button>
      <button id="clear-all-btn">清空全部</button>
    </div>
    <div class="text-grid">
      <section>
        <h2>1) 实时原始转写（口语稿）</h2>
        <textarea id="raw-text"></textarea>
      </section>
      <section>
        <h2>2) 书面整理稿（大模型生成）</h2>
        <textarea id="formal-text"></textarea>
      </section>
      <section>
        <h2>3) 会议纪要（大模型生成）</h2>
        <textarea id="minutes-text"></textarea>
      </section>
    </div>
  </section>

  <section id="panel-process" class="panel">
    <div class="process-top">
      <button id="refresh-tree-btn">刷新 MinIO 树</button>
      <span>点击左侧文件后，中间显示内容，右侧可对话加工</span>
    </div>
    <div class="process-grid">
      <section class="box">
        <h2>MinIO 文件树</h2>
        <div id="tree-view" class="tree"></div>
      </section>
      <section class="box">
        <h2 id="file-title">文件浏览</h2>
        <textarea id="file-preview"></textarea>
      </section>
      <section class="box chat-box">
        <div class="chat-tabs">
          <button id="chat-tab-current" class="tab active">正在进行的会话</button>
          <button id="chat-tab-history" class="tab">历史会话</button>
        </div>
        <div id="chat-current-panel" class="chat-panel active">
          <textarea id="chat-current" readonly></textarea>
          <div class="chat-input-row">
            <textarea id="chat-input"></textarea>
            <div class="chat-buttons">
              <button id="send-chat-btn">发送</button>
              <button id="archive-chat-btn">归档会话</button>
              <button id="clear-chat-btn">清空当前</button>
            </div>
          </div>
        </div>
        <div id="chat-history-panel" class="chat-panel">
          <textarea id="chat-history" readonly></textarea>
        </div>
      </section>
    </div>
  </section>
</main>
`;

const statusEl = must<HTMLSpanElement>("#status");
const levelEl = must<HTMLSpanElement>("#level");
const deviceEl = must<HTMLSpanElement>("#device");

const thresholdInput = must<HTMLInputElement>("#voice-threshold");
const silenceInput = must<HTMLInputElement>("#silence-ms");
const autoPolishInput = must<HTMLInputElement>("#auto-polish");

const rawText = must<HTMLTextAreaElement>("#raw-text");
const formalText = must<HTMLTextAreaElement>("#formal-text");
const minutesText = must<HTMLTextAreaElement>("#minutes-text");

const startBtn = must<HTMLButtonElement>("#start-btn");
const stopBtn = must<HTMLButtonElement>("#stop-btn");
const polishBtn = must<HTMLButtonElement>("#polish-btn");
const minutesBtn = must<HTMLButtonElement>("#minutes-btn");
const uploadRecordingBtn = must<HTMLButtonElement>("#upload-recording-btn");
const uploadRawBtn = must<HTMLButtonElement>("#upload-raw-btn");
const uploadFormalBtn = must<HTMLButtonElement>("#upload-formal-btn");
const uploadMinutesBtn = must<HTMLButtonElement>("#upload-minutes-btn");
const uploadAllBtn = must<HTMLButtonElement>("#upload-all-btn");
const clearAllBtn = must<HTMLButtonElement>("#clear-all-btn");

const treeView = must<HTMLDivElement>("#tree-view");
const fileTitle = must<HTMLHeadingElement>("#file-title");
const filePreview = must<HTMLTextAreaElement>("#file-preview");

const chatCurrent = must<HTMLTextAreaElement>("#chat-current");
const chatHistory = must<HTMLTextAreaElement>("#chat-history");
const chatInput = must<HTMLTextAreaElement>("#chat-input");

let ws: WebSocket | null = null;
let mediaStream: MediaStream | null = null;
let audioContext: AudioContext | null = null;
let sourceNode: MediaStreamAudioSourceNode | null = null;
let processorNode: ScriptProcessorNode | null = null;
let isStarted = false;
let currentSessionId = "";
let currentFileDesc = "";
let currentFileText = "";
let chatMessages: ChatMessage[] = [];

function must<T extends HTMLElement>(selector: string): T {
  const node = document.querySelector(selector);
  if (!node) throw new Error(`Missing ${selector}`);
  return node as T;
}

function stamp(): string {
  return new Date().toLocaleTimeString("zh-CN", { hour12: false });
}

function setStatus(text: string): void {
  statusEl.textContent = text;
}

function appendRaw(text: string): void {
  rawText.value += `[${stamp()}] ${text}\n`;
  rawText.scrollTop = rawText.scrollHeight;
}

function appendChat(role: string, text: string): void {
  chatCurrent.value += `[${stamp()}] ${role}:\n${text}\n\n`;
  chatCurrent.scrollTop = chatCurrent.scrollHeight;
}

function arrayBufferToBase64(buffer: ArrayBufferLike): string {
  let binary = "";
  const bytes = new Uint8Array(buffer);
  const len = bytes.byteLength;
  for (let i = 0; i < len; i += 1) binary += String.fromCharCode(bytes[i]);
  return btoa(binary);
}

function floatToPcm16(float32Array: Float32Array): Int16Array {
  const pcm = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i += 1) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    pcm[i] = s < 0 ? Math.round(s * 0x8000) : Math.round(s * 0x7fff);
  }
  return pcm;
}

async function checkHealth(): Promise<void> {
  const resp = await fetch("/api/health");
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.detail ?? `HTTP ${resp.status}`);
  deviceEl.textContent = `设备: ${body.device ?? "-"}`;
}

async function startRecording(): Promise<void> {
  if (isStarted) return;
  setStatus("正在启动");
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${protocol}://${window.location.host}/ws/asr`);

  ws.onmessage = (event) => {
    const message = JSON.parse(event.data) as { type: string; [k: string]: unknown };
    if (message.type === "started") {
      currentSessionId = String(message.session_id ?? "");
      setStatus("正在监听");
      startBtn.disabled = true;
      stopBtn.disabled = false;
    } else if (message.type === "level") {
      levelEl.textContent = `音量 RMS: ${Number(message.rms ?? 0).toFixed(4)}`;
    } else if (message.type === "transcript") {
      appendRaw(String(message.text ?? ""));
    } else if (message.type === "status") {
      setStatus(String(message.text ?? ""));
    } else if (message.type === "stopped") {
      setStatus("已停止");
      stopBtn.disabled = true;
      startBtn.disabled = false;
      ws?.close();
      ws = null;
      if (autoPolishInput.checked) void runPolish();
    } else if (message.type === "error") {
      setStatus(`失败: ${String(message.text ?? "unknown error")}`);
    }
  };

  await waitSocketOpen(ws);
  ws.send(
    JSON.stringify({
      type: "start",
      config: {
        sample_rate: 16000,
        voice_threshold: Number(thresholdInput.value || "0.001"),
        silence_ms: Number(silenceInput.value || "800"),
      },
    }),
  );

  mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
  audioContext = new AudioContext({ sampleRate: 16000 });
  sourceNode = audioContext.createMediaStreamSource(mediaStream);
  processorNode = audioContext.createScriptProcessor(4096, 1, 1);

  processorNode.onaudioprocess = (event: AudioProcessingEvent) => {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const input = event.inputBuffer.getChannelData(0);
    const pcm16 = floatToPcm16(input);
    ws.send(
      JSON.stringify({
        type: "audio",
        pcm16: arrayBufferToBase64(pcm16.buffer),
      }),
    );
  };

  sourceNode.connect(processorNode);
  processorNode.connect(audioContext.destination);
  isStarted = true;
}

async function stopRecording(): Promise<void> {
  if (!isStarted) return;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "stop" }));
  }
  processorNode?.disconnect();
  sourceNode?.disconnect();
  await audioContext?.close();
  mediaStream?.getTracks().forEach((t) => t.stop());

  processorNode = null;
  sourceNode = null;
  audioContext = null;
  mediaStream = null;
  isStarted = false;
}

async function waitSocketOpen(socket: WebSocket): Promise<void> {
  if (socket.readyState === WebSocket.OPEN) return;
  await new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("socket open timeout")), 8000);
    socket.onopen = () => {
      window.clearTimeout(timer);
      resolve();
    };
    socket.onerror = () => {
      window.clearTimeout(timer);
      reject(new Error("socket open failed"));
    };
  });
}

async function runPolish(): Promise<void> {
  if (!rawText.value.trim()) {
    setStatus("失败: 口语稿为空");
    return;
  }
  setStatus("正在调用 DeepSeek 生成书面稿");
  const resp = await fetch("/api/polish", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: rawText.value }),
  });
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.detail ?? `HTTP ${resp.status}`);
  formalText.value = body.text ?? "";
  setStatus("书面稿已生成");
}

async function runMinutes(): Promise<void> {
  if (!formalText.value.trim()) {
    setStatus("失败: 书面稿为空");
    return;
  }
  setStatus("正在调用 DeepSeek 生成会议纪要");
  const resp = await fetch("/api/minutes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: formalText.value }),
  });
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.detail ?? `HTTP ${resp.status}`);
  minutesText.value = body.text ?? "";
  setStatus("会议纪要已生成");
}

async function uploadRecording(): Promise<void> {
  if (!currentSessionId) throw new Error("当前没有可上传录音会话");
  const resp = await fetch("/api/upload/recording", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: currentSessionId }),
  });
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.detail ?? `HTTP ${resp.status}`);
  setStatus(`录音上传成功: ${body.bucket}/${body.key}`);
}

async function uploadText(kind: "raw" | "formal" | "minutes", content: string): Promise<void> {
  const resp = await fetch("/api/upload/text", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, content }),
  });
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.detail ?? `HTTP ${resp.status}`);
  setStatus(`${kind} 上传成功: ${body.bucket}/${body.key}`);
}

async function uploadAll(): Promise<void> {
  const resp = await fetch("/api/upload/all", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: currentSessionId || null,
      raw: rawText.value,
      formal: formalText.value,
      minutes: minutesText.value,
    }),
  });
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.detail ?? `HTTP ${resp.status}`);
  if (body.errors?.length) {
    setStatus(`部分失败: ${body.errors.join("; ")}`);
  } else {
    setStatus("四项上传流程完成");
  }
}

function renderTree(items: TreeItem[]): void {
  treeView.innerHTML = "";
  if (!items.length) {
    treeView.textContent = "没有 bucket";
    return;
  }
  for (const item of items) {
    const block = document.createElement("section");
    block.className = "tree-bucket";
    const title = document.createElement("h3");
    title.textContent = item.bucket;
    block.appendChild(title);

    const list = document.createElement("div");
    list.className = "tree-list";
    for (const key of item.keys) {
      const btn = document.createElement("button");
      btn.className = "tree-key";
      btn.textContent = key;
      btn.addEventListener("click", () => void loadObject(item.bucket, key));
      list.appendChild(btn);
    }
    if (!item.keys.length) list.textContent = "(空)";
    block.appendChild(list);
    treeView.appendChild(block);
  }
}

async function refreshTree(): Promise<void> {
  setStatus("正在刷新 MinIO 树");
  const resp = await fetch("/api/minio/tree");
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.detail ?? `HTTP ${resp.status}`);
  renderTree((body.items ?? []) as TreeItem[]);
  setStatus("MinIO 树已刷新");
}

async function loadObject(bucket: string, key: string): Promise<void> {
  const url = `/api/minio/object?bucket=${encodeURIComponent(bucket)}&key=${encodeURIComponent(key)}`;
  const resp = await fetch(url);
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.detail ?? `HTTP ${resp.status}`);
  const desc = `桶: ${body.bucket} | 键: ${body.key}`;
  fileTitle.textContent = desc;
  filePreview.value = body.preview ?? "";
  currentFileDesc = desc;
  currentFileText = body.preview ?? "";
}

async function sendChat(): Promise<void> {
  const userText = chatInput.value.trim();
  if (!userText) return;
  chatInput.value = "";
  appendChat("用户", userText);

  if (!chatMessages.length) {
    chatMessages.push({
      role: "system",
      content: "你是会议内容加工助手。请基于用户问题与已选文件内容回答，输出尽量结构化、可执行。",
    });
  }
  const context = currentFileText
    ? `\n\n【当前选中文件】\n${currentFileDesc}\n【文件内容】\n${currentFileText.slice(0, 12000)}`
    : "";
  chatMessages.push({ role: "user", content: userText + context });

  const resp = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: chatMessages }),
  });
  const body = await resp.json();
  if (!resp.ok) throw new Error(body.detail ?? `HTTP ${resp.status}`);
  const answer = String(body.text ?? "");
  chatMessages.push({ role: "assistant", content: answer });
  appendChat("助手", answer);
}

function archiveChat(): void {
  if (!chatCurrent.value.trim()) return;
  chatHistory.value += `==== 会话归档 ${new Date().toLocaleString("zh-CN")} ====\n${chatCurrent.value}\n\n`;
  chatCurrent.value = "";
  chatMessages = [];
}

function clearChat(): void {
  chatCurrent.value = "";
  chatMessages = [];
}

function clearAll(): void {
  rawText.value = "";
  formalText.value = "";
  minutesText.value = "";
}

function bindTabs(): void {
  const tabRecord = must<HTMLButtonElement>("#tab-record");
  const tabProcess = must<HTMLButtonElement>("#tab-process");
  const panelRecord = must<HTMLElement>("#panel-record");
  const panelProcess = must<HTMLElement>("#panel-process");

  const chatTabCurrent = must<HTMLButtonElement>("#chat-tab-current");
  const chatTabHistory = must<HTMLButtonElement>("#chat-tab-history");
  const chatCurrentPanel = must<HTMLElement>("#chat-current-panel");
  const chatHistoryPanel = must<HTMLElement>("#chat-history-panel");

  tabRecord.addEventListener("click", () => {
    tabRecord.classList.add("active");
    tabProcess.classList.remove("active");
    panelRecord.classList.add("active");
    panelProcess.classList.remove("active");
  });
  tabProcess.addEventListener("click", () => {
    tabProcess.classList.add("active");
    tabRecord.classList.remove("active");
    panelProcess.classList.add("active");
    panelRecord.classList.remove("active");
  });

  chatTabCurrent.addEventListener("click", () => {
    chatTabCurrent.classList.add("active");
    chatTabHistory.classList.remove("active");
    chatCurrentPanel.classList.add("active");
    chatHistoryPanel.classList.remove("active");
  });
  chatTabHistory.addEventListener("click", () => {
    chatTabHistory.classList.add("active");
    chatTabCurrent.classList.remove("active");
    chatHistoryPanel.classList.add("active");
    chatCurrentPanel.classList.remove("active");
  });
}

function guard(fn: () => Promise<void> | void): () => void {
  return () => {
    Promise.resolve(fn()).catch((err) => {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus(`失败: ${msg}`);
    });
  };
}

bindTabs();
startBtn.addEventListener("click", guard(startRecording));
stopBtn.addEventListener("click", guard(stopRecording));
polishBtn.addEventListener("click", guard(runPolish));
minutesBtn.addEventListener("click", guard(runMinutes));
uploadRecordingBtn.addEventListener("click", guard(uploadRecording));
uploadRawBtn.addEventListener("click", guard(() => uploadText("raw", rawText.value)));
uploadFormalBtn.addEventListener("click", guard(() => uploadText("formal", formalText.value)));
uploadMinutesBtn.addEventListener("click", guard(() => uploadText("minutes", minutesText.value)));
uploadAllBtn.addEventListener("click", guard(uploadAll));
clearAllBtn.addEventListener("click", clearAll);

must<HTMLButtonElement>("#refresh-tree-btn").addEventListener("click", guard(refreshTree));
must<HTMLButtonElement>("#send-chat-btn").addEventListener("click", guard(sendChat));
must<HTMLButtonElement>("#archive-chat-btn").addEventListener("click", archiveChat);
must<HTMLButtonElement>("#clear-chat-btn").addEventListener("click", clearChat);

window.addEventListener("beforeunload", () => {
  void stopRecording();
});

void Promise.all([checkHealth(), refreshTree()]).then(
  () => setStatus("就绪"),
  (err) => {
    const msg = err instanceof Error ? err.message : String(err);
    setStatus(`启动失败: ${msg}`);
  },
);
