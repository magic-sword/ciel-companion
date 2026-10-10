<#
.SYNOPSIS
  Cubism Editor（java.exe）の、指定したタイトルのウィンドウ（既定は「確認」）を、最前面に出す。
.DESCRIPTION
  起動時の「トライアル版」の確認や、上書きの確認は、スプラッシュや他のウィンドウの裏に隠れることがある。
  focus-window.ps1 はタイトルだけで探すので、別のアプリ（Chrome など）の同じ名前のウィンドウを拾うことがある。
  ここでは java.exe のウィンドウだけを対象にし、最前面（TOPMOST）にしてから前面化する。見つからなければ NOT_FOUND。
  使い方: powershell -File scripts/live2d/focus-cubism-dialog.ps1 [-Title '確認']
#>
param([string]$Title = '確認')
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class CubismFocus {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool f);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr a, int x, int y, int cx, int cy, uint f);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
}
'@
$p = Get-Process java -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$Title*" } | Select-Object -First 1
if (-not $p) { Write-Output "NOT_FOUND $Title"; exit 1 }
$h = $p.MainWindowHandle
$fg = [CubismFocus]::GetForegroundWindow()
$x = 0
$t = [CubismFocus]::GetWindowThreadProcessId($fg, [ref]$x)
$me = [CubismFocus]::GetCurrentThreadId()
[CubismFocus]::AttachThreadInput($me, $t, $true) | Out-Null
[CubismFocus]::ShowWindow($h, 9) | Out-Null
[CubismFocus]::SetWindowPos($h, [IntPtr](-1), 0, 0, 0, 0, 0x0003) | Out-Null   # TOPMOST, NOMOVE|NOSIZE
[CubismFocus]::BringWindowToTop($h) | Out-Null
$ok = [CubismFocus]::SetForegroundWindow($h)
[CubismFocus]::AttachThreadInput($me, $t, $false) | Out-Null
Write-Output "FOCUS java $($p.Id) '$($p.MainWindowTitle)' ok=$ok"
