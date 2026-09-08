; 教伴 Inno Setup 安装脚本
; 使用前先运行 build_exe.bat 生成 dist\TeachBuddy.exe
; 程序数据优先保存在安装目录下的 data\ 子文件夹；安装到用户可写目录，无需管理员权限。

[Setup]
AppName=教伴
AppVersion=1.0.0
AppPublisher=TeachBuddy
DefaultDirName={localappdata}\教伴
DefaultGroupName=教伴
OutputBaseFilename=TeachBuddySetup
OutputDir=Output
Compression=lzma2
SolidCompression=yes
; Python 3.8.10 的 Win7 支持基线为 Windows 7 SP1。
MinVersion=6.1sp1
PrivilegesRequired=lowest

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:"

[Files]
Source: "..\dist\TeachBuddy.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\教伴"; Filename: "{app}\TeachBuddy.exe"
Name: "{group}\卸载教伴"; Filename: "{uninstallexe}"
Name: "{autodesktop}\教伴"; Filename: "{app}\TeachBuddy.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\TeachBuddy.exe"; Description: "立即运行教伴"; Flags: nowait postinstall skipifsilent
