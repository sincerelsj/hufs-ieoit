import pytest

from app.archive.masking import mask_phones


@pytest.mark.parametrize(
    "text",
    ["010-1234-5678", "01012345678", "010 1234 5678", "011-123-4567"],
)
def test_mask_phones_masks_mobile_numbers(text):
    masked = mask_phones(text)
    assert "****" in masked
    assert not any(ch.isdigit() for ch in masked.replace("010", "").replace("011", ""))


def test_mask_phones_output_format():
    assert mask_phones("010-1234-5678") == "010-****-****"
    assert mask_phones("01012345678") == "010-****-****"
    assert mask_phones("010 1234 5678") == "010-****-****"
    assert mask_phones("011-123-4567") == "011-****-****"


def test_mask_phones_keeps_landline_and_surrounding_text():
    assert mask_phones("02-2173-3241") == "02-2173-3241"
    assert (
        mask_phones("문의: 010-1234-5678 / 사무실 02-2173-3241")
        == "문의: 010-****-**** / 사무실 02-2173-3241"
    )


def test_mask_phones_does_not_touch_longer_digit_runs():
    assert mask_phones("0101234567890") == "0101234567890"


def test_mask_phones_none_and_empty():
    assert mask_phones(None) is None
    assert mask_phones("") == ""


@pytest.mark.parametrize(
    "text",
    [
        "010.1234.5678",
        "010 - 1234 - 5678",
        "010_1234_5678",
        "010–1234–5678",
        "010—1234—5678",
        "(010)1234-5678",
        "010)1234-5678",
        "+82 10-1234-5678",
        "+82-10-1234-5678",
        "82-10-1234-5678",
        "+821012345678",
        "０１０-１２３４-５６７８",
    ],
)
def test_mask_phones_masks_common_formats(text):
    assert mask_phones(text) == "010-****-****"
    assert mask_phones(f"문의 {text} 로 연락") == "문의 010-****-**** 로 연락"


@pytest.mark.parametrize(
    "text",
    [
        "02-2173-3241",
        "031-123-4567",
        "2026.11.02",
        "2026-11-02",
        "0101234567890123",
        "1012345678",
    ],
)
def test_mask_phones_leaves_non_phone_numbers(text):
    assert mask_phones(text) == text


def test_mask_phones_returns_original_text_when_nothing_matched():
    text = "１２３ 안내 ①"  # 전각 숫자·원문자는 연락처가 없으면 그대로
    assert mask_phones(text) == text
