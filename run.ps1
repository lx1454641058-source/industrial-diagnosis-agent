# Original project launcher. Uses bundled Python; no account credentials required.
param(
    [ValidateSet('demo','serial')][string]$Mode = 'demo',
    [ValidateSet('baseline','ollama')][string]$Provider = 'baseline',
    [string]$Model = '',
    [string]$ModelUrl = 'http://127.0.0.1:11434',
    [string]$Profile = '',
    [string]$ReferenceProfile = '',
    [int]$Port = 8766,
    [switch]$Open
)
$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw '未找到运行时 Python，请安装 Python 后使用 README 中的手动命令。' }
$env:PYTHONIOENCODING = 'utf-8'
$taskLibraries = Join-Path $PSScriptRoot '.runtime'
if (Test-Path -LiteralPath $taskLibraries) { $env:PYTHONPATH = $taskLibraries }
$taskArguments = @('-m','diagnosis.server','--mode',$Mode,'--provider',$Provider,'--port',"$Port")
if ($Model) { $taskArguments += @('--model',$Model) }
$taskArguments += @('--model-url',$ModelUrl)
if ($Profile) { $taskArguments += @('--profile',$Profile) }
if ($ReferenceProfile) { $taskArguments += @('--reference-profile',$ReferenceProfile) }
Push-Location $PSScriptRoot
try {
    if ($Open) { Start-Process "http://127.0.0.1:$Port" }
    & $taskPython @taskArguments
} finally { Pop-Location }
