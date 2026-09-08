# Win7 部署与验证指南

## 一、打包机要求

1. 使用 **Windows** 打包，位数必须和目标电脑一致；不确定老师电脑位数时，优先打包 **32 位**。
2. 安装 [Python 3.8.10](https://www.python.org/downloads/release/python-3810/)。不要用 Python 3.9、3.10、3.11、3.14；它们已经不能保证 Win7 可运行。
3. 在项目目录执行：

```bat
set TARGET_BITS=32
build_exe.bat
```

如果确认目标是 64 位 Win7，可改用：

```bat
set TARGET_BITS=64
build_exe.bat
```

如果本项目已包含 `runtime\python38\python.exe`，构建脚本会自动优先使用它；新打包电脑仍建议按上面方式安装 Python 3.8.10。

`build_exe.bat` 会拒绝非 Python 3.8.10 构建，并按 `TARGET_BITS` 校验 Python 位数。构建成功后产物是：

```text
dist\TeachBuddy.exe
```

> 当前仓库里的旧 `dist\TeachBuddy.exe` 如果是 Python 3.14 打包产物，不能用于 Win7。请按本指南重新构建后再分发。

## 二、Win7 电脑要求

- 系统必须是 **Windows 7 SP1**。
- 先完成 Windows 基础安全更新，保证系统时间和证书链正常。
- 安装 Microsoft Visual C++ 2015-2019 Redistributable；32 位 exe 装 `vc_redist.x86.exe`，64 位 exe 装 `vc_redist.x64.exe`。
- AI 联网功能需要 TLS 1.2。请保持 Win7 SP1 已打基础更新；如果仍失败，先校准系统时间，再咨询学校网络管理员是否代理拦截了 AI 服务地址。
- 不联网也能使用：文件整理、重复文件检测、离线教案模板、Word 导出。

## 三、Win7 实机验收

把新构建的 `TeachBuddy.exe` 放到桌面或 `D:\TeachBuddy\`，双击启动后检查：

1. 首次欢迎页能显示，可选择“跳过，离线使用”。
2. 选择一个只包含测试文件的目录，执行文件整理，确认预览、执行、撤销都成功。
3. 选择两个内容相同、大小相同的文件，执行重复文件检测，确认重复项进入待删区并可撤销。
4. 教案页选择“常规课”，点击“按模板生成（离线）”，编辑后导出 Word，并用 Word/WPS 打开。
5. 配置主 AI 服务，点击“设置 → 保存并测试连接”。
6. 可选：配置备用 AI 服务；临时改错主服务地址后再测试，确认程序自动回退并在错误信息中说明原因。
7. 对话页发送一个问题，确认不阻塞界面，关闭窗口不残留异常。

## 四、常见问题

### 双击 exe 没有窗口

查看 exe 同级 `data\error.log`。如果提示缺少 `api-ms-win-crt-*.dll` 或 `VCRUNTIME140.dll`，先安装上文的 Visual C++ 运行库。

### 提示未找到 Python 3.8.10

这是打包机的问题，不是 Win7 问题。安装 Python 3.8.10 后重开命令行，再运行 `build_exe.bat`。

### AI 连接失败

1. 检查 API 地址是否到 `/v1`，模型名是否拼写正确。
2. 点击“保存并测试连接”查看具体 HTTP 状态。
3. 校准 Win7 系统时间。
4. 更换备用服务商；程序会按主服务、备用服务顺序重试。

### 杀毒软件拦截

PyInstaller 单文件程序可能被误报。可先加入信任，或使用 Inno Setup 编译 `installer\setup.iss` 生成安装包分发。

## 五、升级与备份

程序数据优先保存在 exe 同级 `data\` 目录；如果该位置不可写，会自动回退到
`%LOCALAPPDATA%\TeachBuddy\data\`。升级前建议备份实际使用的数据目录：

```text
data\config.json
data\operation_log.json
data\templates\
```

替换 exe 后，直接双击启动；不需要导入旧配置。
