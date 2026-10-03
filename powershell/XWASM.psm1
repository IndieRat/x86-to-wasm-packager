Set-StrictMode -Version Latest
$script:XWASM_ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Invoke-XWASM {
    param(
        [Parameter(Mandatory)][string]$Script,
        [string[]]$Arguments = @()
    )
    $p = Join-Path $script:XWASM_ROOT ("tool\" + $Script)
    if (!(Test-Path $p -PathType Leaf)) {
        throw "XWASM tool not found: $p"
    }
    & python $p @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "XWASM tool failed ($LASTEXITCODE): $Script"
    }
}

function Resolve-XWASMTool {
    param(
        [Parameter(Mandatory)][string]$Path,
        [string]$Label
    )
    if (!(Test-Path $Path -PathType Leaf)) {
        throw "$Label not found: $Path"
    }
    return (Resolve-Path $Path).Path
}

function xwasm_prep {
    [CmdletBinding()]
    param(
        [string]$XedInput = "",
        [switch]$LegacyI386
    )

    $args = @()
    if ($XedInput) {
        $args += @("--xed-input", $XedInput)
    }
    if ($LegacyI386) {
        $args += "--legacy-i386"
    }

    Invoke-XWASM "xwasm_prep.py" $args
}

function xwasm_build {
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position=0)][string]$Target,
        [string]$Clang = "C:\Program Files\LLVM\bin\clang.exe",
        [string]$LldLink = "C:\Program Files\LLVM\bin\lld-link.exe",
        [string]$OutputRoot = "dist\xwasm-build"
    )

    $root = $script:XWASM_ROOT
    $out = Join-Path $root $OutputRoot
    $clangPath = Resolve-XWASMTool $Clang "clang"
    $lldPath = if (Test-Path $LldLink -PathType Leaf) {
        (Resolve-Path $LldLink).Path
    } else {
        $null
    }

    New-Item -ItemType Directory -Force -Path $out | Out-Null

    switch -Regex ($Target.ToLowerInvariant()) {
        '^prep(_test)?$' {
            xwasm_prep
            return
        }
        '^runtime(_test)?$' {
            xwasm_prep
            $runtime = Join-Path $root "dist\xwasm-runtime\runtime.xwasm"
            Invoke-XWASM "xwasm_build_x86_runtime.py" @(
                "--clang", $clangPath,
                "--output", $runtime
            )
            Write-Host "XWASM runtime ready: $runtime"
            return
        }
        '^stress(_test)?$' {
            Invoke-XWASM "xwasm_build_cpu_stress.py" @(
                "--output", (Join-Path $out "stress_test"),
                "--clang", $clangPath
            )
            return
        }
        '^c(_test)?$' {
            if (!$lldPath) { throw "lld-link not found: $LldLink" }
            Invoke-XWASM "xwasm_build_c5_fixture.py" @(
                "--output", (Join-Path $out "C_test"),
                "--clang", $clangPath,
                "--lld-link", $lldPath
            )
            return
        }
        '^cpp(_test)?$' {
            if (!$lldPath) { throw "lld-link not found: $LldLink" }
            Invoke-XWASM "xwasm_build_cpp_fixture.py" @(
                "--output", (Join-Path $out "CPP_test"),
                "--clang", $clangPath,
                "--lld-link", $lldPath
            )
            return
        }
        '^sse(_test)?$' {
            if (!$lldPath) { throw "lld-link not found: $LldLink" }
            Invoke-XWASM "xwasm_build_sse_fixture.py" @(
                "--output", (Join-Path $out "SSE_test"),
                "--clang", $clangPath,
                "--lld-link", $lldPath
            )
            return
        }
        '^x87(_test)?$' {
            if (!$lldPath) { throw "lld-link not found: $LldLink" }
            Invoke-XWASM "xwasm_build_x87_fixture.py" @(
                "--output", (Join-Path $out "x87_test"),
                "--clang", $clangPath,
                "--lld-link", $lldPath
            )
            return
        }
        '^integer(_test)?$' {
            if (!$lldPath) { throw "lld-link not found: $LldLink" }
            Invoke-XWASM "xwasm_build_integer_coverage_fixture.py" @(
                "--output", (Join-Path $out "integer_test"),
                "--clang", $clangPath,
                "--lld-link", $lldPath
            )
            return
        }
        '^cpu(_test)?$' {
            Invoke-XWASM "xwasm_build_x86_test.py" @(
                "--output", (Join-Path $out "cpu_test"),
                "--clang", $clangPath
            )
            return
        }
        '^graphics(_test)?$' {
            Invoke-XWASM "xwasm_build_x86_graphics_test.py" @(
                "--output", (Join-Path $out "graphics_test")
            )
            return
        }
        '^window(_test)?
            Invoke-XWASM "xwasm_build_xapi.py" @(
                "--output", (Join-Path $out "default.xapi")
            )
            return
        }
        '^all(_tests)?$' {
            foreach ($k in @(
                "cpu_test", "stress_test", "C_test", "CPP_test",
                "SSE_test", "x87_test", "integer_test", "api_test"
            )) {
                xwasm_build $k -Clang $clangPath -LldLink $LldLink -OutputRoot $OutputRoot
            }
            return
        }
    }

    $game = (Resolve-Path $Target -ErrorAction Stop).Path
    if (!(Test-Path $game -PathType Container)) {
        throw "Game target must be a directory or a supported keyword: $Target"
    }

    xwasm_prep

    $runtime = Join-Path $root "dist\xwasm-runtime\runtime.xwasm"
    $xapi = Join-Path $out "default.xapi"

    Invoke-XWASM "xwasm_build_x86_runtime.py" @(
        "--clang", $clangPath,
        "--output", $runtime
    )
    Invoke-XWASM "xwasm_build_xapi.py" @("--output", $xapi)

    $name = Split-Path $game -Leaf
    $package = Join-Path $out $name

    Invoke-XWASM "xwasm_pack_x86.py" @(
        $game,
        "--output", $package,
        "--runtime", $runtime
    )
    Copy-Item $xapi (Join-Path $package "game.xapi") -Force

    Write-Host "XWASM build complete: $package"
    Write-Host "Runtime: $runtime"
    Write-Host "API:     $(Join-Path $package 'game.xapi')"
}

