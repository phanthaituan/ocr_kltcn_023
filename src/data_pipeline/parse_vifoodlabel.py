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

# """
# parse_vifoodlabel.py (v4)
# Nâng cấp so với v2:
#   1. Phân loại warning thành các subtype: expiry_usage, storage_instruction,
#      child_supervision, generic_allergy_reference, named_allergy, desiccant_or_misc, unclassified
#   2. Khi gặp "generic_allergy_reference" (cảnh báo dị ứng nhưng KHÔNG nêu tên chất cụ thể,
#      vd "dị ứng với các thành phần trên"): tự động quét chéo sang chính field ingredient +
#      additive của ảnh đó bằng ALLERGEN_KEYWORDS để suy ra allergen cụ thể - vì nhãn VN
#      thường đặt allergen ngay trong ingredient list, không lặp lại ở warning.
#   3. allergen_final = hợp nhất từ 2 nguồn (named trong warning + suy luận từ ingredient/additive),
#      có "source" để biết nhãn đến từ đâu (phục vụ review sau này).

# Cách chạy (từ thư mục gốc project; mặc định đọc RAW_LABELS_DIR, ghi GOLD_PARSED_DIR):
#     python src/data_pipeline/parse_vifoodlabel.py
# """

# import json
# import re
# import unicodedata
# import csv
# import argparse
# import sys
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


# def norm(text):
#     """Chuẩn hóa Unicode NFC + chữ thường. BẮT BUỘC trước khi so khớp từ khóa tiếng Việt."""
#     return unicodedata.normalize("NFC", text).lower()


# # Cụm cần "che" trước khi so khớp, tránh khớp nhầm nhóm dị nguyên
# MASKS = {
#     "sữa đậu nành": "đậu nành",   # sữa đậu nành không phải sữa động vật
#     "sữa dừa": "dừa",
#     "sữa hạt": "hạt",
# }
# # Từ khóa cần điều kiện bổ sung (lookahead) để tránh nhầm nghĩa
# EXTRA_LOOKAHEAD = {"cá": r"(?!\s+nhân)"}   # "cá nhân" = personal, không phải cá


# def _compile_keywords(keywords):
#     pats = []
#     for kw in dict.fromkeys(k.strip(" ,.") for k in keywords):  # bỏ khoảng trắng/dấu câu thừa, khử trùng
#         extra = EXTRA_LOOKAHEAD.get(kw, "")
#         pats.append(re.compile(rf"(?<!\w){re.escape(kw)}(?!\w){extra}"))
#     return pats


# KW_PATTERNS = {g: _compile_keywords(kws) for g, kws in ALLERGEN_KEYWORDS.items()}

# # Câu mang nghĩa "có thể lẫn" (cảnh báo vết/dây chuyền) -> may_contain
# TRACE_RE = re.compile(
#     r"có thể (?:chứa|lẫn|có)|may contain|"
#     r"(?:trên|cùng|chung)\s+(?:dây chuyền|cơ sở|nhà máy)|dây chuyền|facility|traces?|dấu vết"
# )
# # Đoạn phủ định: "Không chứa sữa" -> không được tính là dương
# NEG_SPLIT_RE = re.compile(r"(?=\bkhông (?:chứa|có|sử dụng(?!\s*(?:cho|nếu|đối với|khi)\b))\b|\bdoes not contain\b|\bfree from\b)")
# NEG_START_RE = re.compile(r"\s*(?:sản phẩm\s+)?(?:hoàn toàn\s+)?(?:không (?:chứa|có|sử dụng(?!\s*(?:cho|nếu|đối với|khi)\b))|does not contain|free from)\b")
# SENT_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+|\n+")


# def classify_warning_subtype(sentence, matched_named_allergen):
#     """Chỉ dùng để thống kê/QC - không ảnh hưởng allergen_final."""
#     s = norm(sentence)
#     if matched_named_allergen:
#         return "named_allergy"
#     if any(kw in s for kw in GENERIC_ALLERGY_TRIGGER):
#         return "generic_allergy_reference"
#     for subtype, kws in SUBTYPE_PATTERNS.items():
#         if any(kw in s for kw in kws):
#             return subtype
#     return "unclassified"


# def find_groups(text):
#     """Trả về set nhóm dị nguyên khớp trong 1 đoạn text (đã norm, đã che cụm)."""
#     t = norm(text)
#     for phrase, repl in MASKS.items():
#         t = t.replace(phrase, repl)
#     return {g for g, pats in KW_PATTERNS.items() if any(p.search(t) for p in pats)}


