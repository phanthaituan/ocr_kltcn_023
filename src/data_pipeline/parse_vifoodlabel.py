# """
# parse_vifoodlabel.py
# Đọc toàn bộ file JSON trong thư mục labels/ của ViFoodLabel (bản "processed" / KIE record),
# sinh:
#   1. completeness_report.csv - thống kê field nào có/thiếu cho mỗi ảnh
#   2. gold_converted/<id>.json - convert sang schema của đề tài, có gợi ý nhãn dị ứng
#      trích xuất bán tự động từ field "warning"

# Cách chạy:
#     python parse_vifoodlabel.py --labels_dir labels --out_dir gold_converted
# """

# import json
# import re
# import csv
# import argparse
# from pathlib import Path

# # 14 nhóm dị nguyên phổ biến (EU) - tên tiếng Việt thường gặp trên bao bì VN
# # Có thể mở rộng/tinh chỉnh danh sách này theo thực tế dữ liệu của bạn
# ALLERGEN_KEYWORDS = {
#     "gluten": ["lúa mì", "bột mì", "lúa mạch", "yến mạch", "gluten", "wheat"],
#     "giáp_xác": ["tôm", "cua", "giáp xác", "crustacean"],
#     "trứng": ["trứng", "egg"],
#     "cá": ["cá ", "cá,", "cá.", "nước mắm", "fish"],
#     "đậu_phộng": ["đậu phộng", "lạc", "peanut", "peanuts"],
#     "đậu_nành": ["đậu nành", "đậu tương", "soy", "soybean"],
#     "sữa": ["sữa", "milk"],
#     "hạt_cây": ["hạnh nhân", "almond", "hạt điều", "óc chó", "hồ đào", "hạt dẻ", "mắc ca", "hạt phỉ", "hazelnut", "tree nut", "tree nuts", "sheanut"],
#     "cần_tây": ["cần tây", "celery"],
#     "mù_tạt": ["mù tạt", "mustard"],
#     "hạt_vừng": ["vừng", "mè", "sesame"],
#     "sulfite": ["sulfit", "sulfite", "sulphite"],
#     "lupin": ["lupin"],
#     "nhuyễn_thể": ["nhuyễn thể", "ốc", "mực", "bạch tuộc", "sò", "mollusc"],
#     "hải_sản": ["hải sản", "seafood"],
#     "ngô": ["ngô", "bắp", "corn"],
#     "dừa": ["dầu dừa", "dừa", "coconut"],
#     "rong_biển": ["rong biển", "seaweed"],
# }


# def extract_allergen_hints(warning_list):
#     """
#     Tách câu cảnh báo dị ứng tiếng Việt thành 2 mức độ:
#       - contains: "Có chứa X, Y."      -> chắc chắn có
#       - may_contain: "Có thể chứa X."  -> cảnh báo lẫn chéo (trace warning)
#     Trả về dict {"contains": [...], "may_contain": [...]} theo tên nhóm dị nguyên chuẩn hóa.
#     Đây là GỢI Ý bán tự động - vẫn cần người review lại trước khi dùng làm gold nhãn.
#     """
#     result = {"contains": set(), "may_contain": set(), "raw_matched_text": []}
#     if not warning_list:
#         return {"contains": [], "may_contain": [], "raw_matched_text": []}

#     for sentence in warning_list:
#         s_lower = sentence.lower()
#         is_may_contain = "có thể chứa" in s_lower or "có thể lẫn" in s_lower

#         matched_any = False
#         for allergen_group, keywords in ALLERGEN_KEYWORDS.items():
#             for kw in keywords:
#                 if kw in s_lower:
#                     target = result["may_contain"] if is_may_contain else result["contains"]
#                     target.add(allergen_group)
#                     matched_any = True
#         if matched_any:
#             result["raw_matched_text"].append(sentence)

#     return {
#         "contains": sorted(result["contains"]),
#         "may_contain": sorted(result["may_contain"]),
#         "raw_matched_text": result["raw_matched_text"],
#     }


# def safe_get(record, key, default):
#     """Lấy field an toàn - trả về default nếu thiếu hoặc null, không raise lỗi."""
#     val = record.get(key, default)
#     return val if val is not None else default


