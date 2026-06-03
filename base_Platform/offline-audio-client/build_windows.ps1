#Requires -Version 5.1
<#
.SYNOPSIS
  在 Windows 11 上构建可分发目录（onedir），无需在服务器上连接麦克风。

.DESCRIPTION
  - 使用当前目录下的 Python（建议 3.10+ 64 位）
  - 生成 dist\PCGOfflineAudio\，将整个文件夹复制到目标机，运行 PCGOfflineAudio.exe
  - 录音数据写入 exe 同目录下的 data\
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 python，请先安装 Python 3.10+（64 位）并勾选 Add to PATH。"
}

python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-build.txt

python -m PyInstaller --clean --noconfirm offline_audio_client.spec

Write-Host ""
Write-Host "构建完成: $PSScriptRoot\dist\PCGOfflineAudio\"
Write-Host "请将 dist\PCGOfflineAudio 整个文件夹复制到 Windows 11 电脑，双击 PCGOfflineAudio.exe。"
Write-Host "首次运行若被 SmartScreen 拦截，请选择「仍要运行」或使用企业签名。"
