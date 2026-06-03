# Offline Audio Client (Windows/Linux)

## MVP capabilities
- Record audio offline to local `.wav` files
- Persist metadata in `data/manifest.json`
- Login to server with username/password
- Upload pending/failed recordings when network is available

## Windows 11 可执行包（推荐在有麦克风的电脑上构建与使用）

服务器或 CI 环境通常没有麦克风；请在 **Windows 11 本机**（或带麦克风的 Windows 机器）上打包并运行。

1. 安装 [Python 3.10+ 64 位](https://www.python.org/downloads/windows/)，安装时勾选 **Add python.exe to PATH**。
2. 打开 **PowerShell**，进入本目录后执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned -Force   # 若脚本被禁止，仅需一次
.\build_windows.ps1
```

3. 构建产物目录：`dist\PCGOfflineAudio\`。将整个 **`PCGOfflineAudio` 文件夹** 复制到目标 Windows 11 电脑，双击 **`PCGOfflineAudio.exe`**。
4. 程序会在 exe **同目录** 下创建 `data\`（清单、录音、登录 token），便于备份与升级时保留数据。
5. 若出现 **Windows 已保护你的电脑**：未签名 exe 属正常情况，点「更多信息」→「仍要运行」；生产环境建议使用代码签名证书。

默认连接地址在程序内写死为 `https://111.228.12.207:5174`。

### 交给客户的 ZIP（在 Windows 上生成）

含 **exe + 说明** 的压缩包只能在 **Windows** 上通过 PyInstaller 生成（Linux/CI 无法产出可在客户机运行的 Windows exe）。

1. 在本机安装 Python 3.10+（64 位）后，进入 `offline-audio-client` 目录。
2. 双击 **`一键打包给客户.bat`**，或在 PowerShell 中执行：  
   `.\package_customer_zip.ps1`
3. 生成文件路径：**`releases\PCGOfflineAudio-Windows11-客户版-时间戳.zip`**
4. 将该 ZIP 发给客户；客户解压后阅读 **`00-请先阅读.txt`**，双击 **`PCGOfflineAudio.exe`** 即可（**无需安装 Python**）。

说明正文源文件位于 **`delivery\`**，打包时会自动复制进 ZIP。

## UI 2.0（对齐 Web 端）

- 左侧采用深色导航栏，菜单样式与 Web 端一致；当前仅 `离线音频采集` 为可用页面，其它菜单为占位。
- 右侧保留全部原有功能：联网登录、录音控制、本地清单、手动上传、状态提示。
- `开始录音` 入口改为工具栏麦克风图标按钮（`🎤 开始录音`），录音后切换为红色 `● 录音中` 状态。
- 顶部显示网络与登录状态，底部显示操作结果，保持桌面端操作可见性。

## Run
```bash
cd offline-audio-client
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Windows PowerShell:
```powershell
cd offline-audio-client
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

## Data files
- `data/recordings/YYYY-MM-DD/*.wav`
- `data/manifest.json`
- `data/client_config.json`（保存 token 与用户名）
