"""공개 조회 시 연락처를 가린다. 저장된 원문은 바꾸지 않는다."""

import re
import unicodedata

# 구분자: 공백·탭, 하이픈, 점, 밑줄, en/em dash 등. 최대 3자(예: " - ").
_SEP = r"[ \t.\-_‐-―−]{0,3}"

# 휴대폰(010/011/016/017/018/019) 10~11자리.
# - 국내형: 010-1234-5678, (010)1234-5678, 010)1234-5678
# - 국제형: +82 10-1234-5678, 82-10-1234-5678, +821012345678
# 더 긴 숫자열의 일부는 건드리지 않는다(앞뒤 숫자 인접 금지).
_MOBILE = re.compile(
    rf"""
    (?<!\d)
    (?:
        \+?82{_SEP}\(?0?\)?{_SEP}0?(?P<intl>1[016789])
        |
        \(?(?P<dom>01[016789])\)?
    )
    {_SEP}\d{{3,4}}{_SEP}\d{{4}}
    (?!\d)
    """,
    re.VERBOSE,
)


def _replace(match: re.Match[str]) -> str:
    prefix = match.group("dom") or "0" + match.group("intl")
    return f"{prefix}-****-****"


def mask_phones(text: str | None) -> str | None:
    if text is None:
        return None
    # 전각 숫자 등을 맞추기 위해 NFKC로 정규화한 사본에서 찾는다.
    # 연락처가 없으면 원문을 그대로 돌려준다.
    normalized = unicodedata.normalize("NFKC", text)
    masked, count = _MOBILE.subn(_replace, normalized)
    return masked if count else text
