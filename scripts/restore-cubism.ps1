# Obtain the SDK yourself from Live2D under its license, then restore before opening Unity.
param(
    [Parameter(Mandatory = $true)][string] $PackagePath,
    [string] $ProjectPath = (Join-Path $PSScriptRoot '../unity')
)
$ErrorActionPreference = 'Stop'
$expectedHash = 'C9AC920B3A7359DC9EBE4EC0E9AD3C50367D615BDAEBA3FC028141E90D45A0A1'
$package = (Resolve-Path -LiteralPath $PackagePath).Path
if ((Get-FileHash -LiteralPath $package -Algorithm SHA256).Hash -ne $expectedHash) {
    throw 'Package does not match the pinned official Cubism URP R5. No files were changed.'
}
$repository = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$project = [IO.Path]::GetFullPath($ProjectPath)
if (-not $project.StartsWith($repository + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
    throw 'The target project must be inside this repository.'
}
if (Test-Path -LiteralPath (Join-Path $project 'Temp/UnityLockfile')) {
    throw 'Close Unity before restoring the SDK.'
}
Get-Command tar -CommandType Application -ErrorAction Stop | Out-Null
$staging = Join-Path $repository ('.local/cubism-restore-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Force -Path $staging | Out-Null
# Only the exact hash-verified official archive is extracted here.
& tar -xzf $package -C $staging
if ($LASTEXITCODE -ne 0) { throw 'Could not unpack the Unity package.' }
$live2d = [IO.Path]::GetFullPath((Join-Path $project 'Assets/Live2D'))
$count = 0
foreach ($entry in Get-ChildItem -LiteralPath $staging -Directory) {
    $pathname = Join-Path $entry.FullName 'pathname'
    if (-not (Test-Path -LiteralPath $pathname)) { continue }
    $relative = [IO.File]::ReadAllText($pathname).Trim().Replace('\', '/')
    if ($relative -ne 'Assets/Live2D' -and -not $relative.StartsWith('Assets/Live2D/')) { continue }
    $destination = [IO.Path]::GetFullPath((Join-Path $project $relative))
    if ($destination -ne $live2d -and -not $destination.StartsWith($live2d + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
        throw 'SDK asset path is outside Assets/Live2D.'
    }
    $asset = Join-Path $entry.FullName 'asset'
    if (Test-Path -LiteralPath $asset -PathType Leaf) {
        New-Item -ItemType Directory -Force -Path ([IO.Path]::GetDirectoryName($destination)) | Out-Null
        Copy-Item -LiteralPath $asset -Destination $destination -Force
    } else {
        New-Item -ItemType Directory -Force -Path $destination | Out-Null
    }
    $meta = Join-Path $entry.FullName 'asset.meta'
    if (Test-Path -LiteralPath $meta -PathType Leaf) {
        Copy-Item -LiteralPath $meta -Destination ($destination + '.meta') -Force
    }
    $count++
}
& (Join-Path $PSScriptRoot 'repair-cubism.ps1') -ProjectPath $project
Write-Output "Restored $count Live2D assets and their GUIDs. Open Unity, then run CIEL/SDK/Configure and Validate."
