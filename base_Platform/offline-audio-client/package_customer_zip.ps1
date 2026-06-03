#Requires -Version 5.1
<#
.SYNOPSIS
  一键构建 Windows 11 客户版 ZIP（内含可执行程序 + 说明文档）。

.DESCRIPTION
  必须在 Windows 11（或 Windows 10 64 位）上、已安装 Python 3.10+ 的机器上运行。
  输出：releases\PCGOfflineAudio-Windows11-客户版-yyyyMMdd-HHmmss.zip
  将该 ZIP 交给客户解压后即可双击 PCGOfflineAudio.exe 使用（客户机无需 Python）。
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "未找到 python。请先安装 Python 3.10+（64 位）后再运行本脚本。"
}

Write-Host "== 1/3 构建可执行文件 ==" -ForegroundColor Cyan
& "$PSScriptRoot\build_windows.ps1"

$productDir = Join-Path $PSScriptRoot "dist\PCGOfflineAudio"
if (-not (Test-Path (Join-Path $productDir "PCGOfflineAudio.exe"))) {
    Write-Error "未找到 $productDir\PCGOfflineAudio.exe ，构建失败。"
}

$releaseRoot = Join-Path $PSScriptRoot "releases"
New-Item -ItemType Directory -Path $releaseRoot -Force | Out-Null

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$folderName = "PCGOfflineAudio-Windows11-$stamp"
$stageParent = Join-Path $PSScriptRoot "dist\release_stage"
$stageDir = Join-Path $stageParent $folderName

Write-Host "== 2/3 组装客户目录 ==" -ForegroundColor Cyan
if (Test-Path $stageParent) {
    Remove-Item -Path $stageParent -Recurse -Force
}
New-Item -ItemType Directory -Path $stageDir -Force | Out-Null
Copy-Item -Path (Join-Path $productDir "*") -Destination $stageDir -Recurse -Force

$delivery = Join-Path $PSScriptRoot "delivery"
$exeStamped = "PCGOfflineAudio-$stamp.exe"
Rename-Item -Path (Join-Path $stageDir "PCGOfflineAudio.exe") -NewName $exeStamped -Force
Copy-Item (Join-Path $delivery "00-请先阅读.txt") -Destination (Join-Path $stageDir "00-请先阅读-$stamp.txt") -Force
Copy-Item (Join-Path $delivery "客户使用说明.txt") -Destination (Join-Path $stageDir "客户使用说明-$stamp.txt") -Force

# 为客户快速识别版本，额外提供 data 目录时间标记文件（不影响程序读写 data\manifest.json）
Set-Content -Path (Join-Path $stageDir "data\版本时间-$stamp.txt") -Value "本包生成时间：$stamp" -Encoding UTF8

$zipName = "PCGOfflineAudio-Windows11-客户版-$stamp.zip"
$zipPath = Join-Path $releaseRoot $zipName

Write-Host "== 3/3 压缩 ZIP ==" -ForegroundColor Cyan
Compress-Archive -Path $stageDir -DestinationPath $zipPath -CompressionLevel Optimal

Remove-Item -Path $stageParent -Recurse -Force

Write-Host ""
Write-Host "客户交付 ZIP 已生成：" -ForegroundColor Green
Write-Host "  $zipPath"
Write-Host ""
Write-Host "请将上述 ZIP 发给客户。客户操作：解压 → 进入文件夹 → 双击 $exeStamped"
Write-Host "（详见压缩包内「00-请先阅读-$stamp.txt」与「客户使用说明-$stamp.txt」）"
