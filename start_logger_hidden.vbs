Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File ""C:\Users\milin\OneDrive\hyperliquid-arb\logger_startup.ps1""", 0, False
