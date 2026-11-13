"""
registry.py - Model Registry toi gian tren MinIO (giao thuc S3)

Cau truc luu tru trong bucket "warehouse":
    models/prophet_revenue/<version>/model.pkl          mo hinh Prophet da huan luyen (pickle)
    models/prophet_revenue/<version>/model.json         ban sao dang JSON (doc duoc khi khac phien ban Python)
    models/prophet_revenue/<version>/metrics.json       chi so danh gia, tham so tot nhat, ket qua nghiem thu
    models/prophet_revenue/<version>/forecast.csv       du bao 30 ngay (yhat, yhat_lower, yhat_upper)
    models/prophet_revenue/<version>/test_predictions.csv
    models/prophet_revenue/latest.json                  con tro toi phien ban dang dung (chi cap nhat khi dat nghiem thu)
"""
import json
import pickle

import boto3
from botocore.client import Config

import config


def client():
    return boto3.client(
        "s3",
        endpoint_url=config.MINIO_ENDPOINT,
        aws_access_key_id=config.MINIO_ACCESS_KEY,
        aws_secret_access_key=config.MINIO_SECRET_KEY,
        region_name="us-east-1",
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def version_key(version: str, name: str) -> str:
    return f"{config.REGISTRY_PREFIX}/{version}/{name}"


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream") -> None:
    client().put_object(Bucket=config.BUCKET, Key=key, Body=data, ContentType=content_type)


def get_bytes(key: str) -> bytes:
    return client().get_object(Bucket=config.BUCKET, Key=key)["Body"].read()


def put_json(key: str, obj: dict) -> None:
    put_bytes(key, json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8"), "application/json")


def get_json(key: str) -> dict:
    return json.loads(get_bytes(key).decode("utf-8"))


def list_versions() -> list:
    """Danh sach phien ban da huan luyen, moi nhat truoc (phuc vu tab Lich su huan luyen cua Streamlit)."""
    prefix = config.REGISTRY_PREFIX + "/"
    paginator = client().get_paginator("list_objects_v2")
    versions = set()
    for page in paginator.paginate(Bucket=config.BUCKET, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes", []):
            versions.add(cp["Prefix"][len(prefix):].strip("/"))
    return sorted(versions, reverse=True)


def promote(version: str, metrics: dict) -> None:
    """Dat phien ban nay lam mo hinh dang trien khai."""
    put_json(config.LATEST_KEY, {
        "version": version,
        "trained_at": metrics["trained_at"],
        "tuned_wape": metrics["tuned_prophet"]["wape"],
        "model_key": version_key(version, "model.pkl"),
    })


def load_model(version: str = "latest"):
    """Nap mo hinh tu registry (dung cho ung dung Streamlit / Agent)."""
    if version == "latest":
        version = get_json(config.LATEST_KEY)["version"]
    return pickle.loads(get_bytes(version_key(version, "model.pkl")))
