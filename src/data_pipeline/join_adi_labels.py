"""
join_adi_labels.py
Nối bảng ADI (ADI_TABLE_CSV) vào danh sách mã INS của từng ảnh (từ GOLD_INS_DIR),
sinh ra nhãn ADI mức mã và mức ảnh (lưu tại ADI_LABELS_DIR/<image_id>.json + bảng tổng hợp CSV).

Đặc điểm thiết kế (bám sát KeHoach_4Tuan_CapNhat.md):
  1. Hàm compute_adi_for_codes(ins_codes, adi_lookup) được tách độc lập để TÁI SỬ DỤNG
     trực tiếp ở bước hậu xử lý của mọi pipeline (P0, P1, P2, Main, V1, Control).
     Nhờ vậy Gold và Prediction dùng chung 1 hàm + 1 bảng tra, đảm bảo công bằng tuyệt đối.
  2. Phân tách rõ `limit_type` từ cột `adi_status` và `notes`:
       - "adi"           : numeric thông thường (bao gồm cả group ADI)
       - "mtdi"          : numeric nhưng thuộc nhóm MTDI / PMTDI / PTWI (vd nhóm phosphate)
       - "temporary_adi" : numeric nhưng là Temporary ADI
       - "not_specified" : không giới hạn số
       - "withdrawn"     : unknown do JECFA đã rút ADI (ADI WITHDRAWN)
       - "unknown"       : đã tra JECFA nhưng không có ADI số riêng
       - "unverified"    : mã chưa kịp tra trong bảng ADI ("chưa tra", khác với "unknown")
  3. Tính sẵn 2 biến thể nhãn dương cho từng ảnh:
       - has_adi_warning_all_numeric : True nếu có >= 1 mã numeric (gồm cả ADI, Temporary ADI và MTDI)
       - has_adi_warning_strict_adi  : True nếu có >= 1 mã numeric thuộc ADI / Temporary ADI (loại trừ MTDI)

Cách chạy (từ thư mục gốc project):
    python src/data_pipeline/join_adi_labels.py
"""

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.common.paths import ADI_LABELS_DIR, ADI_TABLE_CSV, GOLD_INS_DIR, REPORTS_DIR

MTDI_RE = re.compile(r"\b(?:p?mtdi|ptwi|ptmi)\b", re.I)
TEMP_RE = re.compile(r"\b(?:temp(?:orary)?)\b", re.I)
WITHDRAWN_RE = re.compile(r"\bwithdrawn\b", re.I)

def infer_limit_type(adi_status: str, notes: str) -> str:
    st = (adi_status or "").strip().lower()
    nt = (notes or "").strip()
    if not st:
        return "unverified"
    if st == "numeric":
        if MTDI_RE.search(nt):
            return "mtdi"
        if TEMP_RE.search(nt):
            return "temporary_adi"
        return "adi"
    if st == "not_specified":
        return "not_specified"
    if st == "unknown":
        if WITHDRAWN_RE.search(nt):
            return "withdrawn"
        return "unknown"
    return "unverified"

def load_adi_lookup(csv_path: Path) -> dict:
    lookup = {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = (row.get("ins_code") or "").strip().lower()
            if not code:
                continue
            st = (row.get("adi_status") or "").strip().lower()
            val_str = (row.get("adi_value_mg_per_kg_bw") or "").strip()
            notes = (row.get("notes") or "").strip()
            limit_type = infer_limit_type(st, notes)

            val_float = None
            if st == "numeric" and val_str:
                try:
                    val_float = float(val_str.replace(",", "."))

                except ValueError:
                    val_float = None

            lookup[code] = {
                "ins_code": code,
                "substance_name": (row.get("substance_name") or "").strip(),
                "adi_status": st if st else "unverified",
                "adi_value_mg_per_kg_bw": val_float,
                "limit_type": limit_type,
                "source": (row.get("source") or "").strip(),
                "notes": notes,
            }
    return lookup

def compute_adi_for_codes(ins_codes: list, adi_lookup: dict) -> dict:
    code_details = []
    numeric_all_codes = []
    numeric_strict_adi_codes = []
    mtdi_codes = []
    not_specified_codes = []
    unknown_codes = []
    unverified_codes = []

    for raw_code in sorted(set(c.strip().lower() for c in ins_codes if c and c.strip())):
        info = adi_lookup.get(raw_code)
        if info is None or info["adi_status"] == "unverified":
            detail = {
                "ins_code": raw_code,
                "substance_name": info["substance_name"] if info else "",
                "adi_status": "unverified",
                "adi_value_mg_per_kg_bw": None,
                "limit_type": "unverified",
                "is_positive_all_numeric": False,
                "is_positive_strict_adi": False,
            }
            unverified_codes.append(raw_code)

        else:
            ltype = info["limit_type"]
            is_pos_all = info["adi_status"] == "numeric"
            is_pos_strict = is_pos_all and (ltype in ("adi", "temporary_adi"))

            if is_pos_all:
                numeric_all_codes.append(raw_code)
                if ltype == "mtdi":
                    mtdi_codes.append(raw_code)

                else:
                    numeric_strict_adi_codes.append(raw_code)

            elif info["adi_status"] == "not_specified":
                not_specified_codes.append(raw_code)

            else:
                unknown_codes.append(raw_code)

            detail = {
                "ins_code": raw_code,
                "substance_name": info["substance_name"],
                "adi_status": info["adi_status"],
                "adi_value_mg_per_kg_bw": info["adi_value_mg_per_kg_bw"],
                "limit_type": ltype,
                "is_positive_all_numeric": is_pos_all,
                "is_positive_strict_adi": is_pos_strict,
            }
        code_details.append(detail)

    n_total = len(code_details)
    n_verified = n_total - len(unverified_codes)

    return {
        "has_adi_warning_all_numeric": len(numeric_all_codes) > 0,
        "has_adi_warning_strict_adi": len(numeric_strict_adi_codes) > 0,
        "has_mtdi_only": (len(numeric_all_codes) > 0 and len(numeric_strict_adi_codes) == 0),
        "numeric_all_codes": numeric_all_codes,
        "numeric_strict_adi_codes": numeric_strict_adi_codes,
        "mtdi_codes": mtdi_codes,
        "not_specified_codes": not_specified_codes,
        "unknown_codes": unknown_codes,
        "unverified_codes": unverified_codes,
        "coverage": {
            "n_total_codes": n_total,
            "n_verified_codes": n_verified,
            "n_unverified_codes": len(unverified_codes),
            "verified_ratio": round(n_verified / n_total, 4) if n_total > 0 else 1.0,
        },
        "code_details": code_details,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold_ins_dir", default=str(GOLD_INS_DIR), help="Thư mục chứa gold_ins JSON")
    ap.add_argument("--adi_csv", default=str(ADI_TABLE_CSV), help="File CSV bảng ADI")
    ap.add_argument("--out_dir", default=str(ADI_LABELS_DIR), help="Thư mục xuất adi_labels JSON")
    ap.add_argument("--summary_csv", default=str(REPORTS_DIR / "adi_labels_summary.csv"), help="FIle CSV tổng hợp")
    args = ap.parse_args()

    gold_ins_dir = Path(args.gold_ins_dir)
    adi_csv = Path(args.adi_csv)
    out_dir = Path(args.out_dir)
    summary_csv = Path(args.summary_csv)

    if not adi_csv.exists():
        print(f"Không tìm thấy bảng ADI tại: {adi_csv}")
        sys.exit(1)

    ins_files = sorted(gold_ins_dir.glob("*.json"))
    if not ins_files:
        print(f"Không tìm thấy file JSON nào trong: {gold_ins_dir}. Hãy chạy add_gold_ins.py trước.")
        sys.exit(1)

    out_dir.mkdir(parents=True, exist_ok=True)
    summary_csv.parent.mkdir(parents=True, exist_ok=True)

    adi_lookup= load_adi_lookup(adi_csv)

    summary_rows= []
    stats = Counter()
    code_occurrence_counter = Counter()

    for fp in ins_files:
        rec = json.load(open(fp, encoding="utf-8"))
        image_id = str(rec.get("image_id", fp.stem))
        main_codes = rec.get("gold_ins_additive", [])
        ing_codes = rec.get("gold_ins_in_ingredient", [])

        main_adi = compute_adi_for_codes(main_codes, adi_lookup)
        ing_adi = compute_adi_for_codes(ing_codes, adi_lookup)

        out_record = {
            "image_id": image_id,
            "has_adi_warning_all_numeric": main_adi["has_adi_warning_all_numeric"],
            "has_adi_warning_strict_adi": main_adi["has_adi_warning_strict_adi"],
            "has_mtdi_only": main_adi["has_mtdi_only"],
            "gold_ins_additive_adi": main_adi,
            "gold_ins_in_ingredient_adi": ing_adi,
            "additives_without_code": rec.get("additives_without_code", []),
            "ins_parser_version": rec.get("ins_parser_version", ""),
        }

        with open(out_dir / f"{image_id}.json", "w", encoding="utf-8") as f:
            json.dump(out_record, f, ensure_ascii=False, indent=2)

        stats["total_images"] += 1
        if main_codes:
            stats["images_with_ins"] += 1
        if main_adi["has_adi_warning_all_numeric"]:
            stats["pos_all_numeric"] += 1
        if main_adi["has_adi_warning_strict_adi"]:
            stats["pos_strict_adi"] += 1
        if main_adi["has_mtdi_only"]:
            stats["pos_mtdi_only"] += 1
        if main_adi["unverified_codes"]:
            stats["images_with_unverified"] += 1

        for d in main_adi["code_details"]:
            code_occurrence_counter[d["limit_type"]] += 1

        summary_rows.append({
            "image_id": image_id,
            "n_ins_codes": main_adi["coverage"]["n_total_codes"],
            "n_verified_codes": main_adi["coverage"]["n_verified_codes"],
            "n_unverified_codes": main_adi["coverage"]["n_unverified_codes"],
            "has_adi_warning_all_numeric": main_adi["has_adi_warning_all_numeric"],
            "has_adi_warning_strict_adi": main_adi["has_adi_warning_strict_adi"],
            "has_mtdi_only": main_adi["has_mtdi_only"],
            "numeric_all_codes": ";".join(main_adi["numeric_all_codes"]),
            "numeric_strict_adi_codes": ";".join(main_adi["numeric_strict_adi_codes"]),
            "mtdi_codes": ";".join(main_adi["mtdi_codes"]),
            "unverified_codes": ";".join(main_adi["unverified_codes"]),
        })

    with open(summary_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        writer.writeheader()
        writer.writerows(summary_rows)

    total_occ = sum(code_occurrence_counter.values())
    verified_occ = total_occ - code_occurrence_counter["unverified"]

    print(f"Đã nối nhãn ADI cho {stats['total_images']} ảnh -> {out_dir}")
    print(f"  - Số ảnh có >=1 mã INS (additive)          : {stats['images_with_ins']}")
    print(f"  - Ảnh DƯƠNG (all numeric, gồm cả MTDI)     : {stats['pos_all_numeric']}")
    print(f"  - Ảnh DƯƠNG (strict ADI, không tính MTDI)  : {stats['pos_strict_adi']}")
    print(f"  - Ảnh chỉ dương do MTDI (phosphate)        : {stats['pos_mtdi_only']}")
    print(f"  - Ảnh có chứa ít nhất 1 mã chưa tra        : {stats['images_with_unverified']}")
    if total_occ:
        print(f"  - Độ phủ lượt mã INS đã tra                : {verified_occ}/{total_occ} ({100*verified_occ/total_occ:.2f}%)")
        print(f"  - Phân bố lượt mã theo limit_type          : {dict(code_occurrence_counter)}")
    print(f"Đã lưu bảng tổng hợp tại: {summary_csv}")


if __name__ == "__main__":
    main()