function xwasm_environment {
    [CmdletBinding()]
    param(
        [string]$Clang = "C:\Program Files\LLVM\bin\clang.exe",
        [string]$LldLink = "C:\Program Files\LLVM\bin\lld-link.exe"
    )

    $python = Get-Command python -ErrorAction SilentlyContinue

    Write-Host "XWASM environment: $script:XWASM_ROOT"
    Write-Host "Python: $(if ($python) { $python.Source } else { '[MISSING]' })"
    Write-Host "LLVM clang: $Clang $(if (Test-Path $Clang -PathType Leaf) { '[OK]' } else { '[MISSING]' })"
    Write-Host "LLVM lld-link: $LldLink $(if (Test-Path $LldLink -PathType Leaf) { '[OK]' } else { '[MISSING]' })"
    Write-Host "Commands:"
    Write-Host "  xwasm_prep"
    Write-Host "  xwasm_build prep"
    Write-Host "  xwasm_build runtime"
    Write-Host "  xwasm_build <game-folder>"
    Write-Host "  xwasm_build stress_test | C_test | CPP_test | SSE_test | x87_test"
    Write-Host "  xwasm_build integer_test | cpu_test | graphics_test | window_test | pong"
    Write-Host "  xwasm_build api_test | all_tests"
}

Export-ModuleMember -Function xwasm_prep, xwasm_build, xwasm_environment
 {
            Invoke-XWASM "xwasm_build_x86_window_input_audio_test.py" @(
                "--output", (Join-Path $out "window_test")
            )
            return
        }
        '^pong(_test)?
            Invoke-XWASM "xwasm_build_xapi.py" @(
                "--output", (Join-Path $out "default.xapi")
            )
            return
        }
        '^all(_tests)?$' {
            foreach ($k in @(
                "cpu_test", "stress_test", "C_test", "CPP_test",
                "SSE_test", "x87_test", "integer_test", "api_test"
            )) {
                xwasm_build $k -Clang $clangPath -LldLink $LldLink -OutputRoot $OutputRoot
            }
            return
        }
    }

    $game = (Resolve-Path $Target -ErrorAction Stop).Path
    if (!(Test-Path $game -PathType Container)) {
        throw "Game target must be a directory or a supported keyword: $Target"
    }

    xwasm_prep

    $runtime = Join-Path $root "dist\xwasm-runtime\runtime.xwasm"
    $xapi = Join-Path $out "default.xapi"

    Invoke-XWASM "xwasm_build_x86_runtime.py" @(
        "--clang", $clangPath,
        "--output", $runtime
    )
    Invoke-XWASM "xwasm_build_xapi.py" @("--output", $xapi)

    $name = Split-Path $game -Leaf
    $package = Join-Path $out $name

    Invoke-XWASM "xwasm_pack_x86.py" @(
        $game,
        "--output", $package,
        "--runtime", $runtime
    )
    Copy-Item $xapi (Join-Path $package "game.xapi") -Force

    Write-Host "XWASM build complete: $package"
    Write-Host "Runtime: $runtime"
    Write-Host "API:     $(Join-Path $package 'game.xapi')"
}

