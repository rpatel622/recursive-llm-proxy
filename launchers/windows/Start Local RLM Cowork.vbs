Option Explicit

Dim shell, fso, scriptDir, repoDir, launcher, bundledPython, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
repoDir = fso.GetParentFolderName(fso.GetParentFolderName(scriptDir))
launcher = fso.BuildPath(repoDir, "launchers\launcher.pyw")
bundledPython = fso.BuildPath(repoDir, "runtime\python\pythonw.exe")

If Not fso.FileExists(launcher) Then
    MsgBox "This bundle is incomplete or is being opened from inside a ZIP file. Extract the entire download to a normal folder and try again.", 16, "Local RLM Cowork"
    WScript.Quit 1
End If

If fso.FileExists(bundledPython) Then
    command = Chr(34) & bundledPython & Chr(34) & " " & Chr(34) & launcher & Chr(34)
    shell.Run command, 0, False
    WScript.Quit 0
End If

MsgBox "The bundled Python runtime is missing. Download and fully extract the Windows release bundle. Source-code ZIP files require a separate Python installation.", 16, "Local RLM Cowork"
WScript.Quit 1
