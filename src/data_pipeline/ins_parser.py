"""
ins_parser.py  -  MỘT hàm trích mã INS/E dùng chung cho: gold, bảng ADI, OCR benchmark, và đầu ra của pipeline.
(Gold và dự đoán PHẢI dùng cùng hàm này thì so sánh mới công bằng.)

Quy ước:
  base    = số + hậu tố chữ a-f nếu có      vd '330', '150d', '160a'
  variant = base + số La Mã nếu có          vd '500(ii)', '322(i)'
Nhận dạng: 330 | (330) | E330 | e500ii | INS 322i | 500(ii) | 160a(i) | 450iii
Loại trừ : số kèm đơn vị (100g, 250 ml, 1000 mg, 105 g/l), số thập phân/phần trăm (34,242%), số ngoài 100-1599
"""
import re

PARSER_VERSION = "1.0"

_PREFIX = re.compile(r"\b(?:ins|e)\s*-?\s*(?=\d{3,4})", re.I)       # bỏ tiền tố 'E', 'INS'
_ROMAN = r"(?:iv|vi{0,3}|ix|i{1,3}|v|x)"
_NOT_LETTER = r"(?![^\W\d_])"                                         # sau đó không phải chữ cái (kể cả có dấu)
_CODE = re.compile(
    r"(?<![\w,.])(\d{3,4})"                                           # số 3-4 chữ số, không dính chữ/số/dấu phẩy-chấm phía trước
    r"(?:([a-f])" + _NOT_LETTER + r")?"                               # hậu tố chữ a-f (150d, 160a)
    r"(?:\(\s*(" + _ROMAN + r")\s*\)|(" + _ROMAN + r")" + _NOT_LETTER + r")?"   # (ii) hoặc ii dính liền
    r"(?![\d])" + _NOT_LETTER +
    r"(?!\s*(?:g|mg|µg|mcg|kg|ml|l|kcal|kj|iu|%)(?![^\W\d_]))",      # không phải đơn vị
    re.I,
)


def parse_ins(text):
    """Trả về list (base, variant), có thể trùng; dùng set() nếu cần."""
    text = _PREFIX.sub(" ", text or "")
    out = []
    for m in _CODE.finditer(text):
        num, letter, roman_p, roman_a = m.group(1), (m.group(2) or "").lower(), m.group(3), m.group(4)
        if not (100 <= int(num) <= 1599):
            continue
        roman = (roman_p or roman_a or "").lower()
        base = num + letter
        out.append((base, base + (f"({roman})" if roman else "")))
    return out


def ins_bases(text):
    return {b for b, _ in parse_ins(text)}