# def convert_record(record, image_id):
#     """Convert 1 record KIE gốc -> schema gold của đề tài."""
#     ingredients = safe_get(record, "ingredient", [])
#     additives = safe_get(record, "additive", [])
#     nutrition = safe_get(record, "nutrition", [])
#     warnings = safe_get(record, "warning", [])

#     allergen_hints = extract_allergen_hints(warnings)

#     return {
#         "image_id": image_id,
#         "product_name": safe_get(record, "product_name", None),
#         "gold_ingredients_raw": ingredients,       # chưa tách E-number/định lượng, để nguyên bước sau xử lý
#         "gold_additives_raw": additives,
#         "gold_nutrition": nutrition,
#         "gold_warning_raw": warnings,
#         "allergen_hints": allergen_hints,           # GỢI Ý - cần người review trước khi làm gold thật
#         "origin": safe_get(record, "origin", None),
#         "net_weight": safe_get(record, "net_weight", None),
#         "mfg_date": safe_get(record, "mfg_date", None),
#         "expiry_date": safe_get(record, "expiry_date", None),
#         "completeness": {
#             "has_ingredient": len(ingredients) > 0,
#             "has_additive": len(additives) > 0,
#             "has_nutrition": len(nutrition) > 0,
#             "has_warning": len(warnings) > 0,
#         },
#     }


# def main():
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--labels_dir", default="labels")
#     parser.add_argument("--out_dir", default="gold_converted")
#     parser.add_argument("--report_path", default="completeness_report.csv")
#     args = parser.parse_args()

#     labels_dir = Path(args.labels_dir)
#     out_dir = Path(args.out_dir)
#     out_dir.mkdir(parents=True, exist_ok=True)

#     json_files = sorted(labels_dir.glob("*.json"))
#     if not json_files:
#         print(f"Không tìm thấy file .json nào trong {labels_dir}")
#         return

#     report_rows = []
#     stats = {"total": 0, "has_ingredient": 0, "has_additive": 0, "has_nutrition": 0, "has_warning": 0,
#              "full_record": 0}

#     for fp in json_files:
#         image_id = fp.stem
#         with open(fp, "r", encoding="utf-8") as f:
#             record = json.load(f)

#         converted = convert_record(record, image_id)
#         with open(out_dir / f"{image_id}.json", "w", encoding="utf-8") as f:
#             json.dump(converted, f, ensure_ascii=False, indent=2)

#         c = converted["completeness"]
#         stats["total"] += 1
#         for k in ("has_ingredient", "has_additive", "has_nutrition", "has_warning"):
#             if c[k]:
#                 stats[k] += 1
#         if all(c.values()):
#             stats["full_record"] += 1

#         report_rows.append({
#             "image_id": image_id,
#             **c,
#             "n_ingredients": len(converted["gold_ingredients_raw"]),
#             "n_additives": len(converted["gold_additives_raw"]),
#             "n_allergen_contains_hints": len(converted["allergen_hints"]["contains"]),
#             "n_allergen_may_contain_hints": len(converted["allergen_hints"]["may_contain"]),
#         })

#     with open(args.report_path, "w", newline="", encoding="utf-8") as f:
#         writer = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
#         writer.writeheader()
#         writer.writerows(report_rows)

#     print(f"Đã xử lý {stats['total']} file.")
#     print(f"  - Có ingredient : {stats['has_ingredient']} ({100*stats['has_ingredient']/stats['total']:.1f}%)")
#     print(f"  - Có additive   : {stats['has_additive']} ({100*stats['has_additive']/stats['total']:.1f}%)")
#     print(f"  - Có nutrition  : {stats['has_nutrition']} ({100*stats['has_nutrition']/stats['total']:.1f}%)")
#     print(f"  - Có warning    : {stats['has_warning']} ({100*stats['has_warning']/stats['total']:.1f}%)")
#     print(f"  - Đầy đủ cả 4   : {stats['full_record']} ({100*stats['full_record']/stats['total']:.1f}%)")
#     print(f"\nĐã ghi báo cáo: {args.report_path}")
#     print(f"Đã ghi file convert: {out_dir}/")


# if __name__ == "__main__":
#     main()


