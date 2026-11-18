"""文件解析：从上传文件（PDF/DOCX/TXT/MD）提取纯文本。"""
from pathlib import Path

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024


class FileParseError(Exception):
    """文件解析失败，message面向用户可读。"""


def _parse_pdf(path: Path) -> str:
    import fitz  # PyMuPDF

    with fitz.open(path) as doc:
        return "\n".join(page.get_text() for page in doc)


def _parse_docx(path: Path) -> str:
    import docx  # python-docx

    doc = docx.Document(path)
    lines = [p.text for p in doc.paragraphs if p.text.strip()]
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _parse_plain_text(path: Path) -> str:
    """优先按UTF-8读取，并兼容常见中文Windows编码。"""
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise FileParseError("文本文件编码无法识别，请另存为 UTF-8 后重试")


def parse_file(path: str | Path) -> str:
    """按扩展名解析文件为纯文本；空内容或不支持的格式抛FileParseError。"""
    path = Path(path)
    if not path.exists() or not path.is_file():
        raise FileParseError("文件不存在或无法访问")
    try:
        if path.stat().st_size > MAX_FILE_SIZE:
            raise FileParseError("文件超过 10MB，请压缩或精简后重试")
    except OSError as e:
        raise FileParseError(f"无法读取文件信息：{e}") from e
    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise FileParseError(f"不支持的文件格式 {ext}，请使用：{', '.join(sorted(SUPPORTED_EXTENSIONS))}")
    try:
        if ext in (".txt", ".md"):
            text = _parse_plain_text(path)
        elif ext == ".pdf":
            text = _parse_pdf(path)
        else:
            text = _parse_docx(path)
    except FileParseError:
        raise
    except Exception as e:
        raise FileParseError(f"文件解析失败：{e}") from e
    if not text.strip():
        raise FileParseError("未能从文件中提取到文字内容（可能是扫描件图片）")
    return text.strip()
