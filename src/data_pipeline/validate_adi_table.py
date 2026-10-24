"""
validate_adi_table.py
Kiểm tra file bảng ADI (adi_template.csv sau khi bạn điền) trước khi dùng để tạo nhãn.

Cách chạy:
    python validate_adi_table.py --csv data/adi/adi_table.csv
"""
import argparse, csv, re, sys
from collections import Counter

ALLOWED = {"numeric", "not_specified", "unknown"}
REQUIRED_COLS = ["ins_code", "frequency", "substance_name", "adi_status",
                 "adi_value_mg_per_kg_bw", "source", "notes"]


def suggest_status(raw, value):
    r = re.sub(r"[\s\-]+", "_", raw.strip().lower())
    if r in ALLOWED:
        return r
    if r == "specified" and value.strip():
        return "numeric"
    if r in ("not_limited", "no_limit"):
        return "not_specified"
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    args = ap.parse_args()

    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        print("File rỗng."); sys.exit(1)
    missing = [c for c in REQUIRED_COLS if c not in rows[0]]
    if missing:
        print("Thiếu cột:", missing); sys.exit(1)

    errors, warns = [], []
    status_count = Counter()
    filled_freq = total_freq = 0

    for i, r in enumerate(rows, start=2):          # dòng 1 là header
        code = r["ins_code"]
        freq = int(r["frequency"] or 0)
        total_freq += freq
        st = r["adi_status"].strip()
        val = r["adi_value_mg_per_kg_bw"].strip()
        if not st:
            status_count["(chưa điền)"] += 1
            continue
        filled_freq += freq

        if st not in ALLOWED:
            fix = suggest_status(st, val)
            hint = f" -> nên là '{fix}'" if fix else ""
            errors.append(f"dòng {i} (INS {code}): adi_status '{st}' không hợp lệ{hint}")
            status_count[f"SAI: {st}"] += 1
            st = fix or st
        else:
            status_count[st] += 1

        if st == "numeric":
            try:
                if float(val.replace(",", ".")) <= 0:
                    raise ValueError
            except ValueError:
                errors.append(f"dòng {i} (INS {code}): status numeric nhưng adi_value '{val}' không phải số dương")
        elif val:
            errors.append(f"dòng {i} (INS {code}): status '{st}' thì adi_value phải để trống (đang là '{val}')")

        if st in ("numeric", "not_specified") and not r["substance_name"].strip():
            errors.append(f"dòng {i} (INS {code}): thiếu substance_name")
        if st in ("numeric", "not_specified"):
            if not r["source"].strip().lower().startswith("http"):
                warns.append(f"dòng {i} (INS {code}): source '{r['source']}' chưa phải đường dẫn (dán URL trang đã tra)")
            if not re.search(r"\b(19|20)\d{2}\b", r["notes"]):
                warns.append(f"dòng {i} (INS {code}): notes chưa ghi năm đánh giá")
        if len(r["notes"]) > 200:
            warns.append(f"dòng {i} (INS {code}): notes dài {len(r['notes'])} ký tự, nên giữ ngắn và chỉ ghi dữ kiện")

    print(f"Tổng {len(rows)} dòng. Trạng thái: {dict(status_count)}")
    if total_freq:
        print(f"Các dòng đã điền phủ {100*filled_freq/total_freq:.1f}% lượt xuất hiện của mã INS.")
    print(f"\nLỖI ({len(errors)}):");  [print("  -", e) for e in errors]
    print(f"\nCẢNH BÁO ({len(warns)}):"); [print("  -", w) for w in warns]
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
