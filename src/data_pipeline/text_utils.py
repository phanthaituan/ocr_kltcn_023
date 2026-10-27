"""
text_utils.py
Module dùng chung (Single Source of Truth) cho toàn bộ xử lý văn bản, chuẩn hóa tên nguyên liệu
(`extract_ingredient_head`) và phân loại nhóm chất dinh dưỡng Phương án B (6 nhóm) giữa
`parse_vifoodlabel.py` và `build_kb_aliases.py`.

Giải quyết triệt để các vấn đề trong BaoCao_VanDe_2_Script.md:
  - X1, P10, K17 : Một hàm `extract_ingredient_head` duy nhất; sửa lỗi `\b` sau ký tự `%`
                   khiến phần trăm cuối chuỗi ("Đường 10%", "Bột mì 15,5 %") không được cắt bỏ.
  - K11, K12, X3 : Một bộ quy tắc phân loại dinh dưỡng 6 nhóm duy nhất (`classify_nutritional_item`)
                   dùng chung cho cả Gold Parser và KB Builder.
  - P6, P7, P8   : Loại trừ đạm/protein thủy phân các loại ("đạm đậu nành thủy phân"),
                   tách rõ các ca biên và lọc mảnh vụn/chuỗi rỗng (K16).
"""

import re
import unicodedata

TEXT_UTILS_VERSION = "2.0"


def norm_text(text: str) -> str:
    """Chuẩn hóa Unicode NFC, chữ thường, gom khoảng trắng."""
    t = unicodedata.normalize("NFC", str(text or "")).strip().lower()
    return re.sub(r"\s+", " ", t)


# Regex cắt số lượng / phần trăm / định lượng ở cuối hoặc giữa head
# Sửa lỗi P10/K17: Ký tự '%' không phải word-char nên KHÔNG đặt \b sau '%', tách riêng khỏi nhóm đơn vị chữ.
_TRAILING_QTY_RE = re.compile(
    r"(?:\s*[:\-–—]?\s*)"
    r"\d+(?:[.,]\d+)?\s*"
    r"(?:%|(?:g|mg|kg|ml|l|g/kg|mg/kg|mg/l|g/l|mcg|µg|iu|kcal|kj|°n)\b)"
     r"(?:[\s/]+|\d+(?:[.,]\d+)?|%|\b(?:rni|g|mg|kg|ml|l|mcg|µg|iu|kcal|kj)\b)*$",
    re.I,
)

_LEADING_QTY_RE = re.compile(r"^(?:(?:tối\s+thiểu|ít\s+nhất|hơn)\s+)?\d+(?:[.,]\d+)?\s*%\s*", re.I)

# Các mảnh vụn không phải tên nguyên liệu (K16)
_FRAGMENT_RE = re.compile(
    r"^(?:dùng cho thực phẩm|trong đó|bao gồm|như sau|hoặc|và|có chứa|chứa|từ|\d+[.,]?\d*\s*%?)$",
    re.I,
)


def extract_ingredient_head(raw_term: str) -> str:
    """
    Trích xuất tên chính (head name) của một mục nguyên liệu:
      1. Chuẩn hóa NFC + chữ thường.
      2. Bỏ ký tự đầu dòng và cắt phần trước dấu ngoặc đơn/vuông đầu tiên '(' hoặc '['.
      3. Cắt bỏ định lượng/phần trăm ở cuối (vd: 'Đường 10%' -> 'đường', 'Sữa bột 20% (từ sữa bò)' -> 'sữa bột').
      4. Lọc bỏ các mảnh vụn vô nghĩa (K16).
    """
    t = norm_text(raw_term)
    if not t:
        return ""
    t = re.sub(r"^[\s\-–—•*+:.,;]+", "", t)
    t = _LEADING_QTY_RE.sub("", t)
    head = re.split(r"[\(\[]", t, maxsplit=1)[0].strip()
    # Lặp tối đa 2 lần để cắt sạch các cụm kiểu "calci carbonat 0,7%" hoặc "vitamin c 16 mg/100 ml 20% rni"
    for _ in range(2):
        head_new = _TRAILING_QTY_RE.sub("", head).strip()
        head_new = re.sub(r"[\s,:;.\-–—]+$", "", head_new).strip()
        if head_new == head:
            break
        head = head_new

    if not head or _FRAGMENT_RE.match(head):
        return ""
    return head

