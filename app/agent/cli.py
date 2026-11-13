"""
cli.py - Chay Agent tu dong lenh (phuc vu kiem thu muc 4.4).

    docker exec -it groq-agent python -m agent.cli "Top 5 best-selling products?"
    docker exec -it groq-agent python -m agent.cli --demo      # chay 3 kich ban kiem thu
"""
import sys

from agent import core

DEMO_QUESTIONS = [
    "Top 5 best-selling products?",
    "Ngoài Vương quốc Anh, quốc gia nào đóng góp doanh thu xuất khẩu lớn nhất? Liệt kê top 5.",
    "Phân nhóm sản phẩm theo Pareto A-B-C: nhóm A chiếm 80% doanh thu, B 15%, C 5%. Mỗi nhóm có bao nhiêu sản phẩm và bao nhiêu doanh thu?",
]


def show(res: dict) -> None:
    print("=" * 80)
    print("Câu hỏi :", res["question"])
    print("SQL     :", res["sql"])
    print(f"Số dòng : {res['row_count']} | Số lần thử: {res['attempts']} | Thời gian: {res['elapsed_s']} s")
    if res["rows"]:
        print(" | ".join(res["columns"]))
        for row in res["rows"][:10]:
            print(" | ".join(str(v) for v in row))
    print("Trả lời :", res["answer"] or "")
    if res["error"]:
        print("LỖI    :", res["error"])


def main(argv) -> int:
    questions = DEMO_QUESTIONS if (not argv or argv[0] == "--demo") else [" ".join(argv)]
    ok = True
    for q in questions:
        res = core.ask(q)
        show(res)
        ok = ok and res["ok"]
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
