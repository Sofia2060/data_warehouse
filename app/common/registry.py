"""
registry.py - Doc (chi doc) Model Registry tren MinIO do pipeline Prophet (muc 3.8) ghi ra.

Cau truc do ml/registry.py tao:
    models/prophet_revenue/<version>/metrics.json        chi so danh gia, tham so, ket qua nghiem thu
    models/prophet_revenue/<version>/forecast.csv        du bao 30 ngay (ds, yhat, yhat_lower, yhat_upper)
    models/prophet_revenue/<version>/test_predictions.csv
    models/prophet_revenue/latest.json                   con tro toi phien ban dang trien khai
"""
import io
import json

import boto3
import pandas as pd
from botocore.client import Config
from botocore.exceptions import ClientError

from common import config


def _client():
    return boto3.client(
        "s3",
        endpoint_url=config.MINIO_ENDPOINT,
        aws_access_key_id=config.MINIO_ACCESS_KEY,
        aws_secret_access_key=config.MINIO_SECRET_KEY,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"},
                      connect_timeout=5, read_timeout=20, retries={"max_attempts": 2}),
    )


def _get_bytes(key: str) -> bytes:
    return _client().get_object(Bucket=config.MODEL_BUCKET, Key=key)["Body"].read()


def _exists_error(exc: ClientError) -> bool:
    return exc.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound")


def get_json(key: str):
    """Doc mot file JSON; tra ve None neu file khong ton tai."""
    try:
        return json.loads(_get_bytes(key).decode("utf-8"))
    except ClientError as exc:
        if _exists_error(exc):
            return None
        raise


def get_csv(key: str):
    try:
        return pd.read_csv(io.BytesIO(_get_bytes(key)))
    except ClientError as exc:
        if _exists_error(exc):
            return None
        raise


def version_key(version: str, name: str) -> str:
    return f"{config.REGISTRY_PREFIX}/{version}/{name}"


def list_versions() -> list:
    """Cac phien ban da huan luyen, moi nhat truoc (ten phien ban dang YYYYMMDDTHHMMSSZ)."""
    prefix = config.REGISTRY_PREFIX + "/"
    versions = set()
    for page in _client().get_paginator("list_objects_v2").paginate(
            Bucket=config.MODEL_BUCKET, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            versions.add(cp["Prefix"][len(prefix):].strip("/"))
    return sorted(versions, reverse=True)


def load_metrics(version: str):
    return get_json(version_key(version, "metrics.json"))


def resolve_deployed():
    """Xac dinh phien ban mo hinh dung de phuc vu.

    Tra ve (version, nguon): nguon = "latest" neu doc tu latest.json; "fallback" neu chua co
    latest.json va phai dung phien ban moi nhat da dat nghiem thu; (None, None) neu registry trong.
    """
    latest = get_json(config.LATEST_KEY)
    if latest and latest.get("version"):
        return latest["version"], "latest"
    for v in list_versions():
        m = load_metrics(v)
        if m and m.get("acceptance", {}).get("passed"):
            return v, "fallback"
    return None, None
