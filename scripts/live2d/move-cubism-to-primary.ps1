<#
.SYNOPSIS
  Cubism Editor（java.exe）のメインウィンドウを、主モニター（左上 0,0）へ移して最大化する。
.DESCRIPTION
  Cubism は 2 台目のモニターに開くことがあり、そのモニターが消えていると画面操作ができない。
  使い方: powershell -File scripts/live2d/move-cubism-to-primary.ps1
#>
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class CubismMove {
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
}
'@
$p = Get-Process java -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like '*Cubism Editor*' } | Select-Object -First 1
if (-not $p) { Write-Output 'NOT_FOUND'; exit 1 }
$h = $p.MainWindowHandle
[CubismMove]::ShowWindow($h, 1) | Out-Null                                       # 通常表示に戻す
[CubismMove]::SetWindowPos($h, [IntPtr](-2), 0, 0, 1400, 900, 0x0040) | Out-Null  # NOTOPMOST、主モニターへ
[CubismMove]::ShowWindow($h, 3) | Out-Null                                       # 最大化
Write-Output "MOVED java $($p.Id)"
