Set WshShell = CreateObject("WScript.Shell")
' Get the directory where the VBS script is located
strPath = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
' Run the virtual environment pythonw invisibly (0)
WshShell.Run "cmd /c cd /d """ & strPath & """ && .\.venv\Scripts\pythonw.exe main.py", 0, False
