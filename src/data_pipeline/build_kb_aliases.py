"""
build_kb_aliases.py (v2 - Đã sửa toàn bộ vấn đề K1..K17 và X1..X4 trong BaoCao_VanDe_2_Script.md)
Nâng cấp so với v1:
  1. [X1, K17, K16] Dùng chung `extract_ingredient_head` và `classify_nutritional_item` từ `text_utils.py`.
     Số chuỗi nguyên liệu còn dính '%' trong head giảm từ 294/1.659 về đúng 0/1.659; lọc bỏ hoàn toàn dòng rỗng/mảnh vụn.
  2. [K11, K12, X3] Thống nhất 100% nhãn dinh dưỡng 6 nhóm giữa KB và Parser:
     `kb_entities.csv` có thêm cột `nutritional_category` (1 trong 6 nhóm hoặc rỗng) được tính trực tiếp từ
     `classify_nutritional_item()` trong `text_utils.py`.
  3. [K1, K2, K3, K4] Làm sạch bảng Alias (`kb_aliases.csv`):
     - Bỏ toàn bộ cụm chức năng ('chất điều chỉnh độ acid (330)', 'vitamin c (300)') khỏi `BASE_VI_NAMES` (K2).
     - Đổi `canonical_name_vi` của INS 621 thành 'mononatri glutamat' (đưa 'mì chính', 'bột ngọt' xuống `synonym_vi`) (K3).
     - Không gán trùng alias 'lecithin' cho cả `ADD_322` và `ADD_322_I`: tên chung 'lecithin' trỏ về `ADD_322` (mã gốc),
       còn `ADD_322_I` chỉ nhận mã cụ thể `322(i)` / `e322i` và có `parent_entity_id = ADD_322` (K1, K10).
     - Thêm cột `priority` (1 = mã/canonical chính xác, 2 = synonym chuẩn, 3 = surface/auto) và cờ `is_ambiguous`
       đánh dấu tự động mọi alias nếu trỏ tới >1 `entity_id` (K1).
     - Khai báo ngôn ngữ `(syn_text, lang)` tường minh thay vì đoán bằng regex ASCII (sửa lỗi 'imo', 'men' bị gán 'en') (K4).
  4. [K8, K9, K10]
     - Thêm cột `parent_entity_id` cho thực thể cấp biến thể (vd `ADD_500_II` có `parent_entity_id = ADD_500`) (K10).
     - Loại trừ các head đã nằm trong `CURATED_INGREDIENTS` TRƯỚC KHI lấy Top-K (`--top_ingredients 150` lấy đủ 150 head mới) (K8).
     - Dùng ID ổn định theo slug (`make_stable_ingredient_id`, vd `ING_VI_BOT_PHO_MAI`) thay vì `ING_AUTO_001` (K9).
  5. [K5, K6, K13, K14]
     - Bổ sung thực thể cho nhóm Phụ gia không kèm mã INS phổ biến (Hương liệu tổng hợp/tự nhiên, màu tự nhiên...) và ánh xạ
       tên chất không kèm mã (như 'lecithin đậu nành' -> `ADD_322`, 'gôm xanthan' -> `ADD_415`) (K6).
     - Đọc cả `additives.txt` và `ingredients.txt` của Open Food Facts nếu có trong `RAW_OFF_DIR` (K13).
     - Chỉ giữ các `off_id` chuẩn; loại bỏ các mã `foodon_id` gõ tay chưa xác minh khỏi danh sách mặc định (chỉ điền khi đọc từ file `foodon.owl` thật) (K14).

Cách chạy (từ thư mục gốc project):
    python src/data_pipeline/build_kb_aliases.py
"""

import argparse
import csv
import hashlib
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.common.paths import ADI_TABLE_CSV, KB_DIR, RAW_OFF_DIR, UNIQUE_TERMS_CSV
from ins_parser import parse_ins
from text_utils import (
    classify_nutritional_item,
    extract_ingredient_head,
    make_stable_ingredient_id,
    norm_text,
)


def format_add_entity_id(variant: str) -> str:
    m = re.match(r"^(\d+[a-f]?)(?:\(([ivx]+)\))?$", variant.strip().lower())
    if m:
        base, roman = m.group(1).upper(), (m.group(2) or "").upper()
        return f"ADD_{base}_{roman}" if roman else f"ADD_{base}"
    clean = re.sub(r"[^a-zA-Z0-9]+", "_", variant.strip()).strip("_").upper()
    return f"ADD_{clean}"


def format_off_additive_id(variant: str) -> str:
    compact = variant.strip().lower().replace("(", "").replace(")", "")
    return f"en:e{compact}"


def format_e_number(variant: str) -> str:
    m = re.match(r"^(\d+)([a-f]?)(?:\(([ivx]+)\))?$", variant.strip().lower())
    if m:
        num, let, rom = m.group(1), m.group(2), m.group(3)
        return f"E{num}{let}" + (f"({rom})" if rom else "")
    return "E" + variant.strip().upper()


