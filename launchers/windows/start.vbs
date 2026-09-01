Option Explicit

Dim shell, fso, launcherDir, root, pythonw, manage, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
launcherDir = fso.GetParentFolderName(WScript.ScriptFullName)
root = fso.GetParentFolderName(fso.GetParentFolderName(launcherDir))
pythonw = shell.ExpandEnvironmentStrings("%LocalAppData%") & "\Programs\Python\Python313\pythonw.exe"
manage = root & "\scripts\manage.py"

If Not fso.FileExists(pythonw) Then
    MsgBox "Python 3.13 was not found. Run launchers\windows\start.bat to check Python.", 16, "Bookmark"
    WScript.Quit 1
End If

command = Chr(34) & pythonw & Chr(34) & " -X utf8 " & Chr(34) & manage & Chr(34)
shell.Run command, 0, False