# """
# parse_vifoodlabel.py (v3)
# Nâng cấp so với v2:
#   1. Phân loại warning thành các subtype: expiry_usage, storage_instruction,
#      child_supervision, generic_allergy_reference, named_allergy, desiccant_or_misc, unclassified
#   2. Khi gặp "generic_allergy_reference" (cảnh báo dị ứng nhưng KHÔNG nêu tên chất cụ thể,
#      vd "dị ứng với các thành phần trên"): tự động quét chéo sang chính field ingredient +
#      additive của ảnh đó bằng ALLERGEN_KEYWORDS để suy ra allergen cụ thể - vì nhãn VN
#      thường đặt allergen ngay trong ingredient list, không lặp lại ở warning.
#   3. allergen_final = hợp nhất từ 2 nguồn (named trong warning + suy luận từ ingredient/additive),
#      có "source" để biết nhãn đến từ đâu (phục vụ review sau này).

# Cách chạy (từ thư mục gốc project, mặc định đọc data/raw/.../labels và ghi data/annotations/gold_parsed):
#     python src/data_pipeline/parse_vifoodlabel.py
# """

# import json
# import csv
# import sys
# import argparse
# from pathlib import Path

# sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
# from src.common.paths import RAW_LABELS_DIR, GOLD_PARSED_DIR, COMPLETENESS_REPORT

# ALLERGEN_KEYWORDS = {
#     "gluten": ["lúa mì", "bột mì", "lúa mạch", "yến mạch", "gluten", "wheat"],
#     "giáp_xác": ["tôm", "cua", "giáp xác", "crustacean"],
#     "trứng": ["trứng", "egg"],
#     "cá": ["cá ", "cá,", "cá.", "nước mắm", "fish"],
#     "đậu_phộng": ["đậu phộng", "lạc", "peanut", "peanuts"],
#     "đậu_nành": ["đậu nành", "đậu tương", "soy", "soybean"],
#     "sữa": ["sữa", "milk", "whey", "bơ sữa"],
#     "hạt_cây": ["hạnh nhân", "almond", "hạt điều", "óc chó", "hồ đào", "hạt dẻ", "mắc ca",
#                 "hạt phỉ", "hazelnut", "tree nut", "tree nuts", "sheanut"],
#     "cần_tây": ["cần tây", "celery"],
#     "mù_tạt": ["mù tạt", "mustard"],
#     "hạt_vừng": ["vừng", "mè", "sesame"],
#     "sulfite": ["sulfit", "sulfite", "sulphite"],
#     "lupin": ["lupin"],
#     "nhuyễn_thể": ["nhuyễn thể", "ốc", "mực", "bạch tuộc", "sò", "mollusc"],
#     "hải_sản": ["hải sản", "seafood"],
#     "ngô": ["ngô", "bắp", "corn"],
#     "dừa": ["dầu dừa", "dừa", "coconut"],
#     "rong_biển": ["rong biển", "seaweed"],
# }

# # Từ khóa phân loại warning subtype - chỉ dùng để BÁO CÁO/QC, không ảnh hưởng đến việc
# # tính allergen_final (allergen_final chỉ dựa trên named-keyword match + generic-allergy trigger)
# SUBTYPE_PATTERNS = {
#     "expiry_usage": ["hết hạn", "quá hạn", "hư hỏng", "hỏng", "dấu hiệu", "biến dạng", "lỗi"],
#     "storage_instruction": ["bảo quản", "sau khi mở", "lắc đều", "dùng hết trong", "tránh ánh nắng", "để nơi khô ráo"],
#     "child_supervision": ["trẻ em", "trẻ nhỏ", "tuổi", "giám sát", "tầm tay trẻ", "hóc", "nhai kỹ", "người già"],
#     "desiccant_or_misc": ["hút ẩm", "hút oxy", "màu và mùi lạ", "lò vi sóng"],
# }
# GENERIC_ALLERGY_TRIGGER = ["dị ứng", "mẫn cảm", "allergic", "allergy"]


# def classify_warning_subtype(sentence, matched_named_allergen):
#     """Chỉ dùng để thống kê/QC - trả về 1 nhãn subtype mô tả (không ảnh hưởng allergen_final)."""
#     s = sentence.lower()
#     if matched_named_allergen:
#         return "named_allergy"
#     if any(kw in s for kw in GENERIC_ALLERGY_TRIGGER):
#         return "generic_allergy_reference"
#     for subtype, kws in SUBTYPE_PATTERNS.items():
#         if any(kw in s for kw in kws):
#             return subtype
#     return "unclassified"


