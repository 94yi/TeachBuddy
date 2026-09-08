"""AI 教案回复解析与纯文本格式清洗。"""

import re


DISCUSSION_MARK = "【讨论要点】"
LESSON_MARK = "【更新教案】"


def strip_markdown(text: str) -> str:
    """把常见 Markdown 标记转换为适合教案和 Word 导出的纯文本。"""
    lines = []
    in_code_block = False
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw.strip()
        if line.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            lines.append(raw)
            continue

        line = re.sub(r"^#{1,6}\s*", "", line)
        line = line.replace("**", "").replace("__", "")
        line = re.sub(r"(?<!\w)\*([^*\n]+)\*(?!\w)", r"\1", line)
        line = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", line)
        line = re.sub(r"`([^`]*)`", r"\1", line)
        line = re.sub(r"^\s*[-*+]\s+", "· ", line)
        line = re.sub(r"^\s*>\s?", "", line)
        line = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", line)
        lines.append(line.rstrip())

    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)
    return result.strip() + ("\n" if result else "")


def parse_discussion_response(text: str):
    """解析讨论要点和完整教案，兼容模型漏写标记的情况。"""
    cleaned = strip_markdown(text)
    discussion_pos = cleaned.find(DISCUSSION_MARK)
    lesson_pos = cleaned.find(LESSON_MARK)

    if discussion_pos >= 0 and lesson_pos > discussion_pos:
        discussion = cleaned[discussion_pos + len(DISCUSSION_MARK):lesson_pos].strip()
        lesson = cleaned[lesson_pos + len(LESSON_MARK):].strip()
        return discussion, lesson

    if lesson_pos >= 0:
        before = cleaned[:lesson_pos].strip()
        lesson = cleaned[lesson_pos + len(LESSON_MARK):].strip()
        return (before or "已根据讨论更新教案。"), lesson

    if discussion_pos >= 0:
        discussion = cleaned[discussion_pos + len(DISCUSSION_MARK):].strip()
        return discussion, ""

    heading = re.search(
        r"^[一二三四五六七八九十]+\s*、|^(教学目标|教学重难点|教学过程)\s*$",
        cleaned, re.MULTILINE)
    if heading:
        return "已根据讨论更新教案。", cleaned
    return cleaned, ""
