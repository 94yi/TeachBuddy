# 讲话稿

讲话稿提供开学典礼、家长会、教研活动、工作会议、活动致辞五种预设，以及“其他场合”。选择“其他场合”后填写具体用途，例如婚礼致辞、志愿者交流或情况通报，不受教育场景限制。可选择庄重正式、亲切自然或鼓舞激励的语气，填写标题、发言人、听众和核心要点后生成中文初稿，继续编辑、保存并导出 Word 或 TXT。

离线模式不访问网络，不编造学校名称、人数、成绩、获奖或新闻。五种预设使用各自的场合模板；**“其他场合”使用通用模板初稿，可编辑调整，不会智能判断并适配具体场合的含义、礼仪或情感**。例如填写“婚礼致辞”会保留这个名称及所填要点，但不会自动补出新人故事；情况通报、追思等用途同样需要核对称谓、语气与具体内容。发言人身份用于稿件署名，正文视角也需结合实际核对。

用户填写的核心要点会按顺序保留。附加写作要求属于编辑指令，不会被直接塞进朗读正文；离线模式填写这些要求时，用保存在历史中的 `editing_note` 提醒用户在编辑区核对，或切换 AI 模式进一步调整。AI 模式会将附加要求交给现有 AI 服务执行。

短篇、中篇、长篇分别以约 600、1000、1500 字为参考。核心要点本身很长时，优先保留用户信息，最终字数可能超过参考值。生成的稿件是可编辑初稿，用户提供的具体事实不会由离线模板核验。

## 接口

所有接口沿用现有登录和 `X-TeachBuddy-Request: 1` 校验。

`POST /api/speech/generate` 接收：

```json
{
  "title": "携手支持孩子成长",
  "occasion": "家长会",
  "speaker": "班主任",
  "audience": "各位家长",
  "tone": "亲切自然",
  "length": "medium",
  "key_points": "重视亲子阅读\n保持及时沟通",
  "requirements": "少用书面语",
  "mode": "offline"
}
```

- `title` 必填，1–200 字符。
- `occasion`：`开学典礼 / 家长会 / 教研活动 / 工作会议 / 活动致辞 / 其他场合`，默认 `工作会议`。
- `custom_occasion`：具体场合名称，去掉前后空白后最多 100 字符；仅选择 `其他场合` 时必填，空串和全空白会返回 422。预设场合不需要此字段，浏览器切回预设时会隐藏并停用输入，不再将其提交或作为必填项。
- `speaker` 最大 100 字符，`audience` 最大 200 字符，默认空。
- `tone`：`庄重正式 / 亲切自然 / 鼓舞激励`，默认 `庄重正式`。
- `length`：`short / medium / long`，默认 `medium`。
- `key_points` 为多行字符串，最大 6000 字符；`requirements` 最大 2000 字符。
- `mode`：`offline / ai`，默认 `offline`。

例如，自定义场合的请求可以写为：

```json
{
  "title": "携手相伴，共赴未来",
  "occasion": "其他场合",
  "custom_occasion": "婚礼致辞",
  "speaker": "新郎的朋友",
  "audience": "各位亲友",
  "tone": "亲切自然",
  "length": "short",
  "key_points": "感谢亲友到场\n祝愿新人相互支持",
  "mode": "offline"
}
```

成功响应为 `{id,title,body,mode,kind:"speech",created_at}`，离线稿有附加要求时还返回 `editing_note`。生成成功会自动保存历史。

AI 模式复用 `AI_BASE_URL / AI_API_KEY / AI_MODEL` 及现有超时、并发、速率限制，具体场合名称会随请求交给 AI。不配置 AI 时明确返回 503，不把离线结果冒充 AI 结果。提供商错误不会把密钥或内部响应暴露给前端。

## 编辑、优化与历史兼容

- 保存编辑：`POST /api/history`，传 `{title,body,kind:"speech"}`；可携带已有的 `editing_note` 保留编辑提示。
- 讲话稿列表：`GET /api/history?kind=speech`。
- 教案列表：原来的 `GET /api/history` 保持默认只返回教案；`?kind=lesson` 等价。旧文件缺少 `kind` 时按教案处理。
- 两类历史分别保留当前浏览器会话最近 20 条，互不挤占；退出或清除会话后不再访问旧会话的私人历史。
- AI 优化：沿用 `POST /api/lesson/revise`，传 `{title,body,instruction,kind:"speech"}`，使用讲话稿专用提示并保存新的讲话稿历史。省略 `kind` 保持原教案优化逻辑。
- 删除：`DELETE /api/history/{id}`，仍校验会话归属。
- Word/TXT：沿用 `POST /api/export`，传 `{title,body,format:"docx"}` 或 `format:"txt"`。

测试 `tests/test_speech.py` 覆盖五种预设和其他场合、篇幅、语气和用户要点、字段长度、自定义名称的空值与空白校验、鉴权和 CSRF、AI 请求模拟及故障、旧历史兼容、分类保留、会话隔离和 Word/TXT 文件内容；不调用外部 AI。

`tests/speech_browser_smoke.py` 使用临时本地实例和真实 Chrome，验证自定义场合空白阻止提交、婚礼致辞名称与要点保留、切回预设正常生成、编辑保存与复制、Word/TXT 导出、历史恢复与删除，以及 320px 和 390px 界面的自定义输入可见性和无横向溢出。临时自定义稿验证完即删除，不影响后续历史计数；产物写入项目 `artifacts` 目录。
