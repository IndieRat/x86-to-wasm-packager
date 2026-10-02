$root=(Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Import-Module (Join-Path $root "powershell\XWASM.psm1") -Force
xwasm_environment
