"""file_parser模块测试：txt/docx/pdf解析、异常路径。"""
import docx
import fitz
import pytest

from src.file_parser import FileParseError, parse_file


def test_parse_txt(tmp_path):
    f = tmp_path / "resume.txt"
    f.write_text("张三的简历", encoding="utf-8")
    assert parse_file(f) == "张三的简历"


def test_parse_docx(tmp_path):
    f = tmp_path / "resume.docx"
    doc = docx.Document()
    doc.add_paragraph("五年Python经验")
    doc.save(f)
    assert "五年Python经验" in parse_file(f)


def test_parse_docx_includes_tables(tmp_path):
    f = tmp_path / "resume.docx"
    doc = docx.Document()
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "技能"
    table.cell(0, 1).text = "Python"
    doc.save(f)
    parsed = parse_file(f)
    assert "技能" in parsed and "Python" in parsed


def test_parse_pdf(tmp_path):
    f = tmp_path / "resume.pdf"
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "data analyst resume")
    doc.save(f)
    doc.close()
    assert "data analyst" in parse_file(f)


def test_unsupported_extension_rejected(tmp_path):
    f = tmp_path / "resume.exe"
    f.write_bytes(b"MZ")
    with pytest.raises(FileParseError, match="不支持的文件格式"):
        parse_file(f)


def test_empty_file_rejected(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("   ", encoding="utf-8")
    with pytest.raises(FileParseError, match="未能从文件中提取到文字"):
        parse_file(f)


def test_gb18030_text_is_supported(tmp_path):
    f = tmp_path / "resume.txt"
    f.write_bytes("中文简历".encode("gb18030"))
    assert parse_file(f) == "中文简历"


def test_missing_file_has_friendly_error(tmp_path):
    with pytest.raises(FileParseError, match="不存在"):
        parse_file(tmp_path / "missing.txt")