def split_top_level(s):
    out, d, cur = [], 0, ""
    for ch in s:
        d += (ch == "(") - (ch == ")")
        if ch == "," and d == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def expand_paren_leading(term):
    t = norm_text(term)
    m = re.match(r"^\(\s*(.*)\)\s*(?:\d+(?:[.,]\d+)?\s*%)?\s*$", t)
    if not m:
        return None
    ing, codes = [], []
    for it in split_top_level(m.group(1)):
        if parse_ins(it) and not re.search(r"[^\W\d_]{3,}", it):  # chỉ gồm mã
            codes += [v for _, v in parse_ins(it)]
        else:
            h = extract_ingredient_head(it)
            if h:
                ing.append(h)
    return {"ingredients": ing, "ins_codes": codes}

def make_stable_ingredient_id(head_name: str) -> str:
    """
    Tạo ID ổn định từ tên nguyên liệu (sửa lỗi K9: không đánh số ING_AUTO_001 theo thứ tự tần suất).
    Ví dụ: 'bột phô mai' -> 'ING_VI_BOT_PHO_MAI'
    """
    h = norm_text(head_name).replace("đ", "d")
    ascii_str = "".join(c for c in unicodedata.normalize("NFD", h) if unicodedata.category(c) != "Mn")
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_str).strip("_").upper()
    return f"ING_VI_{slug[:40]}" if slug else "ING_VI_UNKNOWN"


