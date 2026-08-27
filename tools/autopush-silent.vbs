' Launches the auto-push watcher with no visible window.
' Task Scheduler runs this so nothing flashes on screen every few minutes.
' To run the watcher visibly instead, use autopush-run.bat.

Dim shell, fso, here, cmd
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
here = fso.GetParentFolderName(WScript.ScriptFullName)
cmd = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & here & "\autopush.ps1"""
shell.Run cmd, 0, False
