"""공개 조회 시 연락처를 가린다. 저장된 원문은 바꾸지 않는다."""

import re

# 휴대폰(010/011/016/017/018/019) 10~11자리. 하이픈·공백 허용. 더 긴 숫자열의 일부는 건드리지 않는다.
_MOBILE = re.compile(r"(?<!\d)(01[016789])[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)")


def mask_phones(text: str | None) -> str | None:
    if text is None:
        return None
    return _MOBILE.sub(r"\1-****-****", text)