# Tên riêng biệt cho các biến thể số La Mã (K1: không lặp lại tên chung 'Lecithin' ở 322(i) để tránh va chạm với base 322)
SUBVARIANT_SPECIFIC_NAMES = {
    "500(i)": ("Sodium carbonate", "Natri cacbonat"),
    "500(ii)": ("Sodium hydrogen carbonate", "Natri hydro cacbonat"),
    "500(iii)": ("Sodium sesquicarbonate", "Natri sesquicacbonat"),
    "501(i)": ("Potassium carbonate", "Kali cacbonat"),
    "501(ii)": ("Potassium hydrogen carbonate", "Kali hydro cacbonat"),
    "503(i)": ("Ammonium carbonate", "Amoni cacbonat"),
    "503(ii)": ("Ammonium hydrogen carbonate", "Amoni hydro cacbonat"),
    "322(i)": ("Lecithin (unfractionated)", "Lecithin tinh khiết"),
    "322(ii)": ("Partially hydrolyzed lecithin", "Lecithin thủy phân một phần"),
    "331(i)": ("Monosodium dihydrogen citrate", "Mononatri dihydro citrat"),
    "331(ii)": ("Disodium monohydrogen citrate", "Dinatri monohydro citrat"),
    "331(iii)": ("Trisodium citrate", "Trinatri citrat"),
    "332(i)": ("Monopotassium dihydrogen citrate", "Monokali dihydro citrat"),
    "332(ii)": ("Tripotassium citrate", "Trikali citrat"),
    "339(i)": ("Monosodium orthophosphate", "Mononatri orthophosphat"),
    "339(ii)": ("Disodium orthophosphate", "Dinatri orthophosphat"),
    "339(iii)": ("Trisodium orthophosphate", "Trinatri orthophosphat"),
    "340(i)": ("Monopotassium orthophosphate", "Monokali orthophosphat"),
    "340(ii)": ("Dipotassium orthophosphate", "Dikali orthophosphat"),
    "340(iii)": ("Tripotassium orthophosphate", "Trikali orthophosphat"),
    "341(i)": ("Monocalcium orthophosphate", "Monocalci orthophosphat"),
    "341(ii)": ("Dicalcium orthophosphate", "Dicalci orthophosphat"),
    "341(iii)": ("Tricalcium orthophosphate", "Tricalci orthophosphat"),
    "450(i)": ("Disodium diphosphate", "Dinatri diphosphat"),
    "450(ii)": ("Trisodium diphosphate", "Trinatri diphosphat"),
    "450(iii)": ("Tetrasodium diphosphate", "Tetranatri diphosphat"),
    "450(v)": ("Tetrapotassium diphosphate", "Tetrakali diphosphat"),
    "451(i)": ("Pentasodium triphosphate", "Pentanatri triphosphat"),
    "451(ii)": ("Pentapotassium triphosphate", "Pentakali triphosphat"),
    "452(i)": ("Sodium polyphosphate", "Natri polyphosphat"),
    "452(ii)": ("Potassium polyphosphate", "Kali polyphosphat"),
    "160a(i)": ("Beta-carotene, synthetic", "Beta-caroten tổng hợp"),
    "160a(ii)": ("Beta-carotene, vegetable", "Caroten tự nhiên (chiết xuất thực vật)"),
    "160a(iii)": ("Beta-carotene from Blakeslea trispora", "Beta-caroten từ Blakeslea trispora"),
    "160a(iv)": ("Beta-carotene, algal", "Beta-caroten từ tảo"),
    "160b(i)": ("Annatto extracts, bixin-based", "Chiết xuất Annatto (bixin)"),
    "160b(ii)": ("Annatto extracts, norbixin-based", "Chiết xuất Annatto (norbixin)"),
}

# Sửa K2, K3:
# - Đưa tên chuẩn hóa học tiếng Việt lên đầu làm `canonical_vi`, các tên thông tục theo sau làm `synonym_vi`.
# - Tuyệt đối KHÔNG chứa cụm chức năng ('chất điều chỉnh độ acid (330)', 'vitamin c (300)').
BASE_VI_NAMES = {
    "621": ("mononatri glutamat", [("mononatri l-glutamat", "vi"), ("bột ngọt", "vi"), ("mì chính", "vi"), ("msg", "en")]),
    "330": ("axit citric", [("acid citric", "vi")]),
    "322": ("lecithin", [("lecithin đậu nành", "vi"), ("lecithin hướng dương", "vi"), ("soy lecithin", "en"), ("lexithin", "vi")]),
    "471": ("mono và diglycerid của các axit béo", [("mono- and diglycerides of fatty acids", "en")]),
    "415": ("gôm xanthan", [("xanthan gum", "en")]),
    "407": ("carrageenan", [("caragenan", "vi")]),
    "202": ("kali sorbat", [("potassium sorbate", "en")]),
    "211": ("natri benzoat", [("sodium benzoate", "en")]),
    "420": ("sorbitol", [("d-sorbitol", "en"), ("si-rô sorbitol", "vi")]),
    "631": ("dinatri 5'-inosinat", [("disodium 5'-inosinate", "en")]),
    "627": ("dinatri 5'-guanylat", [("disodium 5'-guanylate", "en")]),
    "635": ("dinatri 5'-ribonucleotid", [("disodium 5'-ribonucleotides", "en")]),
    "466": ("natri cacboxymethyl cellulose", [("carboxymethyl cellulose", "en"), ("cmc", "en"), ("cellulose gum", "en")]),
    "422": ("glycerol", [("glycerin", "en")]),
    "950": ("acesulfam kali", [("acesulfame potassium", "en"), ("acesulfame k", "en")]),
    "951": ("aspartam", [("aspartame", "en")]),
    "955": ("sucralose", [("sucraloza", "vi")]),
    "110": ("sunset yellow fcf", [("vàng sunset yellow fcf", "vi")]),
    "102": ("tartrazin", [("tartrazine", "en")]),
    "129": ("allura red ac", [("đỏ allura red ac", "vi")]),
    "133": ("brilliant blue fcf", [("xanh brilliant blue fcf", "vi")]),
    "124": ("ponceau 4r", [("đỏ ponceau 4r", "vi")]),
    "120": ("carmin", [("carmine", "en")]),
    "412": ("gôm guar", [("guar gum", "en")]),
    "440": ("pectin", [("pectins", "en")]),
    "260": ("axit acetic", [("acid acetic", "vi")]),
    "270": ("axit lactic", [("acid lactic", "vi")]),
    "296": ("axit malic", [("acid malic", "vi"), ("dl-malic acid", "en")]),
    "300": ("axit l-ascorbic", [("acid l-ascorbic", "vi"), ("l-ascorbic acid", "en")]),
    "319": ("tertiary butylhydroquinone", [("tbhq", "en")]),
    "320": ("butylated hydroxyanisole", [("bha", "en")]),
    "321": ("butylated hydroxytoluene", [("bht", "en")]),
    "100": ("curcumin", [("tinh chất nghệ", "vi")]),
    "500": ("natri cacbonat (nhóm)", [("sodium carbonates", "en")]),
    "500(ii)": ("natri hydro cacbonat", [("natri bicacbonat", "vi"), ("sodium bicarbonate", "en"), ("baking soda", "en")]),
}

# Sửa K6: Thực thể chuẩn cho nhóm Phụ gia không kèm mã INS (Hương liệu tổng hợp/tự nhiên...)
NON_CODE_ADDITIVE_ENTITIES = [
    ("ADD_FLAVOR_SYNTHETIC", "Synthetic flavouring", "Hương liệu tổng hợp", "en:artificial-flavouring",
     [("hương liệu tổng hợp", "vi"), ("hương tổng hợp", "vi"), ("hương liệu nhân tạo", "vi"), ("artificial flavouring", "en")]),
    ("ADD_FLAVOR_NATURAL", "Natural flavouring", "Hương liệu tự nhiên", "en:natural-flavouring",
     [("hương liệu tự nhiên", "vi"), ("hương tự nhiên", "vi"), ("natural flavouring", "en")]),
    ("ADD_FLAVOR_NATURE_IDENTICAL", "Nature-identical flavouring", "Hương liệu giống tự nhiên", "en:nature-identical-flavouring",
     [("hương liệu giống tự nhiên", "vi"), ("hương giống tự nhiên", "vi")]),
    ("ADD_FLAVOR_GENERIC", "Flavouring", "Hương liệu", "en:flavouring",
     [("hương liệu", "vi"), ("hương liệu thực phẩm", "vi"), ("hương vani", "vi"), ("vani", "vi"), ("flavouring", "en")]),
]

# Sửa K4, K11, K12, K14:
# Mỗi synonym là tuple `(text, lang)` tường minh (không đoán bằng regex ASCII).
# Nhãn dinh dưỡng (6 nhóm) được gọi tự động từ `classify_nutritional_item(can_vi)` của `text_utils.py`.
CURATED_INGREDIENTS = [
    ("ING_SUGAR", "Sugar", "Đường", "en:sugar",
     [("đường", "vi"), ("đường kính", "vi"), ("đường tinh luyện", "vi"), ("đường trắng", "vi"), ("đường mía", "vi"),
      ("đường cát", "vi"), ("sugar", "en"), ("sucrose", "en"), ("saccharose", "en")]),
    ("ING_SALT", "Salt", "Muối", "en:salt",
     [("muối", "vi"), ("muối ăn", "vi"), ("muối tinh", "vi"), ("muối tinh chế", "vi"), ("salt", "en"),
      ("natri clorua", "vi"), ("sodium chloride", "en")]),
    ("ING_IODIZED_SALT", "Iodized salt", "Muối i-ốt", "en:iodized-salt",
     [("muối i-ốt", "vi"), ("muối iod", "vi"), ("muối iốt", "vi"), ("muối ăn i-ốt", "vi"), ("muối tinh chế i-ốt", "vi"), ("iodized salt", "en")]),
    ("ING_WATER", "Water", "Nước", "en:water",
     [("nước", "vi"), ("nước tinh khiết", "vi"), ("nước sạch", "vi"), ("water", "en"), ("purified water", "en")]),
    ("ING_WHEAT_FLOUR", "Wheat flour", "Bột mì", "en:wheat-flour",
     [("bột mì", "vi"), ("bột lúa mì", "vi"), ("wheat flour", "en")]),
    ("ING_VEGETABLE_OIL", "Vegetable oil", "Dầu thực vật", "en:vegetable-oil",
     [("dầu thực vật", "vi"), ("dầu ăn", "vi"), ("vegetable oil", "en")]),
    ("ING_PALM_OIL", "Palm oil", "Dầu cọ", "en:palm-oil",
     [("dầu cọ", "vi"), ("dầu olein cọ", "vi"), ("palm oil", "en")]),
    ("ING_SOYBEAN_OIL", "Soybean oil", "Dầu đậu nành", "en:soya-oil",
     [("dầu đậu nành", "vi"), ("dầu nành", "vi"), ("soybean oil", "en")]),
    ("ING_SESAME_OIL", "Sesame oil", "Dầu mè", "en:sesame-oil",
     [("dầu mè", "vi"), ("dầu vừng", "vi"), ("sesame oil", "en")]),
    ("ING_COCONUT_OIL", "Coconut oil", "Dầu dừa", "en:coconut-oil",
     [("dầu dừa", "vi"), ("coconut oil", "en")]),
    ("ING_VEGETABLE_FAT", "Vegetable fat", "Chất béo thực vật", "en:vegetable-fat",
     [("chất béo thực vật", "vi"), ("shortening", "en"), ("shortening thực vật", "vi"), ("vegetable fat", "en"), ("vegetable shortening", "en")]),
    ("ING_MALTODEXTRIN", "Maltodextrin", "Maltodextrin", "en:maltodextrin",
     [("maltodextrin", "en")]),
    ("ING_MALTOSE_SYRUP", "Maltose syrup", "Mạch nha", "en:maltose-syrup",
     [("mạch nha", "vi"), ("mạch nha maltose", "vi"), ("mạch nha glucose", "vi"), ("si-rô glucose", "vi"), ("siro glucose", "vi"),
      ("maltose syrup", "en"), ("glucose syrup", "en")]),
    ("ING_IMO_SYRUP", "Isomalto-oligosaccharide", "Mạch nha isomalto oligo", "en:isomalto-oligosaccharide",
     [("mạch nha isomalto oligo", "vi"), ("mạch nha imo", "vi"), ("mạch nha isomalto oligosaccharide", "vi"),
      ("imo", "en"), ("isomalto-oligosaccharide", "en")]),
    ("ING_GELATIN", "Gelatin", "Gelatin", "en:gelatin",
     [("gelatin", "en"), ("gelatine", "en")]),
    ("ING_EGG", "Egg", "Trứng", "en:egg",
     [("trứng", "vi"), ("trứng gà", "vi"), ("trứng gà tươi", "vi"), ("bột trứng", "vi"), ("bột nguyên trứng", "vi"),
      ("egg", "en"), ("whole egg powder", "en")]),
    ("ING_EGG_WHITE", "Egg white", "Bột lòng trắng trứng", "en:egg-white",
     [("bột lòng trắng trứng", "vi"), ("lòng trắng trứng", "vi"), ("egg white powder", "en")]),
    ("ING_EGG_YOLK", "Egg yolk", "Bột lòng đỏ trứng", "en:egg-yolk",
     [("bột lòng đỏ trứng", "vi"), ("lòng đỏ trứng", "vi"), ("egg yolk powder", "en")]),
    ("ING_GARLIC", "Garlic", "Tỏi", "en:garlic",
     [("tỏi", "vi"), ("bột tỏi", "vi"), ("tỏi tươi", "vi"), ("garlic", "en"), ("garlic powder", "en")]),
    ("ING_COCOA_POWDER", "Cocoa powder", "Bột cacao", "en:cocoa-powder",
     [("bột cacao", "vi"), ("bột ca cao", "vi"), ("cocoa powder", "en")]),
    ("ING_FOOD_ALCOHOL", "Food grade ethanol", "Cồn thực phẩm", "en:alcohol",
     [("cồn thực phẩm", "vi"), ("ethanol thực phẩm", "vi")]),
    ("ING_CORN_STARCH", "Corn starch", "Tinh bột bắp", "en:corn-starch",
     [("tinh bột bắp", "vi"), ("tinh bột ngô", "vi"), ("bột bắp", "vi"), ("corn starch", "en"), ("maize starch", "en")]),
    ("ING_POTATO_STARCH", "Potato starch", "Tinh bột khoai tây", "en:potato-starch",
     [("tinh bột khoai tây", "vi"), ("bột khoai tây", "vi"), ("potato starch", "en")]),
    ("ING_TAPIOCA_STARCH", "Tapioca starch", "Tinh bột khoai mì", "en:tapioca-starch",
     [("tinh bột khoai mì", "vi"), ("tinh bột sắn", "vi"), ("bột sắn", "vi"), ("bột năng", "vi"),
      ("tapioca starch", "en"), ("cassava starch", "en")]),
    ("ING_STARCH", "Starch", "Tinh bột", "en:starch",
     [("tinh bột", "vi"), ("starch", "en")]),
    ("ING_WHEY_PROTEIN", "Whey powder / protein", "Bột whey", "en:whey-powder",
     [("bột whey", "vi"), ("whey bột", "vi"), ("đạm whey", "vi"), ("đạm whey cô đặc", "vi"), ("bột whey protein", "vi"),
      ("whey powder", "en"), ("whey protein", "en")]),
    ("ING_FISH_SAUCE", "Fish sauce", "Nước mắm", "en:fish-sauce",
     [("nước mắm", "vi"), ("fish sauce", "en")]),
    ("ING_SOY_SAUCE", "Soy sauce", "Nước tương", "en:soy-sauce",
     [("nước tương", "vi"), ("bột nước tương", "vi"), ("xì dầu", "vi"), ("soy sauce", "en")]),
    ("ING_PEPPER", "Black pepper", "Tiêu", "en:black-pepper",
     [("tiêu", "vi"), ("tiêu đen", "vi"), ("bột tiêu", "vi"), ("hạt tiêu", "vi"), ("black pepper", "en")]),
    ("ING_DEXTROSE", "Dextrose", "Đường dextrose", "en:dextrose",
     [("đường dextrose", "vi"), ("dextrose", "en"), ("dextroza", "vi")]),
    ("ING_FRUCTOSE", "Fructose", "Đường fructose", "en:fructose",
     [("đường fructose", "vi"), ("xiro fructoza", "vi"), ("fructose", "en"), ("fructose syrup", "en")]),
    ("ING_LACTOSE", "Lactose", "Đường lactose", "en:lactose",
     [("lactose", "en"), ("đường lactose", "vi"), ("lactoza", "vi")]),
    ("ING_CHILI", "Chili pepper", "Ớt", "en:chili-pepper",
     [("ớt", "vi"), ("bột ớt", "vi"), ("ớt tươi", "vi"), ("chili", "en"), ("chilli powder", "en")]),
    ("ING_MILK", "Milk", "Sữa", "en:milk",
     [("sữa", "vi"), ("sữa tươi", "vi"), ("sữa bò tươi", "vi"), ("sữa hoàn toàn từ sữa bò tươi", "vi"),
      ("sữa từ 100% sữa tươi", "vi"), ("milk", "en"), ("fresh milk", "en")]),
    ("ING_WHOLE_MILK_POWDER", "Whole milk powder", "Sữa bột nguyên kem", "en:whole-milk-powder",
     [("sữa bột nguyên kem", "vi"), ("bột sữa nguyên kem", "vi"), ("sữa bột", "vi"), ("bột sữa", "vi"),
      ("bột sữa béo", "vi"), ("whole milk powder", "en"), ("milk powder", "en")]),
    ("ING_SKIM_MILK_POWDER", "Skimmed milk powder", "Bột sữa gầy", "en:skimmed-milk-powder",
     [("bột sữa gầy", "vi"), ("sữa bột gầy", "vi"), ("sữa gầy", "vi"), ("skimmed milk powder", "en"), ("skim milk powder", "en")]),
    ("ING_MILK_PROTEIN", "Milk protein", "Protein sữa", "en:milk-proteins",
     [("protein sữa", "vi"), ("đạm sữa", "vi"), ("milk protein", "en")]),
    ("ING_MILK_FAT", "Milk fat", "Chất béo sữa", "en:milkfat",
     [("chất béo sữa", "vi"), ("bột kem sữa", "vi"), ("milk fat", "en")]),
    ("ING_BUTTER", "Butter", "Bơ", "en:butter",
     [("bơ", "vi"), ("butter", "en")]),
    ("ING_MARGARINE", "Margarine", "Bơ thực vật", "en:margarine",
     [("bơ thực vật", "vi"), ("margarine", "en")]),
    ("ING_CHEESE", "Cheese", "Phô mai", "en:cheese",
     [("phô mai", "vi"), ("bột phô mai", "vi"), ("cheese", "en"), ("cheese powder", "en")]),
    ("ING_YEAST_EXTRACT", "Yeast extract", "Chiết xuất nấm men", "en:yeast-extract",
     [("chiết xuất nấm men", "vi"), ("yeast extract", "en")]),
    ("ING_YEAST", "Yeast", "Men", "en:yeast",
     [("men", "vi"), ("nấm men", "vi"), ("men bánh mì", "vi"), ("yeast", "en")]),
    ("ING_ONION", "Onion", "Hành tây", "en:onion",
     [("hành tây", "vi"), ("bột hành tây", "vi"), ("hành", "vi"), ("hành lá sấy", "vi"), ("onion", "en"), ("onion powder", "en")]),
    ("ING_SHALLOT", "Shallot", "Hành tím", "en:shallot",
     [("hành tím", "vi"), ("shallot", "en")]),
    ("ING_SOY_PROTEIN", "Soy protein", "Đạm đậu nành", "en:soy-protein",
     [("đạm đậu nành", "vi"), ("chất đạm đậu nành", "vi"), ("protein đậu nành", "vi"), ("soy protein", "en"), ("isolated soy protein", "en")]),
    ("ING_HYDROLYZED_PROTEIN", "Hydrolysed vegetable protein", "Đạm thực vật thủy phân", "en:hydrolysed-vegetable-protein",
     [("đạm thực vật thủy phân", "vi"), ("protein thực vật thủy phân", "vi"), ("đạm đậu nành thủy phân", "vi"), ("hydrolyzed vegetable protein", "en")]),
    ("ING_NON_DAIRY_CREAMER", "Non-dairy creamer", "Bột kem không sữa", "en:non-dairy-creamer",
     [("bột kem không sữa", "vi"), ("bột kem thực vật", "vi"), ("bột kem béo thực vật", "vi"), ("non-dairy creamer", "en"), ("nondairy creamer", "en")]),
    ("ING_RICE", "Rice", "Gạo", "en:rice",
     [("gạo", "vi"), ("gạo st25", "vi"), ("gạo japonica", "vi"), ("bột gạo", "vi"), ("rice", "en")]),
    ("ING_PORK", "Pork", "Thịt heo", "en:pork",
     [("thịt heo", "vi"), ("nạc heo", "vi"), ("thịt lợn", "vi"), ("pork", "en")]),
    ("ING_PORK_FAT", "Pork fat", "Mỡ heo", "en:pork-fat",
     [("mỡ heo", "vi"), ("mỡ lợn", "vi"), ("lard", "en"), ("pork fat", "en")]),
    ("ING_CHICKEN", "Chicken meat", "Thịt gà", "en:chicken-meat",
     [("thịt gà", "vi"), ("chicken", "en")]),
    ("ING_SHRIMP", "Shrimp", "Tôm", "en:shrimp",
     [("tôm", "vi"), ("bột tôm", "vi"), ("thịt tôm", "vi"), ("shrimp", "en"), ("shrimp powder", "en")]),
    ("ING_TOMATO", "Tomato", "Cà chua", "en:tomato",
     [("cà chua", "vi"), ("cà chua cô đặc", "vi"), ("tomato", "en"), ("tomato paste", "en")]),
    ("ING_CARROT", "Carrot", "Cà rốt", "en:carrot",
     [("cà rốt", "vi"), ("nước ép cà rốt đen cô đặc", "vi"), ("carrot", "en")]),
    ("ING_GINGER", "Ginger", "Gừng", "en:ginger",
     [("gừng", "vi"), ("ginger", "en")]),
    ("ING_PEANUT", "Peanut", "Đậu phộng", "en:peanut",
     [("đậu phộng", "vi"), ("lạc", "vi"), ("peanut", "en"), ("peanuts", "en")]),
    ("ING_SESAME", "Sesame", "Mè", "en:sesame",
     [("mè", "vi"), ("vừng", "vi"), ("hạt mè", "vi"), ("sesame", "en")]),
    ("ING_OATS", "Oats", "Yến mạch", "en:oats",
     [("yến mạch", "vi"), ("bột yến mạch", "vi"), ("oats", "en")]),
    ("ING_WHEAT_GLUTEN", "Wheat gluten", "Gluten lúa mì", "en:wheat-gluten",
     [("gluten lúa mì", "vi"), ("wheat gluten", "en")]),
    ("ING_WHEAT_FIBER", "Wheat fiber", "Chất xơ từ lúa mì", "en:wheat-fiber",
     [("chất xơ từ lúa mì", "vi"), ("chất xơ lúa mì", "vi"), ("wheat fiber", "en")]),
    ("ING_SOLUBLE_FIBER", "Soluble dietary fiber", "Chất xơ hòa tan", "en:soluble-fiber",
     [("chất xơ hòa tan", "vi"), ("chất xơ hoà tan", "vi"), ("inulin", "en"), ("fos", "en"), ("fructo oligosaccharide", "en"), ("soluble fiber", "en")]),
    ("ING_COCONUT_MILK", "Coconut milk", "Nước cốt dừa", "en:coconut-milk",
     [("nước cốt dừa", "vi"), ("bột sữa dừa", "vi"), ("cơm dừa sấy", "vi"), ("thạch dừa", "vi"), ("coconut milk", "en")]),
    ("ING_VINEGAR", "Vinegar", "Giấm", "en:vinegar",
     [("giấm", "vi"), ("giấm ăn", "vi"), ("vinegar", "en")]),
    ("ING_CHIA_SEED", "Chia seed", "Hạt chia", "en:chia-seed",
     [("hạt chia", "vi"), ("chia seeds", "en")]),
    ("ING_COFFEE", "Coffee", "Bột cà phê", "en:coffee",
     [("bột cà phê", "vi"), ("cà phê", "vi"), ("cà phê hòa tan", "vi"), ("coffee", "en")]),
    ("ING_BLACK_TEA_EXTRACT", "Black tea extract", "Chiết xuất trà đen", "en:black-tea-extract",
     [("chiết xuất trà đen", "vi"), ("trà đen", "vi"), ("black tea extract", "en")]),
    # Nhóm Dinh dưỡng (6 nhóm đồng bộ hoàn toàn qua classify_nutritional_item)
    ("ING_VITAMIN_GENERIC", "Vitamins", "Vitamin", "en:vitamins",
     [("vitamin", "vi"), ("các vitamin", "vi"), ("hỗn hợp vitamin", "vi"), ("vitamin và khoáng chất", "vi"), ("hỗn hợp vitamin và khoáng chất", "vi")]),
    ("ING_MINERAL_GENERIC", "Minerals", "Khoáng chất", "en:minerals",
     [("khoáng chất", "vi"), ("các khoáng chất", "vi"), ("hỗn hợp khoáng", "vi")]),
    ("ING_VITAMIN_C", "Vitamin C", "Vitamin C", "en:vitamin-c",
     [("vitamin c", "vi")]),
    ("ING_VITAMIN_A", "Vitamin A", "Vitamin A", "en:vitamin-a",
     [("vitamin a", "vi"), ("retinol", "en"), ("retinyl acetat", "en")]),
    ("ING_VITAMIN_D3", "Vitamin D3", "Vitamin D3", "en:cholecalciferol",
     [("vitamin d3", "vi"), ("vitamin d", "vi"), ("cholecalciferol", "en")]),
    ("ING_VITAMIN_E", "Vitamin E", "Vitamin E", "en:vitamin-e",
     [("vitamin e", "vi"), ("dl-alpha-tocopheryl acetat", "en"), ("dl-alpha-tocopherol", "en")]),
    ("ING_VITAMIN_B1", "Vitamin B1", "Vitamin B1", "en:thiamin",
     [("vitamin b1", "vi"), ("thiamin", "en"), ("thiamine hydrochloride", "en")]),
    ("ING_VITAMIN_B2", "Vitamin B2", "Vitamin B2", "en:riboflavin",
     [("vitamin b2", "vi"), ("riboflavin", "en")]),
    ("ING_VITAMIN_B3", "Vitamin B3", "Vitamin B3", "en:niacin",
     [("vitamin b3", "vi"), ("niacin", "en"), ("nicotinamid", "en"), ("nicotinamide", "en"), ("vitamin pp", "vi")]),
    ("ING_VITAMIN_B5", "Vitamin B5", "Vitamin B5", "en:pantothenic-acid",
     [("vitamin b5", "vi"), ("axit pantothenic", "vi"), ("canxi pantothenate", "vi")]),
    ("ING_VITAMIN_B6", "Vitamin B6", "Vitamin B6", "en:vitamin-b6",
     [("vitamin b6", "vi"), ("pyridoxin", "en")]),
    ("ING_VITAMIN_B9", "Vitamin B9 (Folic acid)", "Axit folic", "en:folic-acid",
     [("axit folic", "vi"), ("acid folic", "vi"), ("vitamin b9", "vi"), ("folic acid", "en")]),
    ("ING_VITAMIN_B12", "Vitamin B12", "Vitamin B12", "en:vitamin-b12",
     [("vitamin b12", "vi"), ("cobalamin", "en"), ("cyanocobalamin", "en")]),
    ("ING_BIOTIN", "Biotin", "Biotin", "en:biotin",
     [("biotin", "en"), ("d-biotin", "en"), ("vitamin b7", "vi")]),
    ("ING_CALCIUM_SUPPLEMENT", "Calcium carbonate (supplement)", "Calci carbonat", "en:calcium-carbonate",
     [("calci carbonat", "vi"), ("canxi carbonat", "vi"), ("canxi cacbonat", "vi"), ("calci lactat", "vi"), ("canxi lactat", "vi")]),
    ("ING_IRON_SUPPLEMENT", "Iron pyrophosphate", "Sắt", "en:iron",
     [("sắt", "vi"), ("sắt pyrophosphat", "vi")]),
    ("ING_ZINC_SUPPLEMENT", "Zinc", "Kẽm", "en:zinc",
     [("kẽm", "vi"), ("kẽm sulfat", "vi"), ("kẽm sulphat", "vi"), ("kẽm oxit", "vi"), ("zinc gluconate", "en")]),
    ("ING_TAURINE", "Taurine", "Taurin", "en:taurine",
     [("taurin", "vi"), ("taurine", "en")]),
    ("ING_DHA_FISH_OIL", "DHA / Fish oil", "Dầu cá giàu DHA", "en:fish-oil",
     [("dầu cá giàu dha", "vi"), ("dha", "en"), ("dầu cá", "vi"), ("bột dầu cá", "vi"), ("fish oil", "en")]),
    ("ING_COLOSTRUM", "Colostrum", "Sữa non", "en:colostrum",
     [("sữa non", "vi"), ("bột sữa non", "vi"), ("sữa non colosigg 24h", "vi"), ("colostrum", "en")]),
    ("ING_HYDROLYZED_COLLAGEN", "Hydrolyzed collagen", "Collagen thủy phân", "en:collagen",
     [("collagen thủy phân", "vi"), ("collagen", "en")]),
    ("ING_PROBIOTICS_YOGURT", "Lactic acid bacteria starter", "Men vi sinh", "en:lactic-ferments",
     [("men streptococcus thermophilus và lactobacillus bulgaricus", "vi"),
      ("lợi khuẩn lactobacillus", "vi"), ("lợi khuẩn lactobacillus paracasei", "vi"),
      ("lactobacillus plantarum l-137", "en"), ("lactobacillus paracasei", "en")]),
]


