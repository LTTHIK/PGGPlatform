Param(
    [string]$PythonExe = "py -3.10"
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "[1/5] 在 minimal_craft/.venv 创建虚拟环境"
if (Test-Path .venv) {
    Write-Host "      检测到 .venv，直接复用"
} else {
    & cmd /c "$PythonExe -m venv .venv --system-site-packages"
}

$py = Join-Path $root ".venv\Scripts\python.exe"

Write-Host "[2/5] 升级 pip/setuptools/wheel"
& $py -m pip install --upgrade pip setuptools wheel --no-cache-dir

Write-Host "[3/5] 准备本地 wenet 安装镜像"
$pkgDir = Join-Path $root "_wenet_pkg"
New-Item -ItemType Directory -Force -Path $pkgDir | Out-Null
Copy-Item "..\wenet-main\setup.py" "$pkgDir\setup.py" -Force
Copy-Item "..\wenet-main\setup.cfg" "$pkgDir\setup.cfg" -Force
Copy-Item "..\wenet-main\requirements.txt" "$pkgDir\requirements.txt" -Force
Copy-Item "..\wenet-main\wenet" "$pkgDir\wenet" -Recurse -Force

Write-Host "[4/5] 在本地虚拟环境安装 wenet + whisper"
& $py -m pip install --no-cache-dir "$pkgDir"
& $py -m pip install --no-cache-dir --no-deps --ignore-installed openai-whisper==20250625
& $py -m pip install --no-cache-dir boto3

Write-Host "[5/5] 执行环境自检"
& $py check_prereqs.py --model-dir .\paraformer_model

Write-Host "安装完成。"
Write-Host "运行实时转写命令："
Write-Host "  .\.venv\Scripts\python minimal_streaming.py --model-dir .\paraformer_model"
