"""Kiem thu doc Model Registry (boto3 that) tren S3 gia lap bang moto."""
import os
import subprocess
import sys

import pytest
from moto.server import ThreadedMotoServer

from common import config, registry

SAMPLE = os.environ.get("ML_SAMPLE", os.path.join(os.path.dirname(__file__), "..", "ml", "sample_output"))
HERE = os.path.dirname(__file__)


@pytest.fixture
def s3(monkeypatch):
    srv = ThreadedMotoServer(port=5077, verbose=False)
    srv.start()
    monkeypatch.setattr(config, "MINIO_ENDPOINT", "http://127.0.0.1:5077")
    yield "http://127.0.0.1:5077"
    srv.stop()


def seed(endpoint, version, latest=False):
    args = [sys.executable, os.path.join(HERE, "seed_registry.py"), endpoint, SAMPLE, version]
    subprocess.run(args + (["latest"] if latest else []), check=True, capture_output=True)


def test_empty_registry(s3):
    import boto3
    boto3.client("s3", endpoint_url=s3, aws_access_key_id="a", aws_secret_access_key="b",
                 region_name="us-east-1").create_bucket(Bucket="warehouse")
    assert registry.list_versions() == []
    assert registry.resolve_deployed() == (None, None)


def test_fallback_then_latest(s3):
    seed(s3, "20261030T020521Z")
    seed(s3, "20261031T020000Z")
    assert registry.list_versions() == ["20261031T020000Z", "20261030T020521Z"]
    assert registry.resolve_deployed() == ("20261031T020000Z", "fallback")
    seed(s3, "20261030T020521Z", latest=True)
    assert registry.resolve_deployed() == ("20261030T020521Z", "latest")
    m = registry.load_metrics("20261030T020521Z")
    assert m["acceptance"]["passed"] is True
    fc = registry.get_csv(registry.version_key("20261030T020521Z", "forecast.csv"))
    assert list(fc.columns) == ["ds", "yhat", "yhat_lower", "yhat_upper"] and len(fc) == 30
    assert registry.get_csv(registry.version_key("x", "forecast.csv")) is None