# def find_allergen_keywords_in_text(text_list):
#     """Quét 1 list câu/text, trả về set các nhóm dị nguyên match được (không phân contains/may_contain)."""
#     found = set()
#     joined = " ".join(text_list).lower()
#     for allergen_group, keywords in ALLERGEN_KEYWORDS.items():
#         for kw in keywords:
#             if kw in joined:
#                 found.add(allergen_group)
#     return found


# def extract_allergen_info(warning_list, ingredient_list, additive_list):
#     """
#     Trả về:
#       contains, may_contain: allergen_final đã hợp nhất 2 nguồn
#       subtype_counts: thống kê phân loại warning (để QC)
#       has_generic_reference: có câu dị ứng generic không named hay không
#     """
#     contains_named = set()
#     may_contain_named = set()
#     subtype_counts = {}
#     has_generic_reference = False

#     for sentence in (warning_list or []):
#         s_lower = sentence.lower()
#         is_may_contain = "có thể chứa" in s_lower or "có thể lẫn" in s_lower

#         matched_this_sentence = set()
#         for allergen_group, keywords in ALLERGEN_KEYWORDS.items():
#             if any(kw in s_lower for kw in keywords):
#                 matched_this_sentence.add(allergen_group)

#         if matched_this_sentence:
#             target = may_contain_named if is_may_contain else contains_named
#             target |= matched_this_sentence

#         subtype = classify_warning_subtype(sentence, bool(matched_this_sentence))
#         subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1
#         if subtype == "generic_allergy_reference":
#             has_generic_reference = True

#     inferred_from_ingredients = set()
#     if has_generic_reference:
#         # Suy luận allergen từ chính ingredient + additive khi warning chỉ nói chung chung
#         inferred_from_ingredients = find_allergen_keywords_in_text(
#             (ingredient_list or []) + (additive_list or [])
#         )

#     contains_final = sorted(contains_named | inferred_from_ingredients)
#     may_contain_final = sorted(may_contain_named - contains_named)  # ưu tiên contains nếu trùng

#     return {
#         "contains": contains_final,
#         "may_contain": may_contain_final,
#         "source": {
#             "named_in_warning": sorted(contains_named | may_contain_named),
#             "inferred_from_ingredient_additive": sorted(inferred_from_ingredients),
#             "has_generic_allergy_reference": has_generic_reference,
#         },
#         "warning_subtype_counts": subtype_counts,
#     }


# def safe_get(record, key, default):
#     val = record.get(key, default)
#     return val if val is not None else default


# def convert_record(record, image_id):
#     ingredients = safe_get(record, "ingredient", [])
#     additives = safe_get(record, "additive", [])
#     nutrition = safe_get(record, "nutrition", [])
#     warnings = safe_get(record, "warning", [])

#     allergen_info = extract_allergen_info(warnings, ingredients, additives)

#     return {
#         "image_id": image_id,
#         "product_name": safe_get(record, "product_name", None),
#         "gold_ingredients_raw": ingredients,
#         "gold_additives_raw": additives,
#         "gold_nutrition": nutrition,
#         "gold_warning_raw": warnings,
#         "allergen_final": {
#             "contains": allergen_info["contains"],
#             "may_contain": allergen_info["may_contain"],
#         },
#         "allergen_debug": allergen_info["source"] | {"warning_subtype_counts": allergen_info["warning_subtype_counts"]},
#         "origin": safe_get(record, "origin", None),
#         "net_weight": safe_get(record, "net_weight", None),
#         "mfg_date": safe_get(record, "mfg_date", None),
#         "expiry_date": safe_get(record, "expiry_date", None),
#         "completeness": {
#             "has_ingredient": len(ingredients) > 0,
#             "has_additive": len(additives) > 0,
#             "has_nutrition": len(nutrition) > 0,
#             "has_warning": len(warnings) > 0,
#         },
#     }


# def main():
#     parser = argparse.ArgumentParser()
#     parser.add_argument("--labels_dir", default=str(RAW_LABELS_DIR))
#     parser.add_argument("--out_dir", default=str(GOLD_PARSED_DIR))
#     parser.add_argument("--report_path", default=str(COMPLETENESS_REPORT))
#     args = parser.parse_args()

#     labels_dir = Path(args.labels_dir)
#     out_dir = Path(args.out_dir)
#     out_dir.mkdir(parents=True, exist_ok=True)