# ---------------------------------------------------------------------------
# BỘ QUY TẮC PHÂN LOẠI NHÓM CHẤT DINH DƯỠNG PHƯƠNG ÁN B (6 NHÓM DÙNG CHUNG)
# ---------------------------------------------------------------------------
NUTRITIONAL_PATTERNS = {
    "vitamin": [
        r"\bvitamin[s]?\b", r"\bvit\.?\s*(?:a|b\d{0,2}|c|d\d?|e|k\d?)\b",
        r"\bretinol\b", r"\bretinyl\b", r"\bbeta[\s\-]?caroten",
        r"\bthiamin", r"\briboflavin", r"\bniacin", r"\bnicotinamid",
        r"\bpyridoxin", r"\bfolic\b", r"\bfolat", r"\bpteroylmonoglutamic",
        r"\bcobalamin", r"\bcyanocobalamin", r"\bmethylcobalamin",
        r"\bbiotin\b", r"\bpantothenic", r"\bpantothenat",
        r"\bcholecalciferol", r"\bergocalciferol", r"\btocopherol", r"\btocopheryl",
        r"\bphylloquinon", r"\bphytomenadion", r"\bmenaquinon",
    ],
    "mineral_trace": [
        r"\bkhoáng\s+chất\b", r"\bkhoáng\s+tố\b", r"\bcác\s+khoáng\s+chất\b", r"\bhỗn\s+hợp\s+khoáng\b", r"\bminerals?\b",
        r"\bmuối\s+(?:ăn\s+|tinh\s+|tinh\s+chế\s+)?i[\s\-]?ốt\b", r"\bmuối\s+(?:ăn\s+|tinh\s+)?iod\b",
        r"\biodized\s+salt\b", r"\bkali\s+iodat\b", r"\bkali\s+iodid\b",
        r"\bcanxi\b", r"\bcalci\b", r"\bcalcium\b", r"\btricalci\b", r"\bdicalci\b",
        r"\bsắt\b", r"\biron\b", r"\bferric\b", r"\bferrous\b",
        r"\bkẽm\b", r"\bzinc\b",
        r"\bmagie\b", r"\bmagiê\b", r"\bmagnesi",
        r"\bselen", r"\bmangan", r"\bđồng\s+(?:sulfat|gluconat|citrat)\b", r"\bcopper\b", r"\bcrôm\b", r"\bchrom",
    ],
    "fiber_prebiotic": [
        r"\bchất\s+xơ\b", r"\bxơ\s+thực\s+phẩm\b", r"\bfiber\b", r"\bfibre\b",
        r"\binulin\b", r"\bfos\b", r"\bgos\b",
        r"\bfructo[\s\-]?oligosaccharid", r"\bgalacto[\s\-]?oligosaccharid", r"\boligofructose\b",
        r"\bisomalto[\s\-]?oligo", r"\bmạch\s+nha\s+imo\b", r"\bmạch\s+nha\s*\(\s*imo\s*\)",
        r"\bimo\b", r"\bpolydextrose\b", r"\bdextrin\s+kháng\b", r"\bresistant\s+(?:dextrin|starch)\b", r"\bbeta[\s\-]?glucan\b",
    ],
    "isolated_protein": [
        r"\bprotein\b", r"\bprôtêin\b", r"\bđạm\s+(?:thực\s+vật|đậu\s+hà\s+lan)\b",
        r"\b(?:chất\s+)?đạm\s+đậu\s+nành\b",
        r"\bđạm\s+sữa\b", r"\bđạm\s+whey\b", r"\bbột\s+whey\b", r"\bwhey\s+bột\b", r"\bwhey\s+powder\b",
        r"\bwhey\s+protein\b", r"\bsoy\s+protein\b", r"\bmilk\s+protein[s]?\b", r"\bcasein",
    ],
    "amino_omega_bioactive": [
        r"\bdha\b", r"\bepa\b", r"\bomega[\s\-]?[369]\b", r"\bdầu\s+cá\b", r"\bbột\s+dầu\s+cá\b", r"\bfish\s+oil\b",
        r"\btaurin", r"\blysin", r"\bcarnitin", r"\bcholin", r"\binositol\b",
        r"\blutein\b", r"\bnucleotid", r"\bcolostrum\b", r"\bsữa\s+non\b", r"\bcolosigg\b",
        r"\bcollagen\b", r"\bgaba\b", r"\bmct\b", r"\bhmo\b", r"\b2'-fl\b",
    ],
    "probiotic": [
        r"\blactobacillus\b", r"\bbifidobacterium\b", r"\bstreptococcus\s+thermophilus\b",
        r"\bmen\s+streptococcus\b", r"\bbacillus\s+coagulans\b", r"\blactococcus\s+lactis\b",
        r"\bprobiotic", r"\bpostbiotic", r"\blactic\s+acid\s+bacteria\b", r"\blợi\s+khuẩn\b", r"\bmen\s+vi\s+sinh\b",
    ],
}

COMPILED_NUTR = {
    cat: [re.compile(p, re.I) for p in pats]
    for cat, pats in NUTRITIONAL_PATTERNS.items()
}

_FLAVOR_HEAD_RE = re.compile(r"^(?:hương\s+liệu|chất\s+tạo\s+hương|hương|vani)\b")
_FLAVOR_RULES = [
    (re.compile(r"\bgiống\s+tự\s+nhiên\b"), "ADD_FLAVOR_NATURE_IDENTICAL"),
    (re.compile(r"\b(?:tổng\s+hợp|nhân\s+ tạo)\b"), "ADD_FLAVOR_SYNTHETIC"),
    (re.compile(r"\btự\s+nhiên\b"), "ADD_FLAVOR_NATURAL"),
]

def link_non_code_additive(term: str) -> str:
    """
    Gọi hàm này ở bước Entity Linking trước khi tra alias
    """
    
    t = norm_text(term).strip("()")
    t = re.sub(r"\s+dùng\s+cho\s+thực\s+phẩm$", "", t)
    if not _FLAVOR_HEAD_RE.match(t):
        return ""
    for rx, ent in _FLAVOR_RULES:
        if rx.search(t):
            return ent
    return "ADD_FLAVOR_GENERIC"