function xwasm_environment {
    [CmdletBinding()]
    param(
        [string]$Clang = "C:\Program Files\LLVM\bin\clang.exe",
        [string]$LldLink = "C:\Program Files\LLVM\bin\lld-link.exe"
    )

    $python = Get-Command python -ErrorAction SilentlyContinue

    Write-Host "XWASM environment: $script:XWASM_ROOT"
    Write-Host "Python: $(if ($python) { $python.Source } else { '[MISSING]' })"
    Write-Host "LLVM clang: $Clang $(if (Test-Path $Clang -PathType Leaf) { '[OK]' } else { '[MISSING]' })"
    Write-Host "LLVM lld-link: $LldLink $(if (Test-Path $LldLink -PathType Leaf) { '[OK]' } else { '[MISSING]' })"
    Write-Host "Commands:"
    Write-Host "  xwasm_prep"
    Write-Host "  xwasm_build prep"
    Write-Host "  xwasm_build runtime"
    Write-Host "  xwasm_build <game-folder>"
    Write-Host "  xwasm_build stress_test | C_test | CPP_test | SSE_test | x87_test"
    Write-Host "  xwasm_build integer_test | cpu_test | graphics_test | window_test"
    Write-Host "  xwasm_build api_test | all_tests"
}

Export-ModuleMember -Function xwasm_prep, xwasm_build, xwasm_environment
 {
            $runtime = Join-Path $root "dist\xwasm-runtime\runtime.xwasm"
            if (!(Test-Path $runtime -PathType Leaf)) {
                throw "XWASM runtime not found: $runtime. Run xwasm_build runtime first."
            }
            Invoke-XWASM "xwasm_build_x86_opengl_pong_test.py" @(
                "--output", (Join-Path $out "pong_test"),
                "--runtime", $runtime
            )
            Write-Host "XWASM Pong fixture ready: $(Join-Path $out 'pong_test')"
            return
        }
        '^api(_test)?
            Invoke-XWASM "xwasm_build_xapi.py" @(
                "--output", (Join-Path $out "default.xapi")
            )
            return
        }
        '^all(_tests)?$' {
            foreach ($k in @(
                "cpu_test", "stress_test", "C_test", "CPP_test",
                "SSE_test", "x87_test", "integer_test", "api_test"
            )) {
                xwasm_build $k -Clang $clangPath -LldLink $LldLink -OutputRoot $OutputRoot
            }
            return
        }
    }

    $game = (Resolve-Path $Target -ErrorAction Stop).Path
    if (!(Test-Path $game -PathType Container)) {
        throw "Game target must be a directory or a supported keyword: $Target"
    }

    xwasm_prep

    $runtime = Join-Path $root "dist\xwasm-runtime\runtime.xwasm"
    $xapi = Join-Path $out "default.xapi"

    Invoke-XWASM "xwasm_build_x86_runtime.py" @(
        "--clang", $clangPath,
        "--output", $runtime
    )
    Invoke-XWASM "xwasm_build_xapi.py" @("--output", $xapi)

    $name = Split-Path $game -Leaf
    $package = Join-Path $out $name

    Invoke-XWASM "xwasm_pack_x86.py" @(
        $game,
        "--output", $package,
        "--runtime", $runtime
    )
    Copy-Item $xapi (Join-Path $package "game.xapi") -Force

    Write-Host "XWASM build complete: $package"
    Write-Host "Runtime: $runtime"
    Write-Host "API:     $(Join-Path $package 'game.xapi')"
}

