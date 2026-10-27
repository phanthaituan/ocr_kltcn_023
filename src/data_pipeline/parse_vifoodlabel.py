"""
parse_vifoodlabel.py (v6 - Đã sửa toàn bộ 13 vấn đề P1..P13 và X1..X3 trong BaoCao_VanDe_2_Script.md)
Nâng cấp so với v5:
  1. [P1, P2] Tách câu cảnh báo ở cấp MỆNH ĐỀ (clause-level splitting) trước các từ khóa chuyển trạng thái
     ('không chứa', 'có chứa', 'có thể chứa', 'contains', 'may contain', 'does not contain'...).
     Nhờ vậy:
       - "Không chứa sữa, có chứa trứng." -> negated={'sữa'}, contains={'trứng'} (không bị lan phủ định).
       - "Có chứa sữa, có thể chứa trứng." -> contains={'sữa'}, may_contain={'trứng'} (sữa không bị hạ cấp thành may_contain).
  2. [P3, P4, P5] Sửa suy luận dị ứng từ ingredient/additive:
     - Đổi MASK 'sữa hạt' -> 'hạt cây' để khớp nhóm `hạt_cây` (P4).
     - Bổ sung bộ lọc ngữ cảnh âm tính (`ALLERGEN_FALSE_POS_MASKS`: 'bắp bò', 'bắp cải', 'mực in', 'hương sữa', 'hương bơ'...) (P3, P5).
     - Loại bỏ các nhóm đã nằm trong `negated` khỏi tập `inferred` (P3).
     - Thêm cờ cấp ảnh `allergen_needs_review` khi nhãn dị ứng có dùng suy luận từ ingredient (P3).
  3. [X1, P10, P6..P8, X2, X3] Dùng chung `extract_ingredient_head` và `classify_nutritional_item`
     từ `text_utils.py` (cắt sạch '%', loại trừ 'đạm đậu nành thủy phân', tự động điền `kb_id` nếu đã có `kb_aliases.csv`).
  4. [P11, P12, P13] Tách rõ `core_record` (có ingredient + additive), tính tỷ lệ `has_nutritional_b`
     trên mẫu số ảnh có `ingredient`, và thêm cờ `allergen_label_available` / `nutritional_label_available`
     để phân biệt ảnh thiếu vùng chụp với ảnh âm tính thật.

Cách chạy (từ thư mục gốc project):
    python src/data_pipeline/parse_vifoodlabel.py
    python src/data_pipeline/parse_vifoodlabel.py --selftest
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.common.paths import COMPLETENESS_REPORT, GOLD_PARSED_DIR, KB_DIR, RAW_LABELS_DIR
from text_utils import (
    TEXT_UTILS_VERSION,
    classify_nutritional_item,
    extract_ingredient_head,
    norm_text,
)

PARSER_RULES_VERSION = "6.0"

ALLERGEN_KEYWORDS = {
    "gluten": ["lúa mì", "bột mì", "lúa mạch", "yến mạch", "gluten", "wheat"],
    "giáp_xác": ["tôm", "cua", "giáp xác", "crustacean"],
    "trứng": ["trứng", "egg"],
    "cá": ["cá", "nước mắm", "fish"],
    "đậu_phộng": ["đậu phộng", "lạc", "peanut", "peanuts"],
    "đậu_nành": ["đậu nành", "đậu tương", "soy", "soybean"],
    "sữa": ["sữa", "milk", "whey", "bơ sữa"],
    "hạt_cây": [
        "hạt cây", "hạnh nhân", "almond", "hạt điều", "óc chó", "hồ đào",
        "hạt dẻ", "mắc ca", "hạt phỉ", "hazelnut", "tree nut", "tree nuts", "sheanut",
    ],
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


def norm(text: str) -> str:
    return norm_text(text)


# Sửa P4: "sữa hạt" -> "hạt cây" (khớp nhóm hạt_cây, không khớp nhầm nhóm sữa)
MASKS = {
    "sữa đậu nành": "đậu nành",
    "sữa dừa": "dừa",
    "sữa hạt": "hạt cây",
}

# Sửa P3, P5: Các cụm từ chứa từ khóa ngắn ("bắp", "mực", "sữa", "cá", "lạc"...) nhưng KHÔNG phải dị nguyên
ALLERGEN_FALSE_POS_RE = re.compile(
    r"\bbắp\s+(?:bò|heo|lợn|gà|đùi|cải|chuối|tay)\b|"
    r"\bmực\s+(?:in|nước|độ)\b|"
    r"\bhương\s+(?:sữa|bơ|phô\s*mai|tôm|cua|cá|mực|hải\s+sản|dừa|bắp|đậu\s+phộng|hạnh\s+nhân)(?:\s+tổng\s+hợp|\s+nhân\s+tạo|\s+tự\s+nhiên)?\b|"
    r"\blạc\s+quan\b|\bốc\s+vít\b",
    re.I,
)

EXTRA_LOOKAHEAD = {"cá": r"(?!\s+nhân)"}


def _compile_keywords(keywords):
    pats = []
    for kw in dict.fromkeys(k.strip(" ,.") for k in keywords):
        extra = EXTRA_LOOKAHEAD.get(kw, "")
        pats.append(re.compile(rf"(?<!\w){re.escape(kw)}(?!\w){extra}"))
    return pats


KW_PATTERNS = {g: _compile_keywords(kws) for g, kws in ALLERGEN_KEYWORDS.items()}

SENT_SPLIT_RE = re.compile(r"(?<=[.;!?])\s+|\n+")

# Sửa P1, P2: Tách mệnh đề (clause) ngay trước bất kỳ cụm chuyển đổi trạng thái nào:
# - Phủ định: "không chứa", "không có", "không sử dụng (trừ cho/nếu...)", "does not contain", "free from"
# - Cảnh báo vết (trace): "có thể chứa/lẫn/có", "may contain", "trên/cùng/chung dây chuyền..."
# - Khẳng định: "có chứa", "chứa:", "contains"
CLAUSE_SPLIT_RE = re.compile(
    r"(?="
    r"\bkhông\s+(?:chứa|có|sử\s+dụng(?!\s*(?:cho|nếu|đối\s+với|khi)\b))\b|"
    r"\bdoes\s+not\s+contain\b|\bfree\s+from\b|"
    r"\bcó\s+thể\s+(?:chứa|lẫn|có)\b|\bmay\s+contain\b|"
    r"\b(?:sản\s+xuất\s+)?(?:trên|cùng|chung)\s+(?:dây\s+chuyền|cơ\s+sở|nhà\s+máy)\b|"
    r"(?<!thể\s)(?<!không\s)\bcó\s+chứa\b|"
    r"\bcontains\b"
    r")",
    re.I,
)

TRACE_RE = re.compile(
    r"có\s+thể\s+(?:chứa|lẫn|có)|may\s+contain|"
    r"(?:trên|cùng|chung)\s+(?:dây\s+chuyền|cơ\s+sở|nhà\s+máy)|dây\s+chuyền|facility|traces?|dấu\s+vết",
    re.I,
)

NEG_CLAUSE_RE = re.compile(
    r"\b(?:không\s+(?:chứa|có|sử\s+dụng(?!\s*(?:cho|nếu|đối\s+với|khi)\b))|does\s+not\s+contain|free\s+from)\b",
    re.I,
)


def classify_warning_subtype(sentence: str, matched_named_allergen: bool) -> str:
    s = norm(sentence)
    if matched_named_allergen:
        return "named_allergy"
    if any(kw in s for kw in GENERIC_ALLERGY_TRIGGER):
        return "generic_allergy_reference"
    for subtype, kws in SUBTYPE_PATTERNS.items():
        if any(kw in s for kw in kws):
            return subtype
    return "unclassified"


def find_groups(text: str) -> set:
    t = norm(text)
    t = ALLERGEN_FALSE_POS_RE.sub(" ", t)
    for phrase, repl in MASKS.items():
        t = t.replace(phrase, repl)
    return {g for g, pats in KW_PATTERNS.items() if any(p.search(t) for p in pats)}


def find_allergen_keywords_in_text(text_list: list) -> set:
    return find_groups(" ; ".join(text_list or []))


def extract_allergen_info(warning_list: list, ingredient_list: list, additive_list: list) -> dict:
    """
    Trích xuất thông tin dị ứng mức ảnh (contains, may_contain) đã sửa P1, P2, P3, P4, P5.
    """
    declared_contains, declared_may, negated = set(), set(), set()
    subtype_counts = {}
    has_generic_reference = False

    for entity_text in (warning_list or []):
        for sentence in filter(None, (s.strip() for s in SENT_SPLIT_RE.split(entity_text))):
            s_norm = norm(sentence)
            matched_any = set()

            # Tách thành từng mệnh đề (clause) và xét trạng thái phủ định / trace riêng trên từng mệnh đề
            clauses = [c.strip(" ,;:-") for c in CLAUSE_SPLIT_RE.split(s_norm) if c and c.strip(" ,;:-")]
            """
            chưa hiểu
            """
            carry_trace = False
            for clause in clauses:
                # groups = find_groups(clause)
                # if not groups:
                #     continue
                # matched_any |= groups
                # if NEG_CLAUSE_RE.search(clause):
                #     negated |= groups
                # elif TRACE_RE.search(clause):
                #     declared_may |= groups
                # else:
                #     declared_contains |= groups
                groups = find_groups(clause)
                is_neg = bool(NEG_CLAUSE_RE.search(clause))
                has_trace = bool(TRACE_RE.search(clause))
                if not groups:
                    if has_trace     and not is_neg:
                        carry_trace = True
                    continue
                matched_any |= groups
                if is_neg:
                    negated |= groups
                    carry_trace = False
                elif has_trace or carry_trace:
                    declared_may |= groups
                    carry_trace = False
                else:
                    declared_contains |= groups

            subtype = classify_warning_subtype(sentence, bool(matched_any))
            subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1
            if subtype == "generic_allergy_reference":
                has_generic_reference = True

    inferred = set()
    if has_generic_reference:
        # Sửa P3: Loại bỏ những nhóm đã bị khẳng định là "Không chứa" (negated) khỏi tập suy luận
        inferred = find_allergen_keywords_in_text((ingredient_list or []) + (additive_list or [])) - negated

    contains_final = sorted((declared_contains - negated) | inferred)
    may_final = sorted((declared_may - negated) - set(contains_final))
    needs_review = bool(inferred - declared_contains)

    return {
        "contains": contains_final,
        "may_contain": may_final,
        "allergen_needs_review": needs_review,
        "source": {
            "declared_contains": sorted(declared_contains),
            "declared_may_contain": sorted(declared_may),
            "negated_groups": sorted(negated),
            "named_in_warning": sorted(declared_contains | declared_may),
            "inferred_from_ingredient_additive": sorted(inferred),
            "has_generic_allergy_reference": has_generic_reference,
            "allergen_needs_review": needs_review,
        },
        "warning_subtype_counts": subtype_counts,
    }


def split_composite_ingredient_item(raw_item: str) -> list:
    t = (raw_item or "").strip()
    if ":" in t:
        prefix, rest = t.split(":", 1)
        if len(prefix.strip().split()) <= 6 and "," in rest and "(" not in rest:
            sub_items = [x.strip() for x in rest.split(",") if x.strip()]
            if len(sub_items) >= 2:
                return sub_items
    return [t] if t else []


def load_kb_ingredient_alias_map(kb_dir: Path) -> dict:
    """
    Đọc bảng `kb_aliases.csv` (nếu đã tạo) để nối tự động `head_name` -> `entity_id` (sửa X2).
    Ưu tiên các alias không mơ hồ (is_ambiguous == False) và thuộc thực thể nguyên liệu (ING_*).
    """
    alias_csv = kb_dir / "kb_aliases.csv"
    if not alias_csv.exists():
        print(f"[CẢNH BÁO] Không thấy {alias_csv}: kb_id sẽ để trống. Chạy build_kb_aliases.py trước.")
        return {}
    mapping = {}
    with open(alias_csv, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            ent_id = (r.get("entity_id") or "").strip()
            alias_str = norm(r.get("alias") or "")
            if not alias_str or not ent_id.startswith("ING_"):
                continue
            if str(r.get("is_ambiguous", "")).strip().lower() == "true":
                continue
            if alias_str not in mapping:
                mapping[alias_str] = ent_id
    return mapping


def extract_nutritional_from_ingredients(ingredient_list: list, kb_alias_map: dict = None) -> dict:
    parsed_ingredients = []
    nutritional_items = []
    categories_present = set()

    for raw_entry in (ingredient_list or []):
        for sub_item in split_composite_ingredient_item(raw_entry):
            info = classify_nutritional_item(sub_item, kb_alias_map=kb_alias_map)
            if not info["name"]:
                continue
            info["kb_id_auto"] = info.pop("kb_id", None)
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


def convert_record(record: dict, image_id: str, kb_alias_map: dict = None) -> dict:
    ingredients = safe_get(record, "ingredient", [])
    additives = safe_get(record, "additive", [])
    nutrition_table = safe_get(record, "nutrition", [])
    warnings = safe_get(record, "warning", [])

    has_ing = len(ingredients) > 0
    has_add = len(additives) > 0
    has_warn = len(warnings) > 0
    has_nut_table = len(nutrition_table) > 0

    allergen_info = extract_allergen_info(warnings, ingredients, additives)
    nutr_b_info = extract_nutritional_from_ingredients(ingredients, kb_alias_map=kb_alias_map)

    debug_payload = dict(allergen_info["source"])
    debug_payload["warning_subtype_counts"] = allergen_info["warning_subtype_counts"]

    return {
        "image_id": image_id,
        "product_name": safe_get(record, "product_name", None),
        "gold_ingredients_raw": ingredients,
        "gold_ingredients_parsed": nutr_b_info["parsed_ingredients"],
        "gold_additives_raw": additives,
        "gold_nutrition_table_raw": nutrition_table,
        "gold_warning_raw": warnings,
        "nutritional_final": nutr_b_info["nutritional_final"],
        "allergen_final": {
            "contains": allergen_info["contains"],
            "may_contain": allergen_info["may_contain"],
        },
        "allergen_needs_review": allergen_info["allergen_needs_review"],
        "allergen_debug": debug_payload,
        "origin": safe_get(record, "origin", None),
        "net_weight": safe_get(record, "net_weight", None),
        "mfg_date": safe_get(record, "mfg_date", None),
        "expiry_date": safe_get(record, "expiry_date", None),
        "completeness": {
            "has_ingredient": has_ing,
            "has_additive": has_add,
            "has_warning": has_warn,
            "has_nutrition": has_nut_table,
            "is_core": (has_ing and has_add),
            "full_record_3fields": (has_ing and has_add and has_warn),
            "has_nutritional_b": nutr_b_info["nutritional_final"]["has_nutritional_ingredient"],
            # Sửa P12: Phân biệt rõ ảnh có đủ vùng văn bản để gán nhãn hay bị khuyết vùng chụp
            "allergen_label_available": has_warn,
            "nutritional_label_available": has_ing,
        },
        "rules_version": PARSER_RULES_VERSION,
        "text_utils_version": TEXT_UTILS_VERSION,
    }


def selftest() -> int:
    """Chạy bộ ca kiểm thử đề xuất ở Mục 5 của BaoCao_VanDe_2_Script.md."""
    fails = 0

    def check(desc, got, want):
        nonlocal fails
        ok = got == want
        fails += not ok
        print(("OK  " if ok else "FAIL"), desc, "->", got, "" if ok else f"(mong đợi: {want})")

    # Ca 1 (P1): Phủ định không lan sang mệnh đề khẳng định kế tiếp
    r1 = extract_allergen_info(["Không chứa sữa, có chứa trứng."], [], [])
    check("P1: Không chứa sữa, có chứa trứng.", (r1["contains"], r1["source"]["negated_groups"]), (["trứng"], ["sữa"]))

    # Ca 2 (P2): is_trace tính theo từng mệnh đề
    r2 = extract_allergen_info(["Có chứa sữa, có thể chứa trứng."], [], [])
    check("P2: Có chứa sữa, có thể chứa trứng.", (r2["contains"], r2["may_contain"]), (["sữa"], ["trứng"]))

    # Ca 3: Hai câu tách bằng dấu chấm
    r3 = extract_allergen_info(["Có chứa sữa. Có thể chứa trứng."], [], [])
    check("Ca chuẩn: Có chứa sữa. Có thể chứa trứng.", (r3["contains"], r3["may_contain"]), (["sữa"], ["trứng"]))

    # Ca 4: Tiếng Anh
    r4 = extract_allergen_info(["Contains: milk, soy. May contain wheat."], [], [])
    check("Ca EN: Contains milk, soy. May contain wheat.", (r4["contains"], r4["may_contain"]), (["sữa", "đậu_nành"], ["gluten"]))

    # Ca 5 (P3, P5): Suy luận từ ingredient không bắt nhầm Bắp bò, Mực in, Hương sữa
    r5 = extract_allergen_info(["Sản phẩm có thể gây dị ứng."], ["Bắp bò", "Mực in", "Hương sữa"], [])
    check("P3/P5: Suy luận không bắt nhầm Bắp bò, Mực in, Hương sữa", r5["contains"], [])

    # Ca 6 (P4): Sữa hạt -> hạt_cây
    r6 = extract_allergen_info(["Chứa sữa hạt."], [], [])
    check("P4: Chứa sữa hạt -> hạt_cây", r6["contains"], ["hạt_cây"])

    # Ca 7 (P10/K17): extract_ingredient_head cắt sạch %
    check("P10a: Đường 10%", extract_ingredient_head("Đường 10%"), "đường")
    check("P10b: Sữa bột 20% (từ sữa bò)", extract_ingredient_head("Sữa bột 20% (từ sữa bò)"), "sữa bột")
    check("P10c: Bột mì 15,5 %", extract_ingredient_head("Bột mì 15,5 %"), "bột mì")

    # Ca 8 (P6, P8): Đạm đậu nành thủy phân & Sữa giàu canxi
    c8a = classify_nutritional_item("Đạm đậu nành thủy phân")
    check("P6: Đạm đậu nành thủy phân -> False", c8a["nutritional"], False)
    c8b = classify_nutritional_item("Đạm đậu nành")
    check("P6 đối chứng: Đạm đậu nành -> isolated_protein", c8b["nutritional_category"], "isolated_protein")
    c8c = classify_nutritional_item("Sữa tươi giàu canxi")
    check("P8: Sữa tươi giàu canxi -> False", c8c["nutritional"], False)
    """
    chưa hiểu
    """
    r9 = extract_allergen_info(["Sản phẩm được sản xuất trên dây chuyền có chứa sữa, trứng."], [], [])
    check("Trace: trên dây chuyền có chứa", (r9["contains"], r9["may_contain"]), ([], ["sữa", "trứng"]))
    r10 = extract_allergen_info(["Có chứa sữa. Sản xuất trên dây chuyền có chứa trứng."], [], [])
    check("Trace tách câu", (r10["contains"], r10["may_contain"]), (["sữa"], ["trứng"]))
    check("Head: sữa từ 100% sữa tươi", extract_ingredient_head("Sữa từ 100% sữa tươi"), "sữa từ 100% sữa tươi")
    check("Head: vitamin c 16 mg/100 ml 20% rni", extract_ingredient_head("vitamin c 16 mg/100 ml 20% rni"), "vitamin c")
    check("EN hydrolyzed", classify_nutritional_item("Hydrolyzed vegetable protein")["nutritional"], False)
    check("Sữa bột giàu canxi", classify_nutritional_item("Sữa bột giàu canxi")["nutritional"], False)
    check("Đạm thực vật", classify_nutritional_item("Đạm thực vật")["nutritional_category"], "isolated_protein")

    print("\nKẾT QUẢ SELFTEST:", "TẤT CẢ ĐẠT (0 LỖI)" if fails == 0 else f"{fails} CA LỖI")
    return fails


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--selftest", action="store_true", help="Chạy kiểm thử các ca biên P1..P13")
    parser.add_argument("--labels_dir", default=str(RAW_LABELS_DIR))
    parser.add_argument("--out_dir", default=str(GOLD_PARSED_DIR))
    parser.add_argument("--kb_dir", default=str(KB_DIR))
    parser.add_argument("--report_path", default=str(COMPLETENESS_REPORT))
    args = parser.parse_args()

    if args.selftest:
        sys.exit(1 if selftest() else 0)

    labels_dir = Path(args.labels_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    json_files = sorted(labels_dir.glob("*.json"))
    if not json_files:
        print(f"Không tìm thấy file .json nào trong {labels_dir}")
        return

    kb_alias_map = load_kb_ingredient_alias_map(Path(args.kb_dir))

    report_rows = []
    stats = {
        "total": 0,
        "has_ingredient": 0,
        "has_additive": 0,
        "has_nutrition": 0,
        "has_nutritional_b": 0,
        "has_warning": 0,
        "is_core": 0,
        "full_record_3fields": 0,
        "full_record_4fields": 0,
        "has_allergen_final": 0,
        "inferred_used": 0,
        "allergen_needs_review": 0,
    }

    for fp in json_files:
        image_id = fp.stem
        with open(fp, "r", encoding="utf-8") as f:
            record = json.load(f)

        converted = convert_record(record, image_id, kb_alias_map=kb_alias_map)
        with open(out_dir / f"{image_id}.json", "w", encoding="utf-8") as f:
            json.dump(converted, f, ensure_ascii=False, indent=2)

        c = converted["completeness"]
        stats["total"] += 1
        for k in ("has_ingredient", "has_additive", "has_nutrition", "has_nutritional_b", "has_warning", "is_core", "full_record_3fields"):
            if c[k]:
                stats[k] += 1
        if c["has_ingredient"] and c["has_additive"] and c["has_nutrition"] and c["has_warning"]:
            stats["full_record_4fields"] += 1

        n_allergen_final = len(converted["allergen_final"]["contains"]) + len(converted["allergen_final"]["may_contain"])
        if n_allergen_final > 0:
            stats["has_allergen_final"] += 1
        if converted["allergen_debug"]["inferred_from_ingredient_additive"]:
            stats["inferred_used"] += 1
        if converted["allergen_needs_review"]:
            stats["allergen_needs_review"] += 1

        report_rows.append({
            "image_id": image_id,
            "has_ingredient": c["has_ingredient"],
            "has_additive": c["has_additive"],
            "has_nutrition": c["has_nutrition"],
            "has_nutritional_b": c["has_nutritional_b"],
            "has_warning": c["has_warning"],
            "is_core": c["is_core"],
            "allergen_label_available": c["allergen_label_available"],
            "nutritional_label_available": c["nutritional_label_available"],
            "allergen_needs_review": converted["allergen_needs_review"],
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
    with open(args.report_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(report_rows[0].keys()))
        writer.writeheader()
        writer.writerows(report_rows)

    n_ing_imgs = max(stats["has_ingredient"], 1)
    n_warn_imgs = max(stats["has_warning"], 1)
    print(f"Đã xử lý {stats['total']} file.")
    print(f"  - Có ingredient                   : {stats['has_ingredient']}/{stats['total']} ({100*stats['has_ingredient']/stats['total']:.1f}%)")
    print(f"  - Có additive                     : {stats['has_additive']}/{stats['total']} ({100*stats['has_additive']/stats['total']:.1f}%)")
    print(f"  - Có warning                      : {stats['has_warning']}/{stats['total']} ({100*stats['has_warning']/stats['total']:.1f}%)")
    print(f"  - Core subset (ing + add)         : {stats['is_core']}/{stats['total']} ({100*stats['is_core']/stats['total']:.1f}%)")
    print(f"  - Đủ 3 field chính (ing+add+warn) : {stats['full_record_3fields']}/{stats['total']} ({100*stats['full_record_3fields']/stats['total']:.1f}%)")
    print(f"  - Có chất dinh dưỡng Phương án B  : {stats['has_nutritional_b']}/{stats['has_ingredient']} ảnh có ingredient ({100*stats['has_nutritional_b']/n_ing_imgs:.1f}%)")
    print(f"  - Có allergen_final (>=1 nhãn)    : {stats['has_allergen_final']}/{stats['has_warning']} ảnh có warning ({100*stats['has_allergen_final']/n_warn_imgs:.1f}%)")
    print(f"  - Cần duyệt tay dị ứng suy luận   : {stats['allergen_needs_review']} ảnh")
    print(f"\nĐã ghi báo cáo: {args.report_path}")
    print(f"Đã ghi file convert: {out_dir}/")


if __name__ == "__main__":
    main()