# def find_allergen_keywords_in_text(text_list):
#     return find_groups(" ; ".join(text_list))


# def extract_allergen_info(warning_list, ingredient_list, additive_list):
#     """
#     Tách NGUỒN 1 (khai báo trong warning) và NGUỒN 2 (suy luận từ ingredient/additive) riêng biệt.
#     Sửa so với v3: tách câu trước khi phân loại, so khớp theo ranh giới từ, chuẩn hóa NFC,
#     xử lý phủ định, nhận diện cảnh báo dây chuyền/vết, che cụm 'sữa đậu nành'.
#     """
#     declared_contains, declared_may, negated = set(), set(), set()
#     subtype_counts = {}
#     has_generic_reference = False

#     for entity_text in (warning_list or []):
#         for sentence in filter(None, (s.strip() for s in SENT_SPLIT_RE.split(entity_text))):
#             s_norm = norm(sentence)
#             is_trace = bool(TRACE_RE.search(s_norm))
#             matched_any = set()
#             for seg in NEG_SPLIT_RE.split(s_norm):
#                 groups = find_groups(seg)
#                 if not groups:
#                     continue
#                 matched_any |= groups
#                 if NEG_START_RE.match(seg):
#                     negated |= groups
#                 elif is_trace:
#                     declared_may |= groups
#                 else:
#                     declared_contains |= groups

#             subtype = classify_warning_subtype(sentence, bool(matched_any))
#             subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1
#             if subtype == "generic_allergy_reference":
#                 has_generic_reference = True

#     inferred = set()
#     if has_generic_reference:
#         inferred = find_allergen_keywords_in_text((ingredient_list or []) + (additive_list or []))

#     contains_final = sorted(declared_contains | inferred)
#     may_final = sorted(declared_may - set(contains_final))
#     return {
#         "contains": contains_final,
#         "may_contain": may_final,
#         "source": {
#             "declared_contains": sorted(declared_contains),
#             "declared_may_contain": sorted(declared_may),
#             "negated_groups": sorted(negated),
#             "named_in_warning": sorted(declared_contains | declared_may),
#             "inferred_from_ingredient_additive": sorted(inferred),
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

#     Path(args.report_path).parent.mkdir(parents=True, exist_ok=True)
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
parse_vifoodlabel.py (v5 - Tích hợp Phương án B cho nhóm Dinh dưỡng)
Nâng cấp so với v4:
  1. Giữ `gold_nutrition_table_raw` (field `nutrition` gốc của ViFoodLabel chỉ để tham khảo),
     và TẠO MỚI `gold_ingredients_parsed` + `nutritional_final` trích xuất trực tiếp từ
     bảng thành phần (`ingredient`) theo đúng Phương án B (KeHoach_4Tuan.md & KeHoach_4Tuan_CapNhat.md):
       - Nhóm chất bổ sung vai trò dinh dưỡng trong danh sách thành phần:
         + vitamin             : các loại vitamin (A, B1..B12, C, D3, E, K1, K2, acid folic, biotin, niacin...)
         + mineral_trace       : khoáng chất & vi chất bổ sung (canxi/calci, sắt, kẽm, magie, selen, muối i-ốt...)
         + fiber_prebiotic     : chất xơ bổ sung & prebiotics (inulin, FOS, GOS, IMO / mạch nha isomalto oligo, chất xơ hòa tan...)
         + isolated_protein    : đạm tách chiết / tinh chế (đạm đậu nành, đạm whey, protein sữa, caseinat...)
         + amino_omega_bioactive: axit amin, omega/DHA/EPA, MCT, taurin, lysin, cholin, carnitin, sữa non (colostrum), nucleotid...
         + probiotic           : lợi khuẩn / men vi sinh (Lactobacillus, Bifidobacterium, Streptococcus thermophilus...)
       - Nguyên liệu nền (đường, muối thường, nước, bột mì, dầu thực vật, thịt, cá...) -> `nutritional = False`.
  2. Tách chuỗi nguyên liệu ghép có dấu hai chấm (vd "Gạo sữa: bột gạo, sữa bột, các khoáng chất")
     và chỉ xét từ khóa dinh dưỡng trên tên chính (`head_name`) để tránh bắt nhầm nguyên liệu nền
     chứa chất chống oxy hóa trong ngoặc (vd "dầu thực vật (chứa tocopherol)").
  3. Đã sửa lỗi regex phủ định `NEG_SPLIT_RE` / `NEG_START_RE` ("Không sử dụng cho người dị ứng với..." không bị tính nhầm vào phủ định).

Cách chạy (từ thư mục gốc project; mặc định đọc RAW_LABELS_DIR, ghi GOLD_PARSED_DIR):
    python src/data_pipeline/parse_vifoodlabel.py
"""

import argparse
import csv
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from src.common.paths import COMPLETENESS_REPORT, GOLD_PARSED_DIR, RAW_LABELS_DIR

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

SUBTYPE_PATTERNS = {
    "expiry_usage": ["hết hạn", "quá hạn", "hư hỏng", "hỏng", "dấu hiệu", "biến dạng", "lỗi"],
    "storage_instruction": ["bảo quản", "sau khi mở", "lắc đều", "dùng hết trong", "tránh ánh nắng", "để nơi khô ráo"],
    "child_supervision": ["trẻ em", "trẻ nhỏ", "tuổi", "giám sát", "tầm tay trẻ", "hóc", "nhai kỹ", "người già"],
    "desiccant_or_misc": ["hút ẩm", "hút oxy", "màu và mùi lạ", "lò vi sóng"],
}
GENERIC_ALLERGY_TRIGGER = ["dị ứng", "mẫn cảm", "allergic", "allergy"]


def norm(text):
    """Chuẩn hóa Unicode NFC + chữ thường + gom khoảng trắng."""
    t = unicodedata.normalize("NFC", text or "").lower().strip()
    return re.sub(r"\s+", " ", t)


# --- PHẦN 1: QUY TẮC DỊ ỨNG (ALLERGEN) ---
MASKS = {
    "sữa đậu nành": "đậu nành",
    "sữa dừa": "dừa",
    "sữa hạt": "hạt",
}
EXTRA_LOOKAHEAD = {"cá": r"(?!\s+nhân)"}


def _compile_keywords(keywords):
    pats = []
    for kw in dict.fromkeys(k.strip(" ,.") for k in keywords):
        extra = EXTRA_LOOKAHEAD.get(kw, "")
        pats.append(re.compile(rf"(?<!\w){re.escape(kw)}(?!\w){extra}"))
    return pats


KW_PATTERNS = {g: _compile_keywords(kws) for g, kws in ALLERGEN_KEYWORDS.items()}

TRACE_RE = re.compile(
    r"có thể (?:chứa|lẫn|có)|may contain|"
    r"(?:trên|cùng|chung)\s+(?:dây chuyền|cơ sở|nhà máy)|dây chuyền|facility|traces?|dấu vết"
)
NEG_SPLIT_RE = re.compile(
    r"(?=\bkhông (?:chứa|có|sử dụng(?!\s*(?:cho|nếu|đối với|khi)\b))\b|\bdoes not contain\b|\bfree from\b)"
)
NEG_START_RE = re.compile(
    r"\s*(?:sản phẩm\s+)?(?:hoàn toàn\s+)?(?:không (?:chứa|có|sử dụng(?!\s*(?:cho|nếu|đối với|khi)\b))|does not contain|free from)\b"
)
SENT_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+|\n+")


def classify_warning_subtype(sentence, matched_named_allergen):
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
    t = norm(text)
    for phrase, repl in MASKS.items():
        t = t.replace(phrase, repl)
    return {g for g, pats in KW_PATTERNS.items() if any(p.search(t) for p in pats)}


def find_allergen_keywords_in_text(text_list):
    return find_groups(" ; ".join(text_list))


def extract_allergen_info(warning_list, ingredient_list, additive_list):
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


# --- PHẦN 2: QUY TẮC NHÓM CHẤT DINH DƯỠNG THEO PHƯƠNG ÁN B (TRÍCH TỪ INGREDIENT LIST) ---
NUTRITIONAL_PATTERNS = {
    "vitamin": [
        r"\bvitamin\b", r"\bvit\b", r"\bretinol\b", r"\bretinyl\b", r"\bbeta[\s\-]?caroten",
        r"\bthiamin", r"\briboflavin", r"\bniacin", r"\bnicotinamid",
        r"\bpyridoxin", r"\bfolic\b", r"\bfolat", r"\bpteroylmonoglutamic",
        r"\bcobalamin", r"\bcyanocobalamin", r"\bbiotin\b", r"\bpantothenic", r"\bpantothenat",
        r"\bcholecalciferol", r"\bergocalciferol", r"\btocopherol", r"\btocopheryl",
        r"\bphylloquinon", r"\bphytomenadion", r"\bmenaquinon",
    ],
    "mineral_trace": [
        r"\bkhoáng\s+chất\b", r"\bcác\s+khoáng\s+chất\b", r"\bhỗn\s+hợp\s+khoáng\b", r"\bmineral",
        r"\bmuối\s+i[\s\-]?ốt\b", r"\bmuối\s+iod\b", r"\bmuối\s+tinh\s+chế\s+i[\s\-]?ốt\b",
        r"\biodized\s+salt\b", r"\bkali\s+iodat\b", r"\bkali\s+iodid\b",
        r"\bcanxi\b", r"\bcalci\b", r"\bcalcium\b", r"\btricalci\b", r"\bdicalci\b",
        r"\bsắt\b", r"\biron\b", r"\bferric\b", r"\bferrous\b",
        r"\bkẽm\b", r"\bzinc\b",
        r"\bmagie\b", r"\bmagiê\b", r"\bmagnesi",
        r"\bselen", r"\bmangan", r"\bđồng\s+(?:sulfat|gluconat)\b", r"\bcopper\b", r"\bcrôm\b", r"\bchrom",
    ],
    "fiber_prebiotic": [
        r"\bchất\s+xơ\b", r"\bfiber\b", r"\bfibre\b",
        r"\binulin\b", r"\bfos\b", r"\bgos\b",
        r"\bfructo[\s\-]?oligosaccharid", r"\bgalacto[\s\-]?oligosaccharid", r"\boligofructose\b",
        r"\bisomalto[\s\-]?oligo", r"\bmạch\s+nha\s+imo\b", r"\bmạch\s+nha\s*\(\s*imo\s*\)",
        r"\bpolydextrose\b", r"\bdextrin\s+kháng\b", r"\bresistant\s+dextrin",
    ],
    "isolated_protein": [
        r"\bprotein\b", r"\bđạm\s+đậu\s+nành\b", r"\bchất\s+đạm\s+đậu\s+nành\b",
        r"\bđạm\s+sữa\b", r"\bđạm\s+whey\b",
        r"\bwhey\s+protein\b", r"\bsoy\s+protein\b", r"\bmilk\s+protein\b", r"\bcaseinat",
    ],
    "amino_omega_bioactive": [
        r"\bdha\b", r"\bepa\b", r"\bomega[\s\-]?[369]\b", r"\bdầu\s+cá\b", r"\bbột\s+dầu\s+cá\b",
        r"\btaurin", r"\blysin", r"\bcarnitin", r"\bcholin", r"\binositol\b",
        r"\blutein\b", r"\bnucleotid", r"\bcolostrum\b", r"\bsữa\s+non\b", r"\bcolosigg\b",
        r"\bcollagen\b", r"\bgaba\b", r"\bmct\b", r"\bhmo\b", r"\b2'-fl\b",
    ],
    "probiotic": [
        r"\blactobacillus\b", r"\bbifidobacterium\b", r"\bstreptococcus\s+thermophilus\b",
        r"\bmen\s+streptococcus\b", r"\bbacillus\s+coagulans\b", r"\blactococcus\s+lactis\b",
        r"\bprobiotic", r"\bpostbiotic", r"\blợi\s+khuẩn\b", r"\bmen\s+vi\s+sinh\b",
    ],
}

COMPILED_NUTR = {
    cat: [re.compile(p, re.I) for cat_p in [pats] for p in cat_p]
    for cat, pats in NUTRITIONAL_PATTERNS.items()
}

# Các cụm từ dễ gây dương tính giả cần loại trừ (vỏ xúc xích collagen, cá đồng, đạm thủy phân làm chất điều vị...)
NEGATIVE_NUTR_HEAD_RE = re.compile(
    r"\bcá\s+đồng\b|\bđồng\s+nhất\b|\bđồng\s+quê\b|\bsắt\s+lát\b|"
    r"\bvỏ\s+bọc\b|\bruột\s+collagen\b|"
    r"\bprotein\s+thực\s+vật\s+thủy\s+phân\b|\bđạm\s+thực\s+vật\s+thủy\s+phân\b|"
    r"\bgia\s+vị\b|\bhỗn\s+hợp\s+protein\s+sấy\s+vị\b|\bgiả\s+thịt\b",
    re.I,
)
GENERIC_SUPPLEMENT_HEADS = {"chất bổ sung", "vi chất dinh dưỡng", "hỗn hợp dưỡng chất", "bột tăng cường dinh dưỡng"}


def extract_ingredient_head(raw_term: str) -> str:
    """
    Lấy tên chính (head name) của 1 mục nguyên liệu trước dấu ngoặc đầu tiên,
    lược bỏ phần trăm/định lượng ở cuối.
    """
    t = norm(raw_term)
    t = re.sub(r"^[\s\-–—•*:.,;]+", "", t)
    head = re.split(r"[\(\[]", t, maxsplit=1)[0].strip()
    head = re.sub(
        r"\s+\d+(?:[.,]\d+)?\s*(?:%|g|mg|kg|ml|l|g/kg|mg/kg|mg/l|g/l|mcg|µg|iu)(?:\s+\d+\s*%\s*rni)?\b.*$",
        "",
        head,
    ).strip()
    head = re.sub(r"[\s,:;.\-]+$", "", head).strip()
    return head


def split_composite_ingredient_item(raw_item: str) -> list:
    """
    Một số nhãn gom cả gói con vào 1 phần tử có dấu ':', vd:
    'Gạo sữa: bột gạo, sữa bột, chất xơ hòa tan inulin, đạm whey, các khoáng chất'
    Nếu phần trước dấu ':' là nhãn gói/phần và phía sau có >=2 dấu phẩy ngoài ngoặc,
    tách thành các mục con để không bỏ sót chất dinh dưỡng và không gán nhầm cho cả cụm.
    """
    t = (raw_item or "").strip()
    if ":" in t:
        prefix, rest = t.split(":", 1)
        if len(prefix.strip().split()) <= 6 and "," in rest and "(" not in rest:
            sub_items = [x.strip() for x in rest.split(",") if x.strip()]
            if len(sub_items) >= 2:
                return sub_items
    return [t] if t else []


def classify_nutritional_item(raw_item: str) -> dict:
    """
    Phân loại 1 mục nguyên liệu theo Phương án B (Dinh dưỡng trong bảng thành phần).
    Trả về dict khớp với Schema mục 5 của KeHoach_4Tuan_CapNhat.md:
      {"name": head_name, "raw": raw_item, "nutritional": bool, "nutritional_category": str|None}
    """
    t_norm = norm(raw_item)
    head = extract_ingredient_head(t_norm)
    if not head or NEGATIVE_NUTR_HEAD_RE.search(head):
        return {"name": head or t_norm, "raw": raw_item, "nutritional": False, "nutritional_category": None}

    # Mặc định chỉ kiểm tra trên `head` (trước dấu ngoặc) để tránh bắt nhầm nguyên liệu nền có phụ gia/vitamin trong ngoặc.
    # Ngoại lệ: nếu head là 'chất bổ sung' hoặc 'mạch nha (imo)' thì xét cả chuỗi.
    target = t_norm if (head in GENERIC_SUPPLEMENT_HEADS or head == "mạch nha") else head

    for cat, regexes in COMPILED_NUTR.items():
        if any(r.search(target) for r in regexes):
            return {"name": head, "raw": raw_item, "nutritional": True, "nutritional_category": cat}

    return {"name": head, "raw": raw_item, "nutritional": False, "nutritional_category": None}


def extract_nutritional_from_ingredients(ingredient_list: list) -> dict:
    """
    Áp dụng Phương án B lên toàn bộ danh sách `ingredient` của 1 ảnh.
    Trả về:
      - parsed_ingredients: list[{"name", "raw", "nutritional", "nutritional_category"}]
      - nutritional_final : thông tin tổng hợp các chất dinh dưỡng tìm thấy trong bảng thành phần
    """
    parsed_ingredients = []
    nutritional_items = []
    categories_present = set()

    for raw_entry in (ingredient_list or []):
        for sub_item in split_composite_ingredient_item(raw_entry):
            info = classify_nutritional_item(sub_item)
            parsed_ingredients.append(info)
            if info["nutritional"]:
                nutritional_items.append(info)
                categories_present.add(info["nutritional_category"])

    unique_nutr_names = sorted(dict.fromkeys(x["name"] for x in nutritional_items))
    return {
        "parsed_ingredients": parsed_ingredients,
        "nutritional_final": {
            "has_nutritional_ingredient": len(nutritional_items) > 0,
            "n_nutritional_ingredients": len(nutritional_items),
            "nutritional_names": unique_nutr_names,
            "nutritional_categories": sorted(categories_present),
            "items": nutritional_items,
        },
    }


def safe_get(record, key, default):
    val = record.get(key, default)
    return val if val is not None else default


def convert_record(record, image_id):
    ingredients = safe_get(record, "ingredient", [])
    additives = safe_get(record, "additive", [])
    nutrition_table = safe_get(record, "nutrition", [])
    warnings = safe_get(record, "warning", [])

    allergen_info = extract_allergen_info(warnings, ingredients, additives)
    nutr_b_info = extract_nutritional_from_ingredients(ingredients)

    return {
        "image_id": image_id,
        "product_name": safe_get(record, "product_name", None),
        "gold_ingredients_raw": ingredients,
        "gold_ingredients_parsed": nutr_b_info["parsed_ingredients"],
        "gold_additives_raw": additives,
        "gold_nutrition_table_raw": nutrition_table,  # giữ bảng nutrition facts gốc chỉ để tham khảo
        "gold_warning_raw": warnings,
        "nutritional_final": nutr_b_info["nutritional_final"],  # GOLD PHƯƠNG ÁN B (trích từ bảng thành phần)
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
            "has_nutrition": len(nutrition_table) > 0,
            "has_nutritional_b": nutr_b_info["nutritional_final"]["has_nutritional_ingredient"],
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
    stats = {
        "total": 0,
        "has_ingredient": 0,
        "has_additive": 0,
        "has_nutrition": 0,
        "has_nutritional_b": 0,
        "has_warning": 0,
        "full_record": 0,
        "has_allergen_final": 0,
        "inferred_used": 0,
    }

    for fp in json_files:
        image_id = fp.stem
        with open(fp, "r", encoding="utf-8") as f:
            record = json.load(f)

        converted = convert_record(record, image_id)
        with open(out_dir / f"{image_id}.json", "w", encoding="utf-8") as f:
            json.dump(converted, f, ensure_ascii=False, indent=2)

        c = converted["completeness"]
        stats["total"] += 1
        for k in ("has_ingredient", "has_additive", "has_nutrition", "has_nutritional_b", "has_warning"):
            if c[k]:
                stats[k] += 1
        if c["has_ingredient"] and c["has_additive"] and c["has_nutrition"] and c["has_warning"]:
            stats["full_record"] += 1

        n_allergen_final = len(converted["allergen_final"]["contains"]) + len(converted["allergen_final"]["may_contain"])
        if n_allergen_final > 0:
            stats["has_allergen_final"] += 1
        if converted["allergen_debug"]["inferred_from_ingredient_additive"]:
            stats["inferred_used"] += 1

        report_rows.append({
            "image_id": image_id,
            **c,
            "n_ingredients": len(converted["gold_ingredients_parsed"]),
            "n_nutritional_b": converted["nutritional_final"]["n_nutritional_ingredients"],
            "nutritional_b_categories": ";".join(converted["nutritional_final"]["nutritional_categories"]),
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
    print(f"  - Có ingredient                   : {stats['has_ingredient']} ({100*stats['has_ingredient']/stats['total']:.1f}%)")
    print(f"  - Có additive                     : {stats['has_additive']} ({100*stats['has_additive']/stats['total']:.1f}%)")
    print(f"  - Có bảng nutrition (tham khảo)   : {stats['has_nutrition']} ({100*stats['has_nutrition']/stats['total']:.1f}%)")
    print(f"  - Có chất dinh dưỡng Phương án B  : {stats['has_nutritional_b']} ({100*stats['has_nutritional_b']/stats['total']:.1f}%)")
    print(f"  - Có warning                      : {stats['has_warning']} ({100*stats['has_warning']/stats['total']:.1f}%)")
    print(f"  - Có allergen_final (>=1 nhãn)    : {stats['has_allergen_final']} ({100*stats['has_allergen_final']/stats['total']:.1f}%)")
    print(f"  - Nhờ suy luận từ ingredient      : {stats['inferred_used']}")
    print(f"\nĐã ghi báo cáo: {args.report_path}")
    print(f"Đã ghi file convert: {out_dir}/")


if __name__ == "__main__":
    main()