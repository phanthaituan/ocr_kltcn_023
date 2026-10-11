"""
extract_unique_terms.py
Quét data/annotations/gold_parsed/ (chỉ ảnh thuộc core subset: has_ingredient & has_additive),
gom toàn bộ ingredient + additive DUY NHẤT, kèm tần suất xuất hiện, và 1 bản đã
làm sạch sơ bộ (bỏ % định lượng, bỏ tiền tố mô tả) - dùng làm "từ vựng mục tiêu"
để test khả năng match với FoodOn/Open Food Facts trước khi build Entity Linking đầy đủ.

Cách chạy (từ thư mục gốc project):
    python src/data_pipeline/extract_unique_terms.py
"""

import json
import re
import csv
import sys
import argparse
import unicodedata
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common.paths import GOLD_PARSED_DIR, UNIQUE_TERMS_CSV

# Các tiền tố mô tả thường gặp trước tên chất thật trong additive - bóc ra để lấy tên chất
DESCRIPTIVE_PREFIXES = [
    r"^chất nhũ hóa\s*:?\s*",
    r"^chất tạo màu tự nhiên\s*:?\s*",
    r"^chất tạo màu tổng hợp\s*:?\s*",
    r"^chất bảo quản\s*:?\s*",
    r"^chất tạo ngọt\s*:?\s*",
    r"^chất điều vị\s*:?\s*",
    r"^chất ổn định\s*:?\s*",
    r"^chất chống oxy hóa\s*:?\s*",
    r"^hương liệu tổng hợp\s*:?\s*",
    r"^hương liệu tự nhiên\s*:?\s*",
]


def clean_term(raw_term):
    """Chuẩn hóa NFC, bỏ % định lượng trong ngoặc, bỏ tiền tố mô tả, strip khoảng trắng."""
    t = unicodedata.normalize("NFC", raw_term)
    t_lower = t.lower().strip()

    for pattern in DESCRIPTIVE_PREFIXES:
        t_lower = re.sub(pattern, "", t_lower, flags=re.IGNORECASE)

    # bỏ phần % định lượng dạng (xx%) hoặc (xx,xxx%)
    t_lower = re.sub(r"\(\s*[\d.,]+\s*%\s*\)", "", t_lower)
    t_lower = re.sub(r"\s{2,}", " ", t_lower).strip(" .,:")

    return t_lower


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold_dir", default=str(GOLD_PARSED_DIR))
    parser.add_argument("--out_path", default=str(UNIQUE_TERMS_CSV))
    args = parser.parse_args()

    gold_dir = Path(args.gold_dir)
    json_files = sorted(gold_dir.glob("*.json"))
    if not json_files:
        print(f"[LỖI] Không tìm thấy file .json nào trong {gold_dir}")
        return

    ingredient_counter = Counter()
    additive_counter = Counter()
    n_core = 0

    for fp in json_files:
        with open(fp, "r", encoding="utf-8") as f:
            rec = json.load(f)

        if not (rec["completeness"]["has_ingredient"] and rec["completeness"]["has_additive"]):
            continue
        n_core += 1

        for term in rec["gold_ingredients_raw"]:
            ingredient_counter[clean_term(term)] += 1
        for term in rec["gold_additives_raw"]:
            additive_counter[clean_term(term)] += 1

    print(f"[INFO] Quét {n_core} ảnh thuộc core subset trên tổng {len(json_files)} file.")
    print(f"[INFO] Số ingredient duy nhất (sau làm sạch): {len(ingredient_counter)}")
    print(f"[INFO] Số additive duy nhất (sau làm sạch): {len(additive_counter)}")

    rows = []
    for term, count in ingredient_counter.most_common():
        rows.append({"term_type": "ingredient", "cleaned_term": term, "frequency": count})
    for term, count in additive_counter.most_common():
        rows.append({"term_type": "additive", "cleaned_term": term, "frequency": count})

    with open(args.out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["term_type", "cleaned_term", "frequency"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nĐã ghi {len(rows)} dòng vào {args.out_path}")
    print("\n15 ingredient xuất hiện nhiều nhất:")
    for term, count in ingredient_counter.most_common(15):
        print(f"  {term}: {count}")
    print("\n15 additive xuất hiện nhiều nhất:")
    for term, count in additive_counter.most_common(15):
        print(f"  {term}: {count}")


if __name__ == "__main__":
    main()