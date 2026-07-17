Option Explicit

Dim shell, fso, scriptDir, repoDir, launcher, command, pythonCommand
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
repoDir = fso.GetParentFolderName(fso.GetParentFolderName(scriptDir))
launcher = fso.BuildPath(repoDir, "launchers\launcher.pyw")

If Not fso.FileExists(launcher) Then
    MsgBox "The graphical launcher could not be found:" & vbCrLf & launcher & vbCrLf & vbCrLf & _
        "Extract the complete Windows bundle before starting it. Do not run the VBS file from inside the ZIP archive.", _
        16, "Local RLM Cowork"
    WScript.Quit 1
End If

pythonCommand = FindPythonCommand(shell, fso)
If pythonCommand = "" Then
    MsgBox "Python 3.11 or newer was not found." & vbCrLf & vbCrLf & _
        "Install 64-bit Python from python.org. On the first installer screen, enable 'Add python.exe to PATH' and install the Python launcher." & vbCrLf & vbCrLf & _
        "Then double-click this launcher again.", 16, "Local RLM Cowork"
    WScript.Quit 1
End If

command = pythonCommand & " """ & launcher & """"
shell.Run command, 0, False

Function FindPythonCommand(shellObject, fileSystem)
    Dim localAppData, programFiles, programFilesX86, candidates, candidate, exePath

    localAppData = shellObject.ExpandEnvironmentStrings("%LocalAppData%")
    programFiles = shellObject.ExpandEnvironmentStrings("%ProgramFiles%")
    programFilesX86 = shellObject.ExpandEnvironmentStrings("%ProgramFiles(x86)%")

    candidates = Array( _
        "py.exe -3.13", _
        "py.exe -3.12", _
        "py.exe -3.11", _
        Quote(fso.BuildPath(localAppData, "Programs\Python\Python313\pythonw.exe")), _
        Quote(fso.BuildPath(localAppData, "Programs\Python\Python312\pythonw.exe")), _
        Quote(fso.BuildPath(localAppData, "Programs\Python\Python311\pythonw.exe")), _
        Quote(fso.BuildPath(programFiles, "Python313\pythonw.exe")), _
        Quote(fso.BuildPath(programFiles, "Python312\pythonw.exe")), _
        Quote(fso.BuildPath(programFiles, "Python311\pythonw.exe")), _
        Quote(fso.BuildPath(programFilesX86, "Python313\pythonw.exe")), _
        Quote(fso.BuildPath(programFilesX86, "Python312\pythonw.exe")), _
        Quote(fso.BuildPath(programFilesX86, "Python311\pythonw.exe")), _
        "pythonw.exe" _
    )

    For Each candidate In candidates
        If CommandWorks(shellObject, CStr(candidate)) Then
            FindPythonCommand = CStr(candidate)
            Exit Function
        End If
    Next

    FindPythonCommand = ""
End Function

Function CommandWorks(shellObject, candidateCommand)
    Dim exitCode
    On Error Resume Next
    exitCode = shellObject.Run(candidateCommand & " --version", 0, True)
    If Err.Number <> 0 Then
        Err.Clear
        CommandWorks = False
    Else
        CommandWorks = (exitCode = 0)
    End If
    On Error GoTo 0
End Function

Function Quote(value)
    Quote = """" & value & """"
End Function
