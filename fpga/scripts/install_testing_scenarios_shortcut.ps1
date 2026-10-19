$ErrorActionPreference = 'Stop'
$fpgaDirectory = Split-Path $PSScriptRoot -Parent
$desktopDirectory = [Environment]::GetFolderPath('Desktop')
$shellObject = New-Object -ComObject WScript.Shell
$shortcut = $shellObject.CreateShortcut((Join-Path $desktopDirectory 'IGOR - Testing Scenarios.lnk'))
$shortcut.TargetPath = Join-Path $fpgaDirectory 'bitstreams/RUN_TESTING_SCENARIOS.bat'
$shortcut.WorkingDirectory = Split-Path $fpgaDirectory -Parent
$shortcut.Description = 'Run software, RTL and FPGA checks; report unresolved physical robot acceptance'
$shortcut.Save()
Write-Host "Created: $(Join-Path $desktopDirectory 'IGOR - Testing Scenarios.lnk')"
