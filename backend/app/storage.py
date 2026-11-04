import re
from pathlib import Path, PurePosixPath
from typing import Protocol

import boto3

from app.config import Settings

_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


class MediaStorage(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...

    def open(self, key: str) -> bytes: ...

    # 없는 키를 삭제해도 오류가 나지 않는다.
    def delete(self, key: str) -> None: ...


def media_key(org_slug: str, media_id: str, ext: str) -> str:
    return f"instagram/{org_slug}/{media_id}.{ext}"


def _validate_key(key: str) -> None:
    # 빈 키, 절대경로, Windows 드라이브 경로, 백슬래시, `..` 세그먼트를 거부한다.
    if (
        not key
        or "\\" in key
        or _DRIVE_PREFIX.match(key)
        or PurePosixPath(key).is_absolute()
        or ".." in PurePosixPath(key).parts
    ):
        raise ValueError(f"invalid storage key: {key!r}")


class LocalStorage:
    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir

    def _path(self, key: str) -> Path:
        _validate_key(key)
        base = self._base_dir.resolve()
        resolved = (base / key).resolve()
        if not resolved.is_relative_to(base):
            raise ValueError(f"storage key escapes base directory: {key!r}")
        return resolved

    def put(self, key: str, data: bytes, content_type: str) -> None:
        # 로컬 파일시스템은 content_type을 저장하지 않는다.
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def open(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)


class NcpStorage:
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket: str) -> None:
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="kr-standard",
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        _validate_key(key)
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data, ContentType=content_type)

    def open(self, key: str) -> bytes:
        _validate_key(key)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.NoSuchKey as exc:
            # LocalStorage와 같은 예외로 맞춘다. 호출 측은 FileNotFoundError만 처리하면 된다.
            raise FileNotFoundError(key) from exc
        return response["Body"].read()

    def delete(self, key: str) -> None:
        _validate_key(key)
        self._client.delete_object(Bucket=self._bucket, Key=key)


def make_storage(settings: Settings) -> MediaStorage:
    if settings.media_storage == "ncp":
        return NcpStorage(
            endpoint=settings.ncp_object_storage_endpoint,
            access_key=settings.ncp_access_key,
            secret_key=settings.ncp_secret_key,
            bucket=settings.ncp_bucket_name,
        )
    return LocalStorage(Path(settings.media_local_dir))
