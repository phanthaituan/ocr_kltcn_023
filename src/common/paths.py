"""
paths.py
Nguồn duy nhất (single source of truth) cho mọi đường dẫn trong project.
Các script import từ đây thay vì hardcode đường dẫn tương đối, nên chạy từ thư mục nào cũng đúng.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# --- data/raw: BẤT BIẾN, không script nào được ghi vào đây ---
DATA = ROOT / "data"
RAW = DATA / "raw"
RAW_IMAGES_DIR = RAW / "ViFoodLabel_raw" / "images"
RAW_LABELS_DIR = RAW / "ViFoodLabel_raw" / "labels"
RAW_FOODON_DIR = RAW / "kb" / "foodon"
RAW_OFF_DIR = RAW / "kb" / "openfoodfacts"

# --- data/annotations: gold ---
ANNOTATIONS = DATA / "annotations"
GOLD_PARSED_DIR = ANNOTATIONS / "gold_parsed"
GOLD_KB_LINKS_DIR = ANNOTATIONS / "gold_kb_links"
GOLD_CATEGORIES_DIR = ANNOTATIONS / "gold_categories"
ADDITIVE_DECISIONS_CSV = ANNOTATIONS / "additive_decisions.csv"  # quyết định thủ công cho additive không có mã INS

# --- data/interim: file trung gian sinh tự động / chờ review ---
INTERIM = DATA / "interim"
REVIEW_DIR = INTERIM / "review"
UNIQUE_TERMS_CSV = INTERIM / "unique_terms.csv"
UNMATCHED_WARNINGS_CSV = REVIEW_DIR / "unmatched_warnings_review.csv"

# --- KB đã chuẩn hóa, split, kết quả ---
KB_DIR = DATA / "kb"
ADI_TABLE_CSV = KB_DIR / "adi_template.csv"  # đổi thành adi_table.csv khi điền xong (Bước 0.8)
SPLITS_DIR = DATA / "splits"
RESULTS_DIR = DATA / "results"
REPORTS_DIR = DATA / "reports"
COMPLETENESS_REPORT = REPORTS_DIR / "completeness_report_v2.csv"

# --- artifacts (không commit): FAISS index, weights ---
ARTIFACTS = ROOT / "artifacts"
FAISS_INDEX_DIR = ARTIFACTS / "faiss_index"