#     json_files = sorted(labels_dir.glob("*.json"))
#     if not json_files:
#         print(f"Không tìm thấy file .json nào trong {labels_dir}")
#         return

#     report_rows = []
#     stats = {"total": 0, "has_ingredient": 0, "has_additive": 0, "has_nutrition": 0, "has_warning": 0,
#              "full_record": 0, "has_allergen_final": 0, "inferred_used": 0}

#     for fp in json_files:
#         image_id = fp.stem
#         with open(fp, "r", encoding="utf-8") as f:
#             record = json.load(f)

#         converted = convert_record(record, image_id)
#         with open(out_dir / f"{image_id}.json", "w", encoding="utf-8") as f:
#             json.dump(converted, f, ensure_ascii=False, indent=2)

#         c = converted["completeness"]
#         stats["total"] += 1
#         for k in ("has_ingredient", "has_additive", "has_nutrition", "has_warning"):
#             if c[k]:
#                 stats[k] += 1
#         if all(c.values()):
#             stats["full_record"] += 1

#         n_allergen_final = len(converted["allergen_final"]["contains"]) + len(converted["allergen_final"]["may_contain"])
#         if n_allergen_final > 0:
#             stats["has_allergen_final"] += 1
#         if converted["allergen_debug"]["inferred_from_ingredient_additive"]:
#             stats["inferred_used"] += 1

#         report_rows.append({
#             "image_id": image_id,
#             **c,
#             "n_ingredients": len(converted["gold_ingredients_raw"]),
#             "n_additives": len(converted["gold_additives_raw"]),
#             "n_allergen_contains": len(converted["allergen_final"]["contains"]),
#             "n_allergen_may_contain": len(converted["allergen_final"]["may_contain"]),
#             "has_generic_allergy_reference": converted["allergen_debug"]["has_generic_allergy_reference"],
#             "n_inferred_from_ingredient": len(converted["allergen_debug"]["inferred_from_ingredient_additive"]),
#         })

#     with open(args.report_path, "w", newline="", encoding="utf-8") as f:
#         writer = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
#         writer.writeheader()
#         writer.writerows(report_rows)

#     print(f"Đã xử lý {stats['total']} file.")
#     print(f"  - Có ingredient : {stats['has_ingredient']} ({100*stats['has_ingredient']/stats['total']:.1f}%)")
#     print(f"  - Có additive   : {stats['has_additive']} ({100*stats['has_additive']/stats['total']:.1f}%)")
#     print(f"  - Có nutrition  : {stats['has_nutrition']} ({100*stats['has_nutrition']/stats['total']:.1f}%)")
#     print(f"  - Có warning    : {stats['has_warning']} ({100*stats['has_warning']/stats['total']:.1f}%)")
#     print(f"  - Đầy đủ cả 4   : {stats['full_record']} ({100*stats['full_record']/stats['total']:.1f}%)")
#     print(f"  - Có allergen_final (>=1 nhãn) : {stats['has_allergen_final']} ({100*stats['has_allergen_final']/stats['total']:.1f}%)")
#     print(f"  - Trong đó nhờ suy luận từ ingredient/additive (generic warning) : {stats['inferred_used']}")
#     print(f"\nĐã ghi báo cáo: {args.report_path}")
#     print(f"Đã ghi file convert: {out_dir}/")


# if __name__ == "__main__":
#     main()

"""
parse_vifoodlabel.py (v4)
Nâng cấp so với v2:
  1. Phân loại warning thành các subtype: expiry_usage, storage_instruction,
     child_supervision, generic_allergy_reference, named_allergy, desiccant_or_misc, unclassified
  2. Khi gặp "generic_allergy_reference" (cảnh báo dị ứng nhưng KHÔNG nêu tên chất cụ thể,
     vd "dị ứng với các thành phần trên"): tự động quét chéo sang chính field ingredient +
     additive của ảnh đó bằng ALLERGEN_KEYWORDS để suy ra allergen cụ thể - vì nhãn VN
     thường đặt allergen ngay trong ingredient list, không lặp lại ở warning.
  3. allergen_final = hợp nhất từ 2 nguồn (named trong warning + suy luận từ ingredient/additive),
     có "source" để biết nhãn đến từ đâu (phục vụ review sau này).

Cách chạy (từ thư mục gốc project; mặc định đọc RAW_LABELS_DIR, ghi GOLD_PARSED_DIR):
    python src/data_pipeline/parse_vifoodlabel.py
"""

