"""
review_unmatched.py
Quét data/annotations/gold_parsed/ (output của parse_vifoodlabel.py), tìm các record có
warning nhưng KHÔNG match được từ khóa dị ứng nào trong ALLERGEN_KEYWORDS -> xuất ra
CSV để review thủ công, giúp mở rộng/tinh chỉnh danh sách từ khóa dị ứng.

Dùng allergen_debug["named_in_warning"] (chỉ tính từ câu warning, không tính phần suy luận
từ ingredient/additive) để giữ đúng ý nghĩa "warning chưa match từ khóa".

Cách chạy (từ thư mục gốc project):
    python src/data_pipeline/review_unmatched.py
"""

import json
import csv
import sys
import argparse
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common.paths import GOLD_PARSED_DIR, UNMATCHED_WARNINGS_CSV


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold_dir", default=str(GOLD_PARSED_DIR))
    parser.add_argument("--out_path", default=str(UNMATCHED_WARNINGS_CSV))
    args = parser.parse_args()

    gold_dir = Path(args.gold_dir)
    rows = []
    word_counter = Counter()

    for fp in sorted(gold_dir.glob("*.json")):
        with open(fp, "r", encoding="utf-8") as f:
            rec = json.load(f)

        if not rec["completeness"]["has_warning"]:
            continue

        if len(rec["allergen_debug"]["named_in_warning"]) == 0:
            for w in rec["gold_warning_raw"]:
                rows.append({"image_id": rec["image_id"], "unmatched_warning_text": w})
                # đếm từ để gợi ý từ khóa mới cần thêm
                for token in w.lower().replace(".", "").replace(",", "").split():
                    word_counter[token] += 1

    Path(args.out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["image_id", "unmatched_warning_text"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"Đã ghi {len(rows)} dòng warning chưa match vào {args.out_path}")
    print("\nTop 30 từ xuất hiện nhiều nhất trong các warning chưa match (gợi ý xem có phải từ khóa dị ứng còn thiếu không):")
    for word, count in word_counter.most_common(30):
        print(f"  {word}: {count}")


if __name__ == "__main__":
    main()