# Original isolated Ollama launcher. No system service or startup entry is installed.
$ErrorActionPreference = 'Stop'
$taskRoot = 'D:\codex-runtime\industrial-diagnosis'
$taskExe = Join-Path $taskRoot 'ollama-0.34.2\ollama.exe'
if (-not (Test-Path -LiteralPath $taskExe)) { throw '未找到项目 Ollama 运行时' }
$taskListener = Get-NetTCPConnection -LocalPort 11435 -State Listen -ErrorAction SilentlyContinue
if ($taskListener) {
    $taskExisting = Get-Process -Id $taskListener[0].OwningProcess
    if ($taskExisting.Path -ne $taskExe) { throw '11435 端口由其他程序占用，不会停止它' }
    Invoke-RestMethod 'http://127.0.0.1:11435/api/version' -TimeoutSec 3
    Write-Output '项目模型服务已在运行'
    exit 0
}
$env:OLLAMA_HOST = '127.0.0.1:11435'
$env:OLLAMA_MODELS = Join-Path $taskRoot 'models'
$env:OLLAMA_NO_CLOUD = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_KEEP_ALIVE = '2m'
$taskLogs = Join-Path $taskRoot '.tmp'
$taskStamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$taskProcess = Start-Process -FilePath $taskExe -ArgumentList 'serve' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $taskLogs "serve-$taskStamp.out.log") -RedirectStandardError (Join-Path $taskLogs "serve-$taskStamp.err.log")
@{pid=$taskProcess.Id; executable=$taskExe; port=11435; started=$taskStamp} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $taskRoot '.tmp\service.json') -Encoding utf8
Write-Output ("Started project Ollama PID=" + $taskProcess.Id + ' on 127.0.0.1:11435')
