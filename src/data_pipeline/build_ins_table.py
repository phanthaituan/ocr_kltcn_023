"""
build_ins_table.py (v2: dùng ins_parser chung; có --keep_filled để KHÔNG mất phần ADI đã điền)
Từ unique_terms.csv -> tạo:
  1. adi_template.csv      : mỗi dòng 1 mã INS (base), kèm tần suất + ví dụ; các cột ADI để trống cho bạn điền
  2. additive_no_code.csv  : chuỗi additive KHÔNG có mã INS, kèm gợi ý phân loại

Cách chạy (từ thư mục gốc project):
    python src/data_pipeline/build_ins_table.py
    # Hoặc tùy biến:
    python src/data_pipeline/build_ins_table.py --terms data/interim/unique_terms.csv --out_dir data/kb [--keep_filled adi_da_dien.csv]
"""
import re, csv, sys, argparse
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.common.paths import UNIQUE_TERMS_CSV, KB_DIR
from ins_parser import parse_ins

FLAVOR_HINTS = ["hương", "vani", "flavour", "flavor", "aroma"]
FILL_COLS = ["substance_name", "adi_status", "adi_value_mg_per_kg_bw", "source", "notes"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--terms", default=str(UNIQUE_TERMS_CSV), help="File CSV chứa terms")
    ap.add_argument("--out_dir", default=str(KB_DIR), help="Thư mục xuất kết quả")
    ap.add_argument("--keep_filled", default="", help="File ADI cũ đã điền; giữ lại các cột đã điền theo ins_code")
    args = ap.parse_args()
    out_dir = Path(args.out_dir); out_dir.mkdir(exist_ok=True, parents=True)

    old = {}
    if args.keep_filled:
        with open(args.keep_filled, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                old[r["ins_code"].strip()] = r

    freq = defaultdict(int); variants = defaultdict(set); examples = defaultdict(list)
    no_code = []
    with open(args.terms, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["term_type"] != "additive":
                continue
            t, n = r["cleaned_term"].strip(), int(r["frequency"])
            codes = set(parse_ins(t))
            if codes:
                for base, var in codes:
                    freq[base] += n; variants[base].add(var)
                    if len(examples[base]) < 3:
                        examples[base].append(t)
            else:
                no_code.append((t, n))

    kept = 0
    with open(out_dir / "adi_template.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["ins_code", "e_number", "variants_seen", "frequency", "example_strings"] + FILL_COLS)
        for base, n in sorted(freq.items(), key=lambda x: -x[1]):
            prev = old.get(base, {})
            vals = [prev.get(c, "") for c in FILL_COLS]
            kept += any(v.strip() for v in vals)
            w.writerow([base, "E" + base.upper(), "; ".join(sorted(variants[base])), n,
                        " | ".join(examples[base])] + vals)

    lost = [c for c, r in old.items() if c not in freq and any((r.get(k) or "").strip() for k in FILL_COLS)]

    with open(out_dir / "additive_no_code.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["cleaned_term", "frequency", "suggested_class", "your_decision"])
        for t, n in sorted(no_code, key=lambda x: -x[1]):
            cls = ("EMPTY_after_cleaning (kiểm tra chuỗi gốc)" if t == ""
                   else "flavor" if any(h in t for h in FLAVOR_HINTS) else "review")
            w.writerow([t, n, cls, ""])

    print(f"Mã INS duy nhất (base): {len(freq)}  -> {out_dir}/adi_template.csv")
    print(f"Chuỗi additive không có mã INS: {len(no_code)} -> {out_dir}/additive_no_code.csv")
    if args.keep_filled:
        print(f"Giữ lại {kept} dòng đã điền từ {args.keep_filled}")
        if lost:
            print(f"[!] Các mã đã điền nhưng KHÔNG còn trong template mới (kiểm tra thủ công): {lost}")


if __name__ == "__main__":
    main()