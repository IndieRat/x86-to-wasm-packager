Set-StrictMode -Version Latest
$script:XWASM_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
function Invoke-XWASM {
    param([Parameter(Mandatory)][string]$Script,[string[]]$Arguments=@())
    $p=Join-Path $script:XWASM_ROOT ("tool\"+$Script)
    if(!(Test-Path $p)){ throw "XWASM tool not found: $p" }
    & python $p @Arguments
    if($LASTEXITCODE -ne 0){ throw "XWASM tool failed ($LASTEXITCODE): $Script" }
}
function Get-XWASMTool {
    param([string]$Name,[string]$Fallback)
    if($Name){ return (Resolve-Path $Name).Path }
    if($Fallback -and (Test-Path $Fallback)){ return (Resolve-Path $Fallback).Path }
    return $null
}
function xwasm_build {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory,Position=0)][string]$Target,
        [string]$Clang="C:\Program Files\LLVM\bin\clang.exe",
        [string]$LldLink="C:\Program Files\LLVM\bin\lld-link.exe",
        [string]$OutputRoot="dist\xwasm-build"
    )
    $root=$script:XWASM_ROOT; $out=Join-Path $root $OutputRoot
    $runtime=Join-Path $root "dist\x86-runtime-v0.9\runtime.wasm"
    $xapi=Join-Path $out "default.xapi"
    New-Item -ItemType Directory -Force -Path $out | Out-Null
    $clangPath=Get-XWASMTool $Clang $null
    if(!$clangPath){ throw "clang not found: $Clang" }
    $lldPath=Get-XWASMTool $LldLink $null

    switch -Regex ($Target.ToLowerInvariant()) {
        '^stress(_test)?$' {
            Invoke-XWASM "xwasm_build_cpu_stress.py" @("--output",(Join-Path $out "stress_test"),"--clang",$clangPath); return
        }
        '^c(_test)?$' {
            Invoke-XWASM "xwasm_build_c5_fixture.py" @("--output",(Join-Path $out "C_test"),"--clang",$clangPath); return
        }
        '^cpp(_test)?$' {
            if(!$lldPath){throw "lld-link not found: $LldLink"}
            Invoke-XWASM "xwasm_build_cpp_fixture.py" @("--output",(Join-Path $out "CPP_test\cpp_fixture.exe"),"--clang",$clangPath,"--lld-link",$lldPath); return
        }
        '^sse(_test)?$' {
            if(!$lldPath){throw "lld-link not found: $LldLink"}
            Invoke-XWASM "xwasm_build_sse_fixture.py" @("--output",(Join-Path $out "SSE_test\sse_scalar_fixture.exe"),"--clang",$clangPath,"--lld-link",$lldPath); return
        }
        '^x87(_test)?$' {
            if(!$lldPath){throw "lld-link not found: $LldLink"}
            Invoke-XWASM "xwasm_build_x87_fixture.py" @("--output",(Join-Path $out "x87_test\x87_fixture.exe"),"--clang",$clangPath,"--lld-link",$lldPath); return
        }
        '^integer(_test)?$' {
            Invoke-XWASM "xwasm_build_integer_coverage_fixture.py" @("--output",(Join-Path $out "integer_test"),"--clang",$clangPath); return
        }
        '^cpu(_test)?$' {
            Invoke-XWASM "xwasm_build_x86_test.py" @("--output",(Join-Path $out "cpu_test"),"--clang",$clangPath); return
        }
        '^graphics(_test)?$' {
            Invoke-XWASM "xwasm_build_x86_graphics_test.py" @("--output",(Join-Path $out "graphics_test"),"--clang",$clangPath); return
        }
        '^window(_test)?$' {
            Invoke-XWASM "xwasm_build_x86_window_input_audio_test.py" @("--output",(Join-Path $out "window_test"),"--clang",$clangPath); return
        }
        '^all(_tests)?$' {
            foreach($k in @("cpu_test","stress_test","C_test","SSE_test","x87_test","integer_test","graphics_test","window_test")) { xwasm_build $k -Clang $clangPath -LldLink $LldLink -OutputRoot $OutputRoot }; return
        }
    }
    $game=(Resolve-Path $Target -ErrorAction Stop).Path
    if(!(Test-Path $game -PathType Container)){ throw "Game target must be a directory or a supported keyword: $Target" }
    Invoke-XWASM "xwasm_build_x86_runtime.py" @("--clang",$clangPath,"--output",$runtime)
    Invoke-XWASM "xwasm_build_xapi.py" @("--output",$xapi)
    $name=(Split-Path $game -Leaf)
    $package=Join-Path $out $name
    Invoke-XWASM "xwasm_pack_x86.py" @($game,"--output",$package,"--runtime",$runtime)
    Copy-Item $xapi (Join-Path $package "game.xapi") -Force
    Invoke-XWASM "xwasm_container.py" @("pack",(Join-Path $package "game.xapi"),(Join-Path $package "game.xapi.bin"),"--kind","xapi","--compression","auto")
    Write-Host "XWASM build complete: $package"
    Write-Host "Runtime: $runtime"
    Write-Host "API:     $(Join-Path $package 'game.xapi')"
}
function xwasm_environment {
    Write-Host "XWASM environment: $script:XWASM_ROOT"
    Write-Host "Commands: xwasm_build <game-folder|stress_test|C_test|CPP_test|SSE_test|x87_test|integer_test|cpu_test|graphics_test|window_test|all_tests>"
    Write-Host "LLVM:     C:\Program Files\LLVM\bin"
}
Export-ModuleMember -Function xwasm_build,xwasm_environment