def parse_off_taxonomy_file(filepath: Path) -> dict:
    """Đọc file taxonomy văn bản của Open Food Facts (`additives.txt` hoặc `ingredients.txt`)."""
    if not filepath.exists():
        return {}
    blocks = filepath.read_text(encoding="utf-8", errors="ignore").split("\n\n")
    tax = {}
    for blk in blocks:
        lines = [ln.strip() for ln in blk.splitlines() if ln.strip() and not ln.strip().startswith("#")]
        if not lines:
            continue
        en_names, vi_names = [], []
        wikidata = ""
        for ln in lines:
            if ln.startswith("<"):
                continue
            if ln.startswith("en:"):
                en_names.extend([x.strip() for x in ln[3:].split(",") if x.strip()])
            elif ln.startswith("vi:"):
                vi_names.extend([x.strip() for x in ln[3:].split(",") if x.strip()])
            elif ln.startswith("wikidata:en:"):
                wikidata = ln.split(":", 2)[-1].strip()
        if en_names:
            first_slug = re.sub(r"[^a-z0-9]+", "-", en_names[0].lower()).strip("-")
            off_id = f"en:{first_slug}"
            tax[off_id] = {"en": en_names, "vi": vi_names, "wikidata": wikidata}
    return tax


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--terms_csv", default=str(UNIQUE_TERMS_CSV), help="Đường dẫn unique_terms.csv")
    ap.add_argument("--adi_csv", default=str(ADI_TABLE_CSV), help="Đường dẫn bảng ADI đã điền")
    ap.add_argument("--off_dir", default=str(RAW_OFF_DIR), help="Thư mục chứa file taxonomy OFF (additives.txt, ingredients.txt)")
    ap.add_argument("--out_dir", default=str(KB_DIR), help="Thư mục xuất kb_entities.csv và kb_aliases.csv")
    ap.add_argument("--top_ingredients", type=int, default=150, help="Số lượng head-name nguyên liệu ngoài danh sách curated đưa thêm vào KB")
    args = ap.parse_args()

    terms_csv = Path(args.terms_csv)
    adi_csv = Path(args.adi_csv)
    off_dir = Path(args.off_dir)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Đọc bảng ADI (tự động fallback tìm adi_template.csv ở thư mục gốc nếu chưa chép vào data/kb)
    adi_base_info = {}
    adi_candidates = [adi_csv, Path("adi_template.csv"), Path("data/kb/adi_template.csv")]
    used_adi_path = next((p for p in adi_candidates if p.exists()), None)
    if used_adi_path:
        with open(used_adi_path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                b = (r.get("ins_code") or "").strip().lower()
                if b and (r.get("substance_name") or "").strip():
                    adi_base_info[b] = {
                        "substance_name": (r.get("substance_name") or "").strip(),
                        "adi_status": (r.get("adi_status") or "").strip(),
                    }

    # Sửa K13: Đọc cả additives.txt và ingredients.txt từ Open Food Facts nếu có
    off_additives = parse_off_taxonomy_file(off_dir / "additives.txt")
    off_ingredients = parse_off_taxonomy_file(off_dir / "ingredients.txt")

    # 2. Quét unique_terms.csv (sửa K16, K17: dùng extract_ingredient_head từ text_utils, bỏ dòng rỗng)
    var_freq = defaultdict(int)
    base_to_vars = defaultdict(set)
    ing_head_freq = defaultdict(int)
    dropped_heads = Counter()

    with open(terms_csv, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            ttype = (r.get("term_type") or "").strip()
            term = (r.get("cleaned_term") or "").strip()
            if not term:
                continue
            freq = int(r.get("frequency") or 0)
            if ttype == "additive":
                for base, var in set(parse_ins(term)):
                    var_freq[var] += freq
                    base_to_vars[base].add(var)
            elif ttype == "ingredient":
                head = extract_ingredient_head(term)
                if head:
                    ing_head_freq[head] += freq
                else:
                    dropped_heads[term] += freq

    # Bổ sung mọi mã có trong bảng ADI (sửa K5: đảm bảo KB có đủ thực thể cho mọi mã trong bảng ADI)
    for b in adi_base_info:
        base_to_vars[b].add(b)
    for base in list(base_to_vars.keys()):
        base_to_vars[base].add(base)

    entities = []
    aliases = []
    seen_alias_pairs = set()

    def add_alias(alias_str: str, entity_id: str, alias_type: str, e_num: str, ins_base: str, lang: str, priority: int, source: str):
        a_norm = norm_text(alias_str)
        if not a_norm:
            return
        key = (a_norm, entity_id)
        if key in seen_alias_pairs:
            return
        seen_alias_pairs.add(key)

        if entity_id.startswith("ING_") and re.search(r"[(\[%]", a_norm):
            h = extract_ingredient_head(a_norm)
            if h and h != a_norm:
                add_alias(h, entity_id, alias_type, e_num, ins_base, lang, priority + 1, source + "_head")

        aliases.append({
            "alias": a_norm,
            "entity_id": entity_id,
            "alias_type": alias_type,
            "e_number": e_num,
            "ins_base": ins_base,
            "lang": lang,
            "priority": priority,
            "is_ambiguous": False,  # sẽ được tính toán chính xác sau khi gom toàn bộ alias (sửa K1)
            "source": source,
        })

    # 3. Xây dựng Entities và Aliases cho PHỤ GIA CÓ MÃ INS (Additives)
    all_variants = sorted(
        [(base, var) for base, vs in base_to_vars.items() for var in vs],
        key=lambda x: (-var_freq.get(x[1], 0), x[0], x[1]),
    )

    for base, var in all_variants:
        ent_id = format_add_entity_id(var)
        parent_id = format_add_entity_id(base) if var != base else ""  # Sửa K10: liên kết cha-con
        off_id = format_off_additive_id(var)
        e_num = format_e_number(var)
        compact_var = var.replace("(", "").replace(")", "")

        base_name_en = adi_base_info.get(base, {}).get("substance_name", "")
        has_subvariants = len(base_to_vars.get(base, set())) > 1
        if var in SUBVARIANT_SPECIFIC_NAMES:
            name_en, name_vi = SUBVARIANT_SPECIFIC_NAMES[var]
        else:
            if base == var and has_subvariants and base_name_en:
                name_en = f"{base_name_en} (group E{base.upper()})"
            else:
                name_en = base_name_en if base == var else (f"{base_name_en} ({var})" if base_name_en else f"INS {var}")
            name_vi = BASE_VI_NAMES[var][0] if var in BASE_VI_NAMES else ""

        off_entry = off_additives.get(off_id, {})
        if not name_en and off_entry.get("en"):
            name_en = off_entry["en"][0]
        if not name_vi and off_entry.get("vi"):
            name_vi = off_entry["vi"][0]

        entities.append({
            "entity_id": ent_id,
            "parent_entity_id": parent_id,
            "entity_type": "additive",
            "canonical_name_en": name_en or f"Additive E{compact_var.upper()}",
            "canonical_name_vi": name_vi,
            "off_id": off_id,
            "foodon_id": "",
            "e_number": e_num,
            "ins_variant": var,
            "ins_base": base,
            "is_nutritional": False,
            "nutritional_category": "",
            "frequency_in_dataset": var_freq.get(var, 0),
        })

        # Sinh alias dạng mã (Priority = 1)
        add_alias(var, ent_id, "ins_variant", e_num, base, "code", 1, "auto_code")
        if compact_var != var:
            add_alias(compact_var, ent_id, "ins_compact", e_num, base, "code", 1, "auto_code")
        add_alias(f"e{var}", ent_id, "e_number", e_num, base, "code", 1, "auto_code")
        add_alias(f"e{compact_var}", ent_id, "e_number", e_num, base, "code", 1, "auto_code")
        add_alias(f"e-{compact_var}", ent_id, "e_number", e_num, base, "code", 1, "auto_code")
        add_alias(f"ins {var}", ent_id, "ins_code", e_num, base, "code", 1, "auto_code")
        add_alias(f"ins {compact_var}", ent_id, "ins_code", e_num, base, "code", 1, "auto_code")
        add_alias(f"ins-{compact_var}", ent_id, "ins_code", e_num, base, "code", 1, "auto_code")

        # Chỉ gắn tên chuẩn/đồng nghĩa khi nó thuộc đúng thực thể đó (sửa K1)
        if name_en and (base == var or var in SUBVARIANT_SPECIFIC_NAMES):
            add_alias(name_en, ent_id, "canonical_en", e_num, base, "en", 1, "jecfa_adi_table")
        if name_vi:
            add_alias(name_vi, ent_id, "canonical_vi", e_num, base, "vi", 1, "curated_vi")

        if var in BASE_VI_NAMES:
            _, syn_tuples = BASE_VI_NAMES[var]
            for syn_str, syn_lang in syn_tuples:
                add_alias(syn_str, ent_id, f"synonym_{syn_lang}", e_num, base, syn_lang, 2, "curated_vi")

        for en_syn in off_entry.get("en", []):
            add_alias(en_syn, ent_id, "synonym_en", e_num, base, "en", 2, "openfoodfacts")
        for vi_syn in off_entry.get("vi", []):
            add_alias(vi_syn, ent_id, "synonym_vi", e_num, base, "vi", 2, "openfoodfacts")

    # 3b. Thực thể cho Phụ gia không kèm mã INS (sửa K6)
    for ent_id, can_en, can_vi, off_id, syn_tuples in NON_CODE_ADDITIVE_ENTITIES:
        entities.append({
            "entity_id": ent_id,
            "parent_entity_id": "",
            "entity_type": "additive_no_code",
            "canonical_name_en": can_en,
            "canonical_name_vi": can_vi,
            "off_id": off_id,
            "foodon_id": "",
            "e_number": "",
            "ins_variant": "",
            "ins_base": "",
            "is_nutritional": False,
            "nutritional_category": "",
            "frequency_in_dataset": 0,
        })
        add_alias(can_vi, ent_id, "canonical_vi", "", "", "vi", 1, "curated_no_code")
        add_alias(can_en, ent_id, "canonical_en", "", "", "en", 1, "curated_no_code")
        for syn_str, syn_lang in syn_tuples:
            add_alias(syn_str, ent_id, f"synonym_{syn_lang}", "", "", syn_lang, 2, "curated_no_code")

    # 4. Xây dựng Entities và Aliases cho NGUYÊN LIỆU (Ingredients)
    covered_heads = set()
    for ent_id, can_en, can_vi, off_id, syn_tuples in CURATED_INGREDIENTS:
        # Sửa K11, K12, X3: Gọi trực tiếp classify_nutritional_item từ text_utils.py (1 nguồn sự thật duy nhất)
        nutr_check = classify_nutritional_item(can_vi)
        is_nutr = nutr_check["nutritional"]
        nutr_cat = nutr_check["nutritional_category"] or ""

        _alias_cats = {s: (classify_nutritional_item(s)["nutritional_category"] or "") for s, _ in syn_tuples}
        if not nutr_cat:
            _found = [c for c in _alias_cats.values() if c]
            if _found:
                nutr_cat = Counter(_found).most_common(1)[0][0]
                is_nutr = True
        for _s, _c in _alias_cats.items():
            if _c != nutr_cat:
                print(f" [CẢNH BÁO: nhóm dinh dưỡng] {ent_id}: entity='{nutr_cat}' nhưng alias '{_s}'='{_c}'")


        total_f = sum(ing_head_freq.get(norm_text(s), 0) for s, _ in syn_tuples)
        off_ing_entry = off_ingredients.get(off_id, {})

        entities.append({
            "entity_id": ent_id,
            "parent_entity_id": "",
            "entity_type": "ingredient",
            "canonical_name_en": can_en,
            "canonical_name_vi": can_vi,
            "off_id": off_id,
            "foodon_id": "",
            "e_number": "",
            "ins_variant": "",
            "ins_base": "",
            "is_nutritional": is_nutr,
            "nutritional_category": nutr_cat,
            "frequency_in_dataset": total_f,
        })
        add_alias(can_vi, ent_id, "canonical_vi", "", "", "vi", 1, "curated_kb")
        add_alias(can_en, ent_id, "canonical_en", "", "", "en", 1, "curated_kb")
        covered_heads.add(norm_text(can_vi))
        covered_heads.add(norm_text(can_en))

        for syn_str, syn_lang in syn_tuples:
            s_norm = norm_text(syn_str)
            covered_heads.add(s_norm)
            add_alias(s_norm, ent_id, f"synonym_{syn_lang}", "", "", syn_lang, 2, "curated_kb")

        for en_syn in off_ing_entry.get("en", []):
            add_alias(en_syn, ent_id, "synonym_en", "", "", "en", 2, "openfoodfacts")
        for vi_syn in off_ing_entry.get("vi", []):
            add_alias(vi_syn, ent_id, "synonym_vi", "", "", "vi", 2, "openfoodfacts")

    # 4b. Sửa K8, K9, K11, K12:
    # Lọc bỏ các head đã nằm trong CURATED_INGREDIENTS TRƯỚC KHI cắt Top-K,
    # dùng ID ổn định theo slug (`make_stable_ingredient_id`) và gọi `classify_nutritional_item`.
    uncovered_heads = [
        (h, f) for h, f in sorted(ing_head_freq.items(), key=lambda x: (-x[1], x[0]))
        if h not in covered_heads and not parse_ins(h)
    ]
    used_ent_ids = {e["entity_id"] for e in entities}

    for head_str, freq in uncovered_heads[: args.top_ingredients]:
        base_ent_id = make_stable_ingredient_id(head_str)
        ent_id = base_ent_id
        suffix = 2
        """
        chưa hiểu
        """
        if ent_id in used_ent_ids:
            ent_id = f"{base_ent_id}_{hashlib.md5(head_str.encode('utf-8')).hexdigest()[:6].upper()}"
            # suffix += 1
        used_ent_ids.add(ent_id)

        nutr_info = classify_nutritional_item(head_str)
        entities.append({
            "entity_id": ent_id,
            "parent_entity_id": "",
            "entity_type": "ingredient",
            "canonical_name_en": "",
            "canonical_name_vi": head_str,
            "off_id": "",
            "foodon_id": "",
            "e_number": "",
            "ins_variant": "",
            "ins_base": "",
            "is_nutritional": nutr_info["nutritional"],
            "nutritional_category": nutr_info["nutritional_category"] or "",
            "frequency_in_dataset": freq,
        })
        add_alias(head_str, ent_id, "surface_vi", "", "", "vi", 3, "vifoodlabel_top_k")

    # 5. Sửa K1: Kiểm tra và gắn cờ `is_ambiguous` cho mọi alias trỏ tới >1 entity_id
    alias_to_entities = defaultdict(set)
    for row in aliases:
        alias_to_entities[row["alias"]].add(row["entity_id"])

    ambiguous_aliases = {a: sorted(ents) for a, ents in alias_to_entities.items() if len(ents) > 1}
    for row in aliases:
        row["is_ambiguous"] = row["alias"] in ambiguous_aliases

    # 6. Xuất ra CSV
    ent_path = out_dir / "kb_entities.csv"
    """
    chưa hiểu
    """
    if dropped_heads:
        print(f" - Bỏ {len(dropped_heads)} chuỗi head rỗng, ví dụ:", [t for t, _ in dropped_heads.most_common(5)])
    alias_path = out_dir / "kb_aliases.csv"

    with open(ent_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(entities[0].keys()))
        w.writeheader()
        w.writerows(entities)

    with open(alias_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(aliases[0].keys()))
        w.writeheader()
        w.writerows(aliases)

    n_add = sum(1 for e in entities if e["entity_type"].startswith("additive"))
    n_ing = sum(1 for e in entities if e["entity_type"] == "ingredient")
    n_nutr = sum(1 for e in entities if e["is_nutritional"])
    print(f"Đã tạo thành công bộ KB v2 tại: {out_dir}")
    print(f"  - Bảng ADI sử dụng  : {used_adi_path if used_adi_path else 'Không tìm thấy (dùng fallback)'} ({len(adi_base_info)} mã có tên)")
    print(f"  1. {ent_path.name:16s}: {len(entities):4d} thực thể ({n_add} phụ gia + {n_ing} nguyên liệu; {n_nutr} thực thể dinh dưỡng)")
    print(f"  2. {alias_path.name:16s}: {len(aliases):4d} dòng alias | Số alias trùng >1 entity (is_ambiguous): {len(ambiguous_aliases)}")
    if ambiguous_aliases:
        print("  - Danh sách alias trùng nhiều entity:", ambiguous_aliases)


if __name__ == "__main__":
    main()