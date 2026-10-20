# "Clean PC" test: silent per-user install to a temp folder, run with a bare PATH (no Git/Python/compiler),
# selftest against the local test feed, UI renders, silent uninstall. Data goes to a temp LOCALAPPDATA.
$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$app = Resolve-Path (Join-Path $here '..\app')
$staged = Join-Path $here '..\release-staging\index.local.json' # the release agent's local feed (file: URLs), when it exists
$feed = if (Test-Path $staged) { Resolve-Path $staged } else { Join-Path $app 'testfeed\index.json' }
"feed: $feed"
$t = Join-Path $env:TEMP ("rsim-clean-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
$dir = Join-Path $t 'Reader Simulator'
New-Item -ItemType Directory $t | Out-Null
function Step($name, $ok) { "{0,-34} {1}" -f $name, $(if ($ok) { 'PASS' } else { 'FAIL' }); if (-not $ok) { $script:failed = $true } }
$failed = $false

$p = Start-Process (Join-Path $here 'Output\ReaderSimulator-Setup.exe') -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/CURRENTUSER', '/NORESTART', "/DIR=`"$dir`"", "/LOG=`"$t\setup.log`"" -Wait -PassThru
Step 'silent per-user install' ($p.ExitCode -eq 0 -and (Test-Path "$dir\ReaderSimulator.exe"))
$lnk = Join-Path ([Environment]::GetFolderPath('Programs')) 'Reader Simulator.lnk'
Step 'Start-menu shortcut' (Test-Path $lnk)
Step 'no desktop shortcut by default' (-not (Test-Path (Join-Path ([Environment]::GetFolderPath('Desktop')) 'Reader Simulator.lnk')))
"installed size: {0:N0} bytes" -f ((Get-ChildItem $dir -Recurse -File | Measure-Object Length -Sum).Sum)

$oldPath = $env:PATH; $oldLad = $env:LOCALAPPDATA
$env:PATH = 'C:\Windows\System32;C:\Windows'; $env:LOCALAPPDATA = Join-Path $t 'lad'
try {
  $sw = [Diagnostics.Stopwatch]::StartNew()
  $p = Start-Process "$dir\ReaderSimulator.exe" -ArgumentList '--selftest', '--feed', "`"$feed`"" -Wait -PassThru
  Step "selftest ($([int]$sw.Elapsed.TotalSeconds) s)" ($p.ExitCode -eq 0)
  Get-Content (Join-Path $env:LOCALAPPDATA 'ReaderSimulator\selftest.log') | ForEach-Object { "    $_" }
  foreach ($theme in 'light', 'dark') {
    $png = Join-Path $app "renders\installed-$theme.png"
    $sw.Restart()
    $p = Start-Process "$dir\ReaderSimulator.exe" -ArgumentList '--render-ui', "`"$png`"", '--theme', $theme, '--feed', "`"$feed`"" -Wait -PassThru
    Step "render-ui $theme ($($sw.ElapsedMilliseconds) ms)" ($p.ExitCode -eq 0 -and (Test-Path $png))
  }
  $bmp = Get-ChildItem (Join-Path $env:LOCALAPPDATA 'ReaderSimulator\cards') -Recurse -Filter selftest.bmp | Select-Object -First 1
  if ($bmp) { Add-Type -AssemblyName System.Drawing; $i = [Drawing.Image]::FromFile($bmp.FullName); $i.Save((Join-Path $app 'renders\selftest-simulator-screen.png'), [Drawing.Imaging.ImageFormat]::Png); $i.Dispose() }
} finally { $env:PATH = $oldPath; $env:LOCALAPPDATA = $oldLad }

$p = Start-Process "$dir\unins000.exe" -ArgumentList '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART' -Wait -PassThru
Start-Sleep -Seconds 3 # the uninstaller finishes in a copy of itself
Step 'silent uninstall' ($p.ExitCode -eq 0 -and -not (Test-Path "$dir\ReaderSimulator.exe") -and -not (Test-Path $lnk))
$uninstKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\{6C2B7E7A-3F0D-4C51-9A57-2E6B3C8D9F41}_is1'
Step 'removed from Installed apps' (-not (Test-Path $uninstKey))
Remove-Item -Recurse -Force $t -ErrorAction SilentlyContinue
if ($failed) { 'RESULT: FAIL'; exit 1 } else { 'RESULT: PASS' }