# Sửa P6, P7, P8 + suppress từ điển của Claude:
# - Loại trừ MỌI loại đạm/protein thủy phân (dùng làm chất điều vị/gia vị: "đạm đậu nành thủy phân", "protein thực vật thủy phân")
# - Loại trừ vỏ bọc/ruột collagen xúc xích
# - Loại trừ các muối canxi/magie/sắt thực chất là phụ gia bảo quản/chống đông vón/phẩm màu
# - Loại trừ nước khoáng, độ đạm nước mắm, nguyên liệu nền chỉ ghi "sữa giàu canxi"
NEGATIVE_NUTR_HEAD_RE = re.compile(
    r"\bcá\s+đồng\b|\bđồng\s+nhất\b|\bđồng\s+quê\b|\bsắt\s+lát\b|"
    r"\bvỏ\s+bọc\b|\bruột\s+collagen\b|"
    r"\b(?:protein|đạm)\b[^,;()]*\bthủy\s+phân\b|"
    r"\bhydroly[sz]ed\b[^,;()]*\bprotein\b|\bprotein\s+hydrolys[ae]te?\b|"
    r"\bgia\s+vị\b|\bhỗn\s+hợp\s+protein\s+sấy\s+vị\b|\bgiả\s+thịt\b|"
    r"\bđộ\s+đạm\b|\d+\s*°\s*n\b|\bnước\s+khoáng\b|\bnước\s+suối\b|"
    r"\b(?:can?xi|calci|calcium)\s+(?:propionat|sorbat|benzoat|acetat|stearoyl|disodium|edta|silicat|sulfit|alginat)\b|"
    r"\b(?:magie|magnesi|magnesium)\s+(?:stearat|silicat)\b|"
    r"\b(?:oxit|oxide)\s+sắt\b|\biron\s+oxide|\bsắt\s+\(?iii\)?\s*oxit\b|"
    r"^(?:sữa|nước\s+uống|bột\s+ngũ\s+cốc|bánh)(?:\s+[^\s,;()]+){0,3}?\s+(?:giàu|bổ\s+sung|có\s+thêm)\b",
    re.I,
)

GENERIC_SUPPLEMENT_HEADS = {"chất bổ sung", "vi chất dinh dưỡng", "hỗn hợp dưỡng chất", "bột tăng cường dinh dưỡng"}


def classify_nutritional_item(raw_item: str, kb_alias_map: dict = None) -> dict:
    """
    Hàm phân loại 1 mục nguyên liệu theo Phương án B (6 nhóm) dùng chung cho cả Gold và KB.
    Trả về:
      {
        "name": head_name,
        "raw": raw_item,
        "kb_id": entity_id (nếu truyền kb_alias_map và khớp được, sửa X2),
        "nutritional": bool,
        "nutritional_category": str | None
      }
    """
    t_norm = norm_text(raw_item)
    head = extract_ingredient_head(t_norm)
    kb_id = kb_alias_map.get(head) if (kb_alias_map and head) else None

    if not head or NEGATIVE_NUTR_HEAD_RE.search(head) or NEGATIVE_NUTR_HEAD_RE.search(t_norm):
        return {
            "name": head or t_norm,
            "raw": raw_item,
            "kb_id": kb_id,
            "nutritional": False,
            "nutritional_category": None,
        }

    target = t_norm if (head in GENERIC_SUPPLEMENT_HEADS or head == "mạch nha") else head

    for cat, regexes in COMPILED_NUTR.items():
        if any(r.search(target) for r in regexes):
            return {
                "name": head,
                "raw": raw_item,
                "kb_id": kb_id,
                "nutritional": True,
                "nutritional_category": cat,
            }

    return {
        "name": head,
        "raw": raw_item,
        "kb_id": kb_id,
        "nutritional": False,
        "nutritional_category": None,
    }