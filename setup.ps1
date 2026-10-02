# Original project dependency setup; installs only pyserial into this project.
$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { throw '未找到运行时 Python' }
& $taskPython -m pip install --disable-pip-version-check --no-deps --target (Join-Path $PSScriptRoot '.runtime') 'pyserial==3.5'
if ($LASTEXITCODE -ne 0) { throw 'pyserial 安装失败' }
