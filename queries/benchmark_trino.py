"""
benchmark_trino.py - Do hieu nang truy van Gold Layer qua Trino (muc 3.6.5)

Doc cac truy van trong queries/truy_van_mau.sql, chay moi truy van 1 lan khoi dong (warm-up, khong tinh)
roi N lan do. Ghi thoi gian tuong (wall) phia client va so lieu do chinh Trino bao cao.

Cach chay tren may host (Trino map cong 8090):
    pip install trino
    python queries/benchmark_trino.py --runs 5
Ket qua: bang Markdown in ra man hinh + file queries/benchmark_result.csv (de dua vao bao cao).
"""
import argparse
import csv
import os
import re
import statistics
import time

import trino

HERE = os.path.dirname(os.path.abspath(__file__))


def load_queries(path: str) -> list:
    """Tach file SQL theo dong tieu de '-- [Qn] Ten | Loai'."""
    text = open(path, encoding="utf-8").read()
    pattern = re.compile(r"^-- \[(Q\d+)\] (.+?) \| (.+?)$", re.MULTILINE)
    matches = list(pattern.finditer(text))
    queries = []
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sql = text[m.end():end].strip().rstrip(";").strip()
        queries.append({"id": m.group(1), "name": m.group(2), "kind": m.group(3), "sql": sql})
    return queries


def run_once(cur, sql: str) -> dict:
    t0 = time.perf_counter()
    cur.execute(sql)
    rows = cur.fetchall()
    wall_ms = (time.perf_counter() - t0) * 1000
    stats = cur.stats or {}
    return {"wall_ms": wall_ms, "rows": len(rows),
            "trino_elapsed_ms": stats.get("elapsedTimeMillis", 0),
            "trino_cpu_ms": stats.get("cpuTimeMillis", 0),
            "processed_rows": stats.get("processedRows", 0),
            "processed_mb": stats.get("processedBytes", 0) / 1e6}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8090)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--sql", default=os.path.join(HERE, "truy_van_mau.sql"))
    parser.add_argument("--out", default=os.path.join(HERE, "benchmark_result.csv"))
    args = parser.parse_args()

    conn = trino.dbapi.connect(host=args.host, port=args.port, user="benchmark", catalog="iceberg")
    cur = conn.cursor()
    results = []
    for q in load_queries(args.sql):
        run_once(cur, q["sql"])                                  # warm-up
        runs = [run_once(cur, q["sql"]) for _ in range(args.runs)]
        walls = [r["wall_ms"] for r in runs]
        results.append({
            "id": q["id"], "name": q["name"], "kind": q["kind"], "result_rows": runs[-1]["rows"],
            "processed_rows": runs[-1]["processed_rows"], "processed_mb": round(runs[-1]["processed_mb"], 1),
            "avg_ms": round(statistics.mean(walls)), "min_ms": round(min(walls)), "max_ms": round(max(walls)),
            "stdev_ms": round(statistics.pstdev(walls)),
            "trino_cpu_ms": round(statistics.mean(r["trino_cpu_ms"] for r in runs)),
        })
        print(f"{q['id']:>4} {results[-1]['avg_ms']:>7} ms  {q['name']}", flush=True)

    with open(args.out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(results[0]))
        writer.writeheader()
        writer.writerows(results)

    print(f"\n| Truy van | Loai | So dong doc | TB (ms) | Min | Max | Do lech chuan |")
    print("|---|---|---:|---:|---:|---:|---:|")
    for r in results:
        print(f"| {r['id']} {r['name']} | {r['kind']} | {r['processed_rows']:,} | {r['avg_ms']:,} | "
              f"{r['min_ms']:,} | {r['max_ms']:,} | {r['stdev_ms']:,} |")
    print(f"\nDa ghi {args.out} ({args.runs} lan do moi truy van, bo 1 lan warm-up)")


if __name__ == "__main__":
    main()
