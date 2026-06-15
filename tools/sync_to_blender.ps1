$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$targetRoot = "C:\Users\User\AppData\Roaming\Blender Foundation\Blender\5.1\extensions\user_default"
$target = Join-Path $targetRoot "hotspot_base_map_generator"

$resolvedTargetRoot = [System.IO.Path]::GetFullPath($targetRoot)
$resolvedTarget = [System.IO.Path]::GetFullPath($target)
if (-not $resolvedTarget.StartsWith($resolvedTargetRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to sync outside Blender user extension folder: $resolvedTarget"
}

New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null

if (Test-Path -LiteralPath $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
}

New-Item -ItemType Directory -Force -Path $target | Out-Null

Copy-Item -LiteralPath (Join-Path $repoRoot "blender_manifest.toml") -Destination $target
Copy-Item -LiteralPath (Join-Path $repoRoot "__init__.py") -Destination $target
Copy-Item -LiteralPath (Join-Path $repoRoot "hotspot_base_map_generator") -Destination $target -Recurse

Get-ChildItem -Path $target -Recurse -Directory -Filter "__pycache__" | ForEach-Object {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
}

Write-Host "Synced Hotspot Base Map Generator to $target"

