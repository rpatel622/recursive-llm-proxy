Option Explicit

Dim shell, fso, scriptDir, repoDir, launcher, command, candidate, pythonw
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
repoDir = fso.GetParentFolderName(fso.GetParentFolderName(scriptDir))
launcher = fso.BuildPath(repoDir, "launchers\launcher.pyw")

pythonw = ""
For Each candidate In Array("pyw.exe -3.11", "pyw.exe -3", "pythonw.exe")
    If shell.Run("cmd /c """ & Split(candidate, " ")(0) & """ --version", 0, True) = 0 Then
        pythonw = candidate
        Exit For
    End If
Next

If pythonw = "" Then
    MsgBox "Python 3.11 or newer was not found. Install Python from python.org and enable the Python launcher, then double-click this file again.", 16, "Local RLM Cowork"
    WScript.Quit 1
End If

command = pythonw & " """ & launcher & """"
shell.Run command, 0, False