function xwasm_environment {
    [CmdletBinding()]
    param(
        [string]$Clang = "C:\Program Files\LLVM\bin\clang.exe",
        [string]$LldLink = "C:\Program Files\LLVM\bin\lld-link.exe"
    )

    $python = Get-Command python -ErrorAction SilentlyContinue

    Write-Host "XWASM environment: $script:XWASM_ROOT"
    Write-Host "Python: $(if ($python) { $python.Source } else { '[MISSING]' })"
    Write-Host "LLVM clang: $Clang $(if (Test-Path $Clang -PathType Leaf) { '[OK]' } else { '[MISSING]' })"
    Write-Host "LLVM lld-link: $LldLink $(if (Test-Path $LldLink -PathType Leaf) { '[OK]' } else { '[MISSING]' })"
    Write-Host "Commands:"
    Write-Host "  xwasm_prep"
    Write-Host "  xwasm_build prep"
    Write-Host "  xwasm_build runtime"
    Write-Host "  xwasm_build <game-folder>"
    Write-Host "  xwasm_build stress_test | C_test | CPP_test | SSE_test | x87_test"
    Write-Host "  xwasm_build integer_test | cpu_test | graphics_test | window_test"
    Write-Host "  xwasm_build api_test | all_tests"
}

Export-ModuleMember -Function xwasm_prep, xwasm_build, xwasm_environment
 {
            Invoke-XWASM "xwasm_build_xapi.py" @(
                "--output", (Join-Path $out "default.xapi")
            )
            return
        }
        '^all(_tests)?$' {
            foreach ($k in @(
                "cpu_test", "stress_test", "C_test", "CPP_test",
                "SSE_test", "x87_test", "integer_test", "api_test"
            )) {
                xwasm_build $k -Clang $clangPath -LldLink $LldLink -OutputRoot $OutputRoot
            }
            return
        }
    }

    $game = (Resolve-Path $Target -ErrorAction Stop).Path
    if (!(Test-Path $game -PathType Container)) {
        throw "Game target must be a directory or a supported keyword: $Target"
    }

    xwasm_prep

    $runtime = Join-Path $root "dist\xwasm-runtime\runtime.xwasm"
    $xapi = Join-Path $out "default.xapi"

    Invoke-XWASM "xwasm_build_x86_runtime.py" @(
        "--clang", $clangPath,
        "--output", $runtime
    )
    Invoke-XWASM "xwasm_build_xapi.py" @("--output", $xapi)

    $name = Split-Path $game -Leaf
    $package = Join-Path $out $name

    Invoke-XWASM "xwasm_pack_x86.py" @(
        $game,
        "--output", $package,
        "--runtime", $runtime
    )
    Copy-Item $xapi (Join-Path $package "game.xapi") -Force

    Write-Host "XWASM build complete: $package"
    Write-Host "Runtime: $runtime"
    Write-Host "API:     $(Join-Path $package 'game.xapi')"
}

function xwasm_environment {
    [CmdletBinding()]
    param(
        [string]$Clang = "C:\Program Files\LLVM\bin\clang.exe",
        [string]$LldLink = "C:\Program Files\LLVM\bin\lld-link.exe"
    )

    $python = Get-Command python -ErrorAction SilentlyContinue

    Write-Host "XWASM environment: $script:XWASM_ROOT"
    Write-Host "Python: $(if ($python) { $python.Source } else { '[MISSING]' })"
    Write-Host "LLVM clang: $Clang $(if (Test-Path $Clang -PathType Leaf) { '[OK]' } else { '[MISSING]' })"
    Write-Host "LLVM lld-link: $LldLink $(if (Test-Path $LldLink -PathType Leaf) { '[OK]' } else { '[MISSING]' })"
    Write-Host "Commands:"
    Write-Host "  xwasm_prep"
    Write-Host "  xwasm_build prep"
    Write-Host "  xwasm_build runtime"
    Write-Host "  xwasm_build <game-folder>"
    Write-Host "  xwasm_build stress_test | C_test | CPP_test | SSE_test | x87_test"
    Write-Host "  xwasm_build integer_test | cpu_test | graphics_test | window_test"
    Write-Host "  xwasm_build api_test | all_tests"
}

Export-ModuleMember -Function xwasm_prep, xwasm_build, xwasm_environment
