<#
.SYNOPSIS
    Renames "Orion" -> "Aquila" (case-preserving) across every .py file,
    IN PLACE, so Git sees them as modified files, not new ones.

.DESCRIPTION
    Recursively scans a project folder for .py files and replaces:
        ORION -> AQUILA   (all-caps constants/enum values)
        Orion -> Aquila   (class names, docstrings, titles)
        orion -> aquila   (hostnames, logger names, slugs)

    Skips .git, .venv, venv, __pycache__, build, and dist folders.
    Only writes a file if it actually changed. Files are re-encoded
    as UTF-8 without a BOM; existing line endings (CRLF/LF) are left
    exactly as they were, since this only does text substitution.

.PARAMETER Path
    Root folder to scan. Defaults to the current directory, so you can
    just cd into your project root and run the script with no arguments.

.PARAMETER WhatIf
    Preview which files WOULD change and how many replacements each
    would get, without writing anything.

.EXAMPLE
    cd C:\Aquila
    .\Rename-OrionToAquila.ps1 -WhatIf

.EXAMPLE
    cd C:\Aquila
    .\Rename-OrionToAquila.ps1
#>

[CmdletBinding()]
param(
    [string]$Path = ".",
    [switch]$WhatIf
)

$ExcludeDirs = @('.git', '.venv', 'venv', '__pycache__', 'build', 'dist', 'node_modules')

# Order doesn't matter here since each rule targets a distinct exact
# case pattern -- they can't accidentally match each other's output.
# (A plain hashtable can't be used here: PowerShell hashtable keys are
# case-INsensitive by default, so 'Orion' and 'orion' would collide.
# Using two parallel arrays instead of an array-of-arrays sidesteps
# PowerShell's array-flattening quirks entirely.)
$OldValues = @('ORION', 'Orion', 'orion')
$NewValues = @('AQUILA', 'Aquila', 'aquila')

$RootInfo = Resolve-Path -Path $Path -ErrorAction Stop
$Root = $RootInfo.Path

Write-Host "Scanning '$Root' for .py files..." -ForegroundColor Cyan

$Files = Get-ChildItem -Path $Root -Recurse -File -Filter *.py | Where-Object {
    $segments = $_.FullName -split '[\\/]'
    -not ($segments | Where-Object { $ExcludeDirs -contains $_ })
}

Write-Host "Found $($Files.Count) Python file(s) to check.`n"

$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$changedCount = 0
$totalReplacements = 0

foreach ($file in $Files) {
    $original = [System.IO.File]::ReadAllText($file.FullName, $Utf8NoBom)
    $updated = $original
    $fileReplacements = 0

    for ($i = 0; $i -lt $OldValues.Count; $i++) {
        $old = $OldValues[$i]
        $new = $NewValues[$i]
        $matchCount = ([regex]::Matches($updated, [regex]::Escape($old))).Count
        if ($matchCount -gt 0) {
            $updated = $updated.Replace($old, $new)
            $fileReplacements += $matchCount
        }
    }

    if ($updated -ne $original) {
        $changedCount++
        $totalReplacements += $fileReplacements
        $relativePath = $file.FullName.Substring($Root.Length).TrimStart('\', '/')

        if ($WhatIf) {
            Write-Host "[WOULD CHANGE] $relativePath  ($fileReplacements replacements)" -ForegroundColor Yellow
        }
        else {
            [System.IO.File]::WriteAllText($file.FullName, $updated, $Utf8NoBom)
            Write-Host "[CHANGED]      $relativePath  ($fileReplacements replacements)" -ForegroundColor Green
        }
    }
}

Write-Host ""
if ($WhatIf) {
    Write-Host "DRY RUN: $changedCount file(s) would be modified, $totalReplacements total replacements." -ForegroundColor Cyan
    Write-Host "Run again without -WhatIf to actually apply the changes." -ForegroundColor Cyan
}
else {
    Write-Host "Done: $changedCount file(s) modified, $totalReplacements total replacements." -ForegroundColor Cyan
    Write-Host "Run 'git status' and 'git diff' to review before committing." -ForegroundColor Cyan
}