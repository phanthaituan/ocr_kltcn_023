"""
add_gold_ins.py
Tạo GOLD MÃ INS theo từng ảnh từ gold_parsed/ (ghi ra thư mục RIÊNG, không sửa dữ liệu gốc).
Mỗi file <id>.json gồm:
  gold_ins_additive      : mã INS (base) trong field additive  -> gold CHÍNH cho nhãn Phụ gia và nhãn ADI
  gold_ins_in_ingredient : mã INS nằm lẫn trong field ingredient -> gold PHỤ (tránh phạt oan khi pipeline tìm thấy)
  additives_without_code : chuỗi additive không có mã (hương liệu, tên chất không kèm mã) -> không đánh giá theo mã
  ins_parser_version

Cách chạy (từ thư mục gốc project):
    python src/data_pipeline/add_gold_ins.py
    # Hoặc tùy biến: 
    python src/data_pipeline/add_gold_ins.py --gold_dir data/annotations/gold_parsed --out_dir data/annotations/gold_ins
"""
import argparse, json, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.common.paths import GOLD_PARSED_DIR, GOLD_INS_DIR
from ins_parser import ins_bases, PARSER_VERSION


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold_dir", default=str(GOLD_PARSED_DIR), help="Thư mục chứa gold_parsed JSON")
    ap.add_argument("--out_dir", default=str(GOLD_INS_DIR), help="Thư mục xuất gold_ins JSON")
    args = ap.parse_args()
    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)

    n = n_with = n_no_code_imgs = 0
    all_codes = set()
    for fp in sorted(Path(args.gold_dir).glob("*.json")):
        g = json.load(open(fp, encoding="utf-8"))
        adds = g.get("gold_additives_raw", [])
        ings = g.get("gold_ingredients_raw", [])
        main_codes = set().union(*[ins_bases(a) for a in adds]) if adds else set()
        ing_codes = (set().union(*[ins_bases(i) for i in ings]) if ings else set()) - main_codes
        no_code = [a for a in adds if not ins_bases(a)]
        rec = {"image_id": g.get("image_id", fp.stem),
               "gold_ins_additive": sorted(main_codes),
               "gold_ins_in_ingredient": sorted(ing_codes),
               "additives_without_code": no_code,
               "ins_parser_version": PARSER_VERSION}
        json.dump(rec, open(out / fp.name, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
        n += 1; n_with += bool(main_codes); n_no_code_imgs += bool(no_code); all_codes |= main_codes
    print(f"Đã xử lý {n} ảnh -> {out}")
    print(f"  ảnh có >=1 mã INS trong additive : {n_with}")
    print(f"  ảnh có additive không kèm mã      : {n_no_code_imgs}")
    print(f"  số mã INS duy nhất (gold chính)   : {len(all_codes)}")


if __name__ == "__main__":
    main()