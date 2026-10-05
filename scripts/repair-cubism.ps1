# Reapply CIEL's Unity 6.6 compatibility changes after importing Cubism URP R5.
param([string] $ProjectPath = (Join-Path $PSScriptRoot '../unity'))
$ErrorActionPreference = 'Stop'
$cubismRoot = Join-Path $ProjectPath 'Assets/Live2D/Cubism'
if (-not (Test-Path -LiteralPath (Join-Path $cubismRoot 'cubism-info.yml'))) {
    throw 'Import the official Cubism 5 SDK for Unity R5 (URP) first.'
}
$changes = @(
    @{ Path = 'Editor/CubismUnityEditorUtility.cs'; Old = 'AssetDatabase.GetAssetPath(activeObject.GetInstanceID())'; New = 'AssetDatabase.GetAssetPath(activeObject)'; Count = 1 },
    @{ Path = 'Framework/Pose/Editor/CubismPoseMotionImporter.cs'; Old = 'animationClip.GetInstanceID()'; New = 'Live2D.Cubism.Framework.CubismMotionEventId.Get(animationClip)'; Count = 3 },
    @{ Path = 'Framework/MotionFade/Editor/CubismFadeMotionImporter.cs'; Old = 'animationClip.GetInstanceID()'; New = 'Live2D.Cubism.Framework.CubismMotionEventId.Get(animationClip)'; Count = 2 }
)
$prepared = @()
foreach ($change in $changes) {
    $path = Join-Path $cubismRoot $change.Path
    $source = [IO.File]::ReadAllText($path)
    $oldCount = [regex]::Matches($source, [regex]::Escape($change.Old)).Count
    $newCount = [regex]::Matches($source, [regex]::Escape($change.New)).Count
    if ($oldCount -eq 0 -and $newCount -eq $change.Count) { continue }
    if ($oldCount -ne $change.Count) { throw "Unexpected SDK source in $path; check SDK version before patching." }
    $source = $source.Replace($change.Old, $change.New)
    $source = '// Modified by CIEL: Unity 6.6 compatibility. See docs/decisions/sdk-setup.md.' + [Environment]::NewLine + $source
    $prepared += @{ Path = $path; Source = $source }
}
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'cubism/CubismMotionEventId.cs') -Destination (Join-Path $cubismRoot 'Framework/CubismMotionEventId.cs') -Force
foreach ($item in $prepared) {
    [IO.File]::WriteAllText($item.Path, $item.Source, (New-Object Text.UTF8Encoding $false))
}
Write-Output 'Cubism R5 compatibility changes are applied. Run CIEL/SDK/Configure and Validate in Unity.'