import json
import re
import unicodedata
import csv
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common.paths import RAW_LABELS_DIR, GOLD_PARSED_DIR, COMPLETENESS_REPORT

ALLERGEN_KEYWORDS = {
    "gluten": ["lúa mì", "bột mì", "lúa mạch", "yến mạch", "gluten", "wheat"],
    "giáp_xác": ["tôm", "cua", "giáp xác", "crustacean"],
    "trứng": ["trứng", "egg"],
    "cá": ["cá ", "cá,", "cá.", "nước mắm", "fish"],
    "đậu_phộng": ["đậu phộng", "lạc", "peanut", "peanuts"],
    "đậu_nành": ["đậu nành", "đậu tương", "soy", "soybean"],
    "sữa": ["sữa", "milk", "whey", "bơ sữa"],
    "hạt_cây": ["hạnh nhân", "almond", "hạt điều", "óc chó", "hồ đào", "hạt dẻ", "mắc ca",
                "hạt phỉ", "hazelnut", "tree nut", "tree nuts", "sheanut"],
    "cần_tây": ["cần tây", "celery"],
    "mù_tạt": ["mù tạt", "mustard"],
    "hạt_vừng": ["vừng", "mè", "sesame"],
    "sulfite": ["sulfit", "sulfite", "sulphite"],
    "lupin": ["lupin"],
    "nhuyễn_thể": ["nhuyễn thể", "ốc", "mực", "bạch tuộc", "sò", "mollusc"],
    "hải_sản": ["hải sản", "seafood"],
    "ngô": ["ngô", "bắp", "corn"],
    "dừa": ["dầu dừa", "dừa", "coconut"],
    "rong_biển": ["rong biển", "seaweed"],
}

# Từ khóa phân loại warning subtype - chỉ dùng để BÁO CÁO/QC, không ảnh hưởng đến việc
# tính allergen_final (allergen_final chỉ dựa trên named-keyword match + generic-allergy trigger)
SUBTYPE_PATTERNS = {
    "expiry_usage": ["hết hạn", "quá hạn", "hư hỏng", "hỏng", "dấu hiệu", "biến dạng", "lỗi"],
    "storage_instruction": ["bảo quản", "sau khi mở", "lắc đều", "dùng hết trong", "tránh ánh nắng", "để nơi khô ráo"],
    "child_supervision": ["trẻ em", "trẻ nhỏ", "tuổi", "giám sát", "tầm tay trẻ", "hóc", "nhai kỹ", "người già"],
    "desiccant_or_misc": ["hút ẩm", "hút oxy", "màu và mùi lạ", "lò vi sóng"],
}
GENERIC_ALLERGY_TRIGGER = ["dị ứng", "mẫn cảm", "allergic", "allergy"]


def norm(text):
    """Chuẩn hóa Unicode NFC + chữ thường. BẮT BUỘC trước khi so khớp từ khóa tiếng Việt."""
    return unicodedata.normalize("NFC", text).lower()


# Cụm cần "che" trước khi so khớp, tránh khớp nhầm nhóm dị nguyên
MASKS = {
    "sữa đậu nành": "đậu nành",   # sữa đậu nành không phải sữa động vật
    "sữa dừa": "dừa",
    "sữa hạt": "hạt",
}
# Từ khóa cần điều kiện bổ sung (lookahead) để tránh nhầm nghĩa
EXTRA_LOOKAHEAD = {"cá": r"(?!\s+nhân)"}   # "cá nhân" = personal, không phải cá


def _compile_keywords(keywords):
    pats = []
    for kw in dict.fromkeys(k.strip(" ,.") for k in keywords):  # bỏ khoảng trắng/dấu câu thừa, khử trùng
        extra = EXTRA_LOOKAHEAD.get(kw, "")
        pats.append(re.compile(rf"(?<!\w){re.escape(kw)}(?!\w){extra}"))
    return pats


KW_PATTERNS = {g: _compile_keywords(kws) for g, kws in ALLERGEN_KEYWORDS.items()}

