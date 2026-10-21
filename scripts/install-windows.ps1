param([string]$InstallDir = "$env:LOCALAPPDATA\Programs\SkillPilot")
$ErrorActionPreference = 'Stop'
$sourceRoot = [IO.Path]::GetFullPath((Split-Path $PSScriptRoot -Parent))
$targetRoot = [IO.Path]::GetFullPath($InstallDir)
$python = (Get-Command python.exe -ErrorAction Stop).Source
& $python -X utf8 -c 'import sys; assert sys.version_info >= (3,12), "Python 3.12 or newer is required"'
if ($LASTEXITCODE) { throw 'Python 3.12 or newer is required.' }
if (-not (Test-Path -LiteralPath (Join-Path $sourceRoot '.skill-pilot-windows.json'))) {
    throw '请使用包含 Windows 适配清单的完整安装包。'
}
if ($sourceRoot -ne $targetRoot) {
    New-Item -ItemType Directory -Path $targetRoot -Force | Out-Null
    foreach ($name in @('skill_pilot','skill','docs','assets','scripts','tests','.gitignore','skill-pilot','.skill-pilot-windows.json','.skill-pilot-install.json')) {
        $item = Join-Path $sourceRoot $name
        if (Test-Path -LiteralPath $item) { Copy-Item -LiteralPath $item -Destination $targetRoot -Recurse -Force }
    }
    Get-ChildItem -LiteralPath $sourceRoot -Filter '*.md' -File | Copy-Item -Destination $targetRoot -Force
}
& $python -X utf8 -B (Join-Path $targetRoot 'scripts/install.py')
if ($LASTEXITCODE) { throw 'Windows 入口安装失败。' }
Write-Output "Installed: $targetRoot"
