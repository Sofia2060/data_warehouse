"""Nap file mau cua pipeline Prophet (ml/sample_output) vao S3 gia lap, dung dung cau truc ml/registry.py."""
import json
import os
import sys

import boto3

endpoint, sample_dir, version = sys.argv[1], sys.argv[2], sys.argv[3]
write_latest = len(sys.argv) > 4 and sys.argv[4] == "latest"
s3 = boto3.client("s3", endpoint_url=endpoint, aws_access_key_id="admin", aws_secret_access_key="password",
                  region_name="us-east-1")
try:
    s3.create_bucket(Bucket="warehouse")
except s3.exceptions.BucketAlreadyOwnedByYou:
    pass
prefix = f"models/prophet_revenue/{version}"
for name in ["metrics.json", "forecast.csv", "test_predictions.csv"]:
    if not os.path.exists(os.path.join(sample_dir, name)):   # test_predictions.csv khong bat buoc
        continue
    with open(os.path.join(sample_dir, name), "rb") as f:
        s3.put_object(Bucket="warehouse", Key=f"{prefix}/{name}", Body=f.read())
if write_latest:
    m = json.load(open(os.path.join(sample_dir, "metrics.json"), encoding="utf-8"))
    s3.put_object(Bucket="warehouse", Key="models/prophet_revenue/latest.json",
                  Body=json.dumps({"version": version, "trained_at": m["trained_at"],
                                   "tuned_wape": m["tuned_prophet"]["wape"],
                                   "model_key": f"{prefix}/model.pkl"}).encode())
print("seeded", version, "latest" if write_latest else "")
