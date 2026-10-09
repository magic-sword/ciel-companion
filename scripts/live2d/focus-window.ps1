<#
.SYNOPSIS
  指定したプロセスのウィンドウを前面に出す（Cubism Editor などの画面操作の補助）。
.DESCRIPTION
  SetForegroundWindow だけだと、別のアプリが前面にあるとき拒否される。呼び出しスレッドを前面ウィンドウの
  スレッドへ AttachThreadInput で結び付けてから、ShowWindow・SetForegroundWindow・BringWindowToTop を呼ぶ。
  使い方: powershell -File scripts/live2d/focus-window.ps1 -TitlePattern 'Cubism'
#>
param([string]$TitlePattern = 'Cubism')
Add-Type -TypeDefinition @'
using System; using System.Runtime.InteropServices;
public static class FocusWin {
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll")] public static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);
  [DllImport("user32.dll")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
  [DllImport("user32.dll")] public static extern bool BringWindowToTop(IntPtr h);
  [DllImport("kernel32.dll")] public static extern uint GetCurrentThreadId();
}
'@
$p = Get-Process | Where-Object { $_.MainWindowHandle -ne 0 -and $_.MainWindowTitle -like "*$TitlePattern*" } | Select-Object -First 1
if (-not $p) { Write-Output "NOT_FOUND $TitlePattern"; exit 1 }
$h = $p.MainWindowHandle
$fg = [FocusWin]::GetForegroundWindow()
$pid2 = 0
$fgThread = [FocusWin]::GetWindowThreadProcessId($fg, [ref]$pid2)
$me = [FocusWin]::GetCurrentThreadId()
[FocusWin]::AttachThreadInput($me, $fgThread, $true) | Out-Null
[FocusWin]::ShowWindow($h, 9) | Out-Null
[FocusWin]::BringWindowToTop($h) | Out-Null
$ok = [FocusWin]::SetForegroundWindow($h)
[FocusWin]::AttachThreadInput($me, $fgThread, $false) | Out-Null
Write-Output "FOCUS $($p.ProcessName) $($p.Id) ok=$ok"
