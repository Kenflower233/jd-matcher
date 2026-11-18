"""隐私脱敏测试。"""
from src.privacy import redact_personal_info


def test_redacts_common_personal_information_and_restores_it():
    original = (
        "电话：13812345678\n"
        "邮箱：student@example.com\n"
        "身份证号：110101200001011234\n"
        "现居地：北京市海淀区某街道88号"
    )
    result = redact_personal_info(original)
    assert result.total == 4
    assert "13812345678" not in result.text
    assert "student@example.com" not in result.text
    assert "110101200001011234" not in result.text
    assert "某街道88号" not in result.text
    assert result.restore(result.text) == original


def test_text_without_personal_information_is_unchanged():
    original = "使用Python完成数据分析项目"
    result = redact_personal_info(original)
    assert result.text == original
    assert result.total == 0


def test_missing_placeholders_are_reported():
    result = redact_personal_info("邮箱：student@example.com")
    assert len(result.missing_placeholders("邮箱已隐藏")) == 1


def test_project_and_company_addresses_are_not_treated_as_home_address():
    original = "项目地址：https://example.com\n公司地址：上海分公司"
    result = redact_personal_info(original)
    assert result.text == original
    assert result.total == 0
