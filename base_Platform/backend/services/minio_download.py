"""
MinIO 对象下载：供 AnalysisFilePrepareService staging 使用。

默认 endpoint/凭证与 backend/app.py 保持一致，避免单独配置导致 stage 失败。
"""

from __future__ import annotations

import os
from pathlib import Path

import boto3
from botocore.client import Config


def _minio_client():
    endpoint = (os.getenv("MINIO_ENDPOINT") or "http://111.228.12.207:9000").strip()
    access_key = (os.getenv("MINIO_ACCESS_KEY") or "minioadmin").strip()
    secret_key = (os.getenv("MINIO_SECRET_KEY") or "Minio@123456").strip()
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def download_object_to_file(*, bucket: str, key: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    client = _minio_client()
    client.download_file(bucket, key, str(dest))
    return dest
