# 教伴 —— 教学办公助手

面向 Win7 老旧办公电脑的桌面工具：文件整理（预览→确认→执行→可撤销、扩展名/文件名关键词规则自定义、操作历史）、重复文件检测（MD5 核验、重复项移入待删区、可撤销）、教案撰写（离线模板 / 导入自定义模板 .json/.docx/.txt/.md / AI 生成初稿 / AI 讨论改稿 / Word 导出 / 基础 PPT 导出 / 样例与知识库导入）、AI 对话（多轮问答、气泡样式）。首次启动有引导页，可配置 AI 或跳过离线使用。

## 技术栈

- Python 3.8.10（Win7 支持的最后版本，勿用 3.9+）
- PyQt5 5.15（界面）
- requests（AI 接口，OpenAI 兼容格式）
- python-docx（Word 导出）
- python-pptx（PPT 导出）
- PyInstaller（打包 exe）+ Inno Setup（安装向导，可选）

AI 运行时支持任意 OpenAI 兼容接口、连接测试、超时控制和主/备服务商自动回退；文件移动等敏感操作必须由用户确认并可撤销。

## 本地运行

```bat
pip install -r requirements.txt
python main.py
```

## 打包 Win7 可用 exe

1. 在目标位数一致的环境安装 **Python 3.8.10**（老机器多为 32 位 Win7，则装 32 位 Python）。
2. 执行 `set TARGET_BITS=32` 后运行 `build_exe.bat`；脚本会强制校验 Python 3.8.10 和位数，产物在 `dist\TeachBuddy.exe`。
3. 把 `dist\TeachBuddy.exe` 单文件直接发给老师即可绿色使用；
   如需安装向导，运行 `build_installer.bat`，产物位于
   `installer\Output\TeachBuddySetup.exe`。

### 内置 AI 配置版

当前构建流程会把 `data\config.json` 作为默认 AI 配置嵌入 exe。单发
`TeachBuddy.exe` 或安装包均可直接读取该配置；用户之后在「设置」页保存的配置
优先级更高。内置 API Key 可被具备技术能力的用户提取，仅限受控范围分发。
`data\config.json` 已被 Git 忽略；首次构建可复制 `data\config.example.json`
并填入本机配置。不要把真实密钥、绿色版或安装包提交到公开仓库。

## Win7 注意事项

- 系统必须打到 Win7 SP1 并安装基础安全补丁（TLS 1.2 支持，AI 联网必需）。
- 打包机与目标机位数保持一致（32 位更保险）。
- 已内置 AI 配置时可直接使用；服务失效后可在「设置」页更新。不联网仍能使用离线教案模板。
- 程序产生的配置与操作日志优先保存在 exe 同级 `data\` 目录；目录不可写时自动回退到 `%LOCALAPPDATA%\TeachBuddy\data\`，避免因权限问题无法启动。
- 详细安装步骤、实机验收清单和常见故障处理见 `docs/WIN7.md`。