# Câu mang nghĩa "có thể lẫn" (cảnh báo vết/dây chuyền) -> may_contain
TRACE_RE = re.compile(
    r"có thể (?:chứa|lẫn|có)|may contain|"
    r"(?:trên|cùng|chung)\s+(?:dây chuyền|cơ sở|nhà máy)|dây chuyền|facility|traces?|dấu vết"
)
# Đoạn phủ định: "Không chứa sữa" -> không được tính là dương
NEG_SPLIT_RE = re.compile(r"(?=\bkhông (?:chứa|có|sử dụng)\b|\bdoes not contain\b|\bfree from\b)")
NEG_START_RE = re.compile(r"\s*(?:sản phẩm\s+)?(?:hoàn toàn\s+)?(?:không (?:chứa|có|sử dụng)|does not contain|free from)\b")
SENT_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+|\n+")


def classify_warning_subtype(sentence, matched_named_allergen):
    """Chỉ dùng để thống kê/QC - không ảnh hưởng allergen_final."""
    s = norm(sentence)
    if matched_named_allergen:
        return "named_allergy"
    if any(kw in s for kw in GENERIC_ALLERGY_TRIGGER):
        return "generic_allergy_reference"
    for subtype, kws in SUBTYPE_PATTERNS.items():
        if any(kw in s for kw in kws):
            return subtype
    return "unclassified"


def find_groups(text):
    """Trả về set nhóm dị nguyên khớp trong 1 đoạn text (đã norm, đã che cụm)."""
    t = norm(text)
    for phrase, repl in MASKS.items():
        t = t.replace(phrase, repl)
    return {g for g, pats in KW_PATTERNS.items() if any(p.search(t) for p in pats)}


def find_allergen_keywords_in_text(text_list):
    return find_groups(" ; ".join(text_list))


def extract_allergen_info(warning_list, ingredient_list, additive_list):
    """
    Tách NGUỒN 1 (khai báo trong warning) và NGUỒN 2 (suy luận từ ingredient/additive) riêng biệt.
    Sửa so với v3: tách câu trước khi phân loại, so khớp theo ranh giới từ, chuẩn hóa NFC,
    xử lý phủ định, nhận diện cảnh báo dây chuyền/vết, che cụm 'sữa đậu nành'.
    """
    declared_contains, declared_may, negated = set(), set(), set()
    subtype_counts = {}
    has_generic_reference = False

    for entity_text in (warning_list or []):
        for sentence in filter(None, (s.strip() for s in SENT_SPLIT_RE.split(entity_text))):
            s_norm = norm(sentence)
            is_trace = bool(TRACE_RE.search(s_norm))
            matched_any = set()
            for seg in NEG_SPLIT_RE.split(s_norm):
                groups = find_groups(seg)
                if not groups:
                    continue
                matched_any |= groups
                if NEG_START_RE.match(seg):
                    negated |= groups
                elif is_trace:
                    declared_may |= groups
                else:
                    declared_contains |= groups

            subtype = classify_warning_subtype(sentence, bool(matched_any))
            subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1
            if subtype == "generic_allergy_reference":
                has_generic_reference = True

    inferred = set()
    if has_generic_reference:
        inferred = find_allergen_keywords_in_text((ingredient_list or []) + (additive_list or []))

    contains_final = sorted(declared_contains | inferred)
    may_final = sorted(declared_may - set(contains_final))
    return {
        "contains": contains_final,
        "may_contain": may_final,
        "source": {
            "declared_contains": sorted(declared_contains),
            "declared_may_contain": sorted(declared_may),
            "negated_groups": sorted(negated),
            "named_in_warning": sorted(declared_contains | declared_may),
            "inferred_from_ingredient_additive": sorted(inferred),
            "has_generic_allergy_reference": has_generic_reference,
        },
        "warning_subtype_counts": subtype_counts,
    }


def safe_get(record, key, default):
    val = record.get(key, default)
    return val if val is not None else default


