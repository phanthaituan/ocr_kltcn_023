#!/usr/bin/env python3
"""
adi_label.py (v2) - Sinh nhãn "phụ gia cần lưu ý liều lượng" (ADI dạng số) THEO ẢNH.

Đầu vào (đúng định dạng pipeline của bạn, KHÔNG tự trích mã lần thứ hai):
  --gold_ins_dir : thư mục đầu ra của add_gold_ins.py (<id>.json có gold_ins_additive, ...)
  --adi_table    : adi_template.csv đã điền (cột ins_code, adi_status, ...)

Quy tắc (theo taxonomy mục 2 tổng kết):
  adi_status == numeric        -> mã này làm ảnh DƯƠNG
  adi_status == not_specified  -> không gán, nhưng tính là "đã tra"
  adi_status == unknown        -> không gán; ĐÃ có kết luận "không có ADI số / không xác nhận được" (xem cột notes)
  (ô trống / mã không có trong bảng) -> không gán, CHƯA tra

Hai cờ theo ảnh:
  adi_complete = 1 : mọi mã INS của ảnh đều đã được xử lý (không còn ô trống / thiếu trong bảng)
  adi_certain  = 1 : adi_complete = 1 VÀ không mã nào ở trạng thái unknown
Nhãn âm chỉ đáng tin ở ảnh adi_certain = 1; ảnh adi_complete = 1 nhưng có unknown là "âm tính có dè dặt".
Lưu ý: unknown gộp hai trường hợp khác nhau (vd 160a: JECFA đã rút ADI; 364: chưa xác minh được chất).
Nếu cần phân biệt, ghi rõ trong cột notes của bảng ADI.

Cột n_additive_no_code = số chuỗi additive không có mã INS (hương liệu, tên chất viết bằng chữ...).
Chúng KHÔNG được xét ở đây; một số là tên chất thật (vd "natri benzoate") nên nhãn ADI của ảnh có thể thiếu.
Xem additive_decisions để xử lý.

Chạy (từ thư mục gốc project):
  python src/data_pipeline/adi_label.py
  # Hoặc tùy biến:
  python src/data_pipeline/adi_label.py --gold_ins_dir data/annotations/gold_ins --adi_table data/kb/adi_template.csv --out_dir data/annotations/adi_labels
  python src/data_pipeline/adi_label.py --selftest
"""
import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common.paths import GOLD_INS_DIR, ADI_TABLE_CSV, ADI_LABELS_DIR

RULES_VERSION = "adi_label_v2"
VALID = {"numeric", "not_specified", "unknown", ""}


def load_table(path: Path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rd = csv.DictReader(f)
        cols = rd.fieldnames or []
        if "ins_code" not in cols or "adi_status" not in cols:
            sys.exit(f"Bảng ADI thiếu cột ins_code/adi_status. Cột hiện có: {cols}")
        table, bad = {}, []
        for row in rd:
            code = (row["ins_code"] or "").strip().lower()
            status = (row["adi_status"] or "").strip().lower()
            if status not in VALID:
                bad.append((code, status))
                status = ""          # trạng thái lạ -> coi như chưa tra, không đoán
            if code in table and table[code] != status:
                bad.append((code, f"trùng mã, trạng thái khác nhau: {table[code]!r} vs {status!r}"))
            table[code] = status
    return table, bad


def label_codes(codes, table):
    status = {c: table.get(c, "") for c in codes}
    numeric = [c for c, s in status.items() if s == "numeric"]
    unresolved = [c for c, s in status.items() if s == ""]          # ô trống / không có trong bảng
    unknown = [c for c, s in status.items() if s == "unknown"]
    return {
        "label_adi": int(bool(numeric)),
        "adi_numeric_codes": numeric,
        "n_codes": len(codes),
        "n_unresolved": len(unresolved),
        "unresolved_codes": unresolved,
        "n_unknown": len(unknown),
        "unknown_codes": unknown,
        "adi_complete": int(not unresolved),
        "adi_certain": int(not unresolved and not unknown),
    }


def run(gold_dir: Path, table_path: Path, out_dir: Path, include_ingredient: bool):
    table, bad = load_table(table_path)
    if bad:
        print(f"[CẢNH BÁO] {len(bad)} dòng bảng ADI có vấn đề (coi như chưa tra): {bad[:6]}")
    n_filled = sum(1 for s in table.values() if s)
    print(f"Bảng ADI: {len(table)} mã | đã có trạng thái: {n_filled} | trống: {len(table) - n_filled}")

    files = sorted(gold_dir.glob("*.json"))
    if not files:
        sys.exit(f"Không thấy *.json trong {gold_dir}")

    rows, code_rows = [], []
    for fp in files:
        g = json.load(open(fp, encoding="utf-8"))
        codes = list(g.get("gold_ins_additive", []))
        if include_ingredient:
            codes += [c for c in g.get("gold_ins_in_ingredient", []) if c not in codes]
        r = label_codes(codes, table)
        iid = g.get("image_id", fp.stem)
        rows.append({
            "image_id": iid,
            "ins_codes": ";".join(codes),
            "label_adi": r["label_adi"],
            "adi_numeric_codes": ";".join(r["adi_numeric_codes"]),
            "n_codes": r["n_codes"],
            "n_unresolved": r["n_unresolved"],
            "unresolved_codes": ";".join(r["unresolved_codes"]),
            "unknown_codes": ";".join(r["unknown_codes"]),
            "adi_complete": r["adi_complete"],
            "adi_certain": r["adi_certain"],
            "n_additive_no_code": len(g.get("additives_without_code", [])),
            "ins_parser_version": g.get("ins_parser_version", ""),
            "rules_version": RULES_VERSION,
        })
        for c in codes:
            code_rows.append({"image_id": iid, "ins": c, "adi_status": table.get(c, "") or "unfilled"})

    out_dir.mkdir(parents=True, exist_ok=True)
    for name, data in (("adi_label_per_image.csv", rows), ("adi_label_per_code.csv", code_rows)):
        with open(out_dir / name, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(data[0].keys()) if data else ["empty"])
            w.writeheader()
            w.writerows(data)

    n = len(rows)
    pos = sum(r["label_adi"] for r in rows)
    comp = sum(r["adi_complete"] for r in rows)
    cert = sum(r["adi_certain"] for r in rows)
    with_codes = sum(1 for r in rows if r["n_codes"])
    versions = Counter(r["ins_parser_version"] for r in rows)
    pos_codes = Counter(c for r in rows for c in r["adi_numeric_codes"].split(";") if c)
    unres = Counter(d["ins"] for d in code_rows if d["adi_status"] == "unfilled")
    unkn = Counter(d["ins"] for d in code_rows if d["adi_status"] == "unknown")
    print(f"\nẢnh: {n} (có >=1 mã INS: {with_codes}) | parser: {dict(versions)}")
    print(f"Nhãn dương: {pos} ({pos / n:.1%}) | adi_complete=1: {comp} ({comp / n:.1%}) | adi_certain=1: {cert} ({cert / n:.1%})")
    if comp < n:
        print("  -> Ảnh adi_complete=0 còn mã CHƯA tra: nhãn âm có thể là âm tính GIẢ.")
    if cert < comp:
        print("  -> Ảnh có mã unknown: nhãn âm chỉ là 'không có ADI số theo bảng hiện tại'.")
    print("Mã dương hay gặp:", pos_codes.most_common(8))
    print("Mã CHƯA tra (ô trống), theo số ảnh bị ảnh hưởng (ưu tiên điền):", unres.most_common(15))
    print("Mã unknown (đã tra nhưng không có ADI số / chưa xác nhận):", unkn.most_common(8))
    print(f"Đã ghi vào {out_dir}")


def selftest():
    fails = 0
    table = {"211": "numeric", "621": "not_specified", "330": "", "500": "numeric", "999": "unknown"}
    cases = [   # codes, label, complete, certain
        (["211"], 1, 1, 1),
        (["621"], 0, 1, 1),
        (["330"], 0, 0, 0),          # ô trống = chưa tra
        (["999"], 0, 1, 0),          # unknown = đã tra nhưng không chắc
        (["500"], 1, 1, 1),
        (["211", "330"], 1, 0, 0),
        (["211", "999"], 1, 1, 0),
        (["777"], 0, 0, 0),          # không có trong bảng
        ([], 0, 1, 1),               # ảnh không có mã INS
    ]
    for codes, want_lab, want_comp, want_cert in cases:
        r = label_codes(codes, table)
        ok = (r["label_adi"], r["adi_complete"], r["adi_certain"]) == (want_lab, want_comp, want_cert)
        fails += not ok
        print("OK  " if ok else "FAIL", codes, "->", r["label_adi"], r["adi_complete"], r["adi_certain"])
    print("KẾT QUẢ:", "TẤT CẢ ĐẠT" if not fails else f"{fails} CA LỖI")
    return fails


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--gold_ins_dir", type=Path, default=GOLD_INS_DIR, help=f"Thư mục chứa gold INS (mặc định: {GOLD_INS_DIR})")
    ap.add_argument("--adi_table", type=Path, default=ADI_TABLE_CSV, help=f"Đường dẫn file bảng ADI (mặc định: {ADI_TABLE_CSV})")
    ap.add_argument("--out_dir", type=Path, default=ADI_LABELS_DIR, help=f"Thư mục xuất nhãn ADI (mặc định: {ADI_LABELS_DIR})")
    ap.add_argument("--include_ingredient_ins", action="store_true",
                    help="gộp cả mã INS nằm trong ingredient (mặc định chỉ dùng gold_ins_additive)")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(1 if selftest() else 0)
    if not (a.gold_ins_dir and a.adi_table):
        ap.error("cần --gold_ins_dir và --adi_table (hoặc --selftest)")
    if not a.gold_ins_dir.exists():
        ap.error(f"Thư mục gold_ins không tồn tại: {a.gold_ins_dir}")
    if not a.adi_table.exists():
        ap.error(f"File bảng ADI không tồn tại: {a.adi_table}")
    run(a.gold_ins_dir, a.adi_table, a.out_dir, a.include_ingredient_ins)


if __name__ == "__main__":
    main()