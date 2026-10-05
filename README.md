# Khóa luận: OCR & Phân loại thành phần trên bao bì sản phẩm

Xem kế hoạch và đặc tả kỹ thuật trong [`plan_docs/`](plan_docs/).

## Cấu trúc thư mục

```
data/
  raw/            # BẤT BIẾN: ảnh + label gốc ViFoodLabel, FoodOn .owl, OFF taxonomy
  annotations/    # gold: gold_parsed/ (600 JSON), gold_kb_links/, gold_categories/, additive_decisions.csv
  interim/        # file sinh tự động, tạo lại được: unique_terms.csv, review/ (warning chưa match)
  kb/             # KB FoodOn + OFF đã chuẩn hóa, bảng ADI (adi_template.csv -> adi_table.csv)
  splits/         # train / dev / test
  reports/        # báo cáo chất lượng dữ liệu
  results/        # output từng pipeline: P0 P1 P2 Main V1 V2 Control
  archive/        # phiên bản cũ (v1), không dùng nữa
src/
  common/         # paths.py (đường dẫn dùng chung), text cleaning, schemas
  data_pipeline/  # parse / extract / review dữ liệu
  entity_linking/ ocr/ llm/ classification/ pipelines/ evaluation/ models/
artifacts/        # FAISS index, weights (không commit)
notebooks/ scripts/ configs/
```

## Quy ước

- Không script nào ghi vào `data/raw/`.
- Mọi đường dẫn lấy từ `src/common/paths.py`, không hardcode.
- Chạy script từ thư mục gốc: `python src/data_pipeline/parse_vifoodlabel.py`.

## Chạy pipeline dữ liệu

```bash
python src/data_pipeline/parse_vifoodlabel.py      # raw labels -> annotations/gold_parsed
python src/data_pipeline/extract_unique_terms.py   # gold_parsed -> interim/unique_terms.csv
python src/data_pipeline/review_unmatched.py       # warning chưa match -> interim/review/
```