def convert_record(record, image_id):
    ingredients = safe_get(record, "ingredient", [])
    additives = safe_get(record, "additive", [])
    nutrition = safe_get(record, "nutrition", [])
    warnings = safe_get(record, "warning", [])

    allergen_info = extract_allergen_info(warnings, ingredients, additives)

    return {
        "image_id": image_id,
        "product_name": safe_get(record, "product_name", None),
        "gold_ingredients_raw": ingredients,
        "gold_additives_raw": additives,
        "gold_nutrition": nutrition,
        "gold_warning_raw": warnings,
        "allergen_final": {
            "contains": allergen_info["contains"],
            "may_contain": allergen_info["may_contain"],
        },
        "allergen_debug": allergen_info["source"] | {"warning_subtype_counts": allergen_info["warning_subtype_counts"]},
        "origin": safe_get(record, "origin", None),
        "net_weight": safe_get(record, "net_weight", None),
        "mfg_date": safe_get(record, "mfg_date", None),
        "expiry_date": safe_get(record, "expiry_date", None),
        "completeness": {
            "has_ingredient": len(ingredients) > 0,
            "has_additive": len(additives) > 0,
            "has_nutrition": len(nutrition) > 0,
            "has_warning": len(warnings) > 0,
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels_dir", default=str(RAW_LABELS_DIR))
    parser.add_argument("--out_dir", default=str(GOLD_PARSED_DIR))
    parser.add_argument("--report_path", default=str(COMPLETENESS_REPORT))
    args = parser.parse_args()

    labels_dir = Path(args.labels_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(labels_dir.glob("*.json"))
    if not json_files:
        print(f"Không tìm thấy file .json nào trong {labels_dir}")
        return

    report_rows = []
    stats = {"total": 0, "has_ingredient": 0, "has_additive": 0, "has_nutrition": 0, "has_warning": 0,
             "full_record": 0, "has_allergen_final": 0, "inferred_used": 0}

    for fp in json_files:
        image_id = fp.stem
        with open(fp, "r", encoding="utf-8") as f:
            record = json.load(f)

        converted = convert_record(record, image_id)
        with open(out_dir / f"{image_id}.json", "w", encoding="utf-8") as f:
            json.dump(converted, f, ensure_ascii=False, indent=2)

        c = converted["completeness"]
        stats["total"] += 1
        for k in ("has_ingredient", "has_additive", "has_nutrition", "has_warning"):
            if c[k]:
                stats[k] += 1
        if all(c.values()):
            stats["full_record"] += 1

        n_allergen_final = len(converted["allergen_final"]["contains"]) + len(converted["allergen_final"]["may_contain"])
        if n_allergen_final > 0:
            stats["has_allergen_final"] += 1
        if converted["allergen_debug"]["inferred_from_ingredient_additive"]:
            stats["inferred_used"] += 1

        report_rows.append({
            "image_id": image_id,
            **c,
            "n_ingredients": len(converted["gold_ingredients_raw"]),
            "n_additives": len(converted["gold_additives_raw"]),
            "n_allergen_contains": len(converted["allergen_final"]["contains"]),
            "n_allergen_may_contain": len(converted["allergen_final"]["may_contain"]),
            "has_generic_allergy_reference": converted["allergen_debug"]["has_generic_allergy_reference"],
            "n_inferred_from_ingredient": len(converted["allergen_debug"]["inferred_from_ingredient_additive"]),
        })

    Path(args.report_path).parent.mkdir(parents=True, exist_ok=True)
    with open(args.report_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
        writer.writeheader()
        writer.writerows(report_rows)

    print(f"Đã xử lý {stats['total']} file.")
    print(f"  - Có ingredient : {stats['has_ingredient']} ({100*stats['has_ingredient']/stats['total']:.1f}%)")
    print(f"  - Có additive   : {stats['has_additive']} ({100*stats['has_additive']/stats['total']:.1f}%)")
    print(f"  - Có nutrition  : {stats['has_nutrition']} ({100*stats['has_nutrition']/stats['total']:.1f}%)")
    print(f"  - Có warning    : {stats['has_warning']} ({100*stats['has_warning']/stats['total']:.1f}%)")
    print(f"  - Đầy đủ cả 4   : {stats['full_record']} ({100*stats['full_record']/stats['total']:.1f}%)")
    print(f"  - Có allergen_final (>=1 nhãn) : {stats['has_allergen_final']} ({100*stats['has_allergen_final']/stats['total']:.1f}%)")
    print(f"  - Trong đó nhờ suy luận từ ingredient/additive (generic warning) : {stats['inferred_used']}")
    print(f"\nĐã ghi báo cáo: {args.report_path}")
    print(f"Đã ghi file convert: {out_dir}/")


if __name__ == "__main__":
    main()