# Builds the app into app/bin with a per-user .NET SDK in tools/dotnet (next to this repo folder).
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'; $env:DOTNET_NOLOGO = '1'; $env:DOTNET_SKIP_FIRST_TIME_EXPERIENCE = '1'
if (-not (Test-Path (Join-Path $here 'ReaderSimulator.ico'))) { & (Join-Path $here 'make-icon.ps1') }
$bin = Join-Path $here 'bin'
if (Test-Path $bin) { Remove-Item -Recurse -Force $bin }
# the per-user SDK next to the repo when there is one, else the installed one (GitHub Actions)
$dotnet = Join-Path $here '..\tools\dotnet\dotnet.exe'
if (-not (Test-Path $dotnet)) { $dotnet = 'dotnet' }
& $dotnet build (Join-Path $here 'src\ReaderSimulator.csproj') -c Release -o $bin -nologo -v:minimal
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
