# TECHNICAL SPECIFICATION
## Đề tài: OCR & Phân loại thành phần trên bao bì sản phẩm

**Phiên bản:** 1.0
**Cập nhật lần cuối:** 27/09/2026

> File này là tài liệu kỹ thuật tham chiếu. Khi có thay đổi thiết kế (đổi model, đổi schema, đổi KB...), cập nhật mục tương ứng **và** ghi lại vào phần "11. Changelog" ở cuối file.

---

## 1. Kiến trúc tổng thể

### 1.1. Ma trận 7 pipeline

| Mã | Trích xuất | Grounding | Input | Output |
|---|---|---|---|---|
| P0 | Rule/Dictionary | Không | Ảnh | Nhãn phân loại |
| P1 | Rule/Dictionary | FoodOn + OFF | Ảnh | Nhãn phân loại |
| P2 | LLM | Không | Ảnh | Nhãn phân loại |
| **Main** | **LLM** | **FoodOn + OFF** | **Ảnh** | **Nhãn phân loại** |
| V1 | VLM (API, lớn) | Không (E2E) | Ảnh | Nhãn phân loại |
| V2 | VLM (local, nhỏ) | Không (E2E) | Ảnh | Nhãn phân loại |
| Control | LLM | FoodOn + OFF | Gold OCR text (không phải ảnh) | Nhãn phân loại |

### 1.2. Sơ đồ pipeline chính (Main)

```
[Image]
   │
   ▼
[1] OCR  (PaddleOCR-VL / VietOCR+PaddleOCR — engine cố định cho toàn bộ P0-P2-Main)
   │  output: raw_text (string)
   ▼
[2] LLM chuẩn hóa
   │  - tách "Thành phần:" thành list các mục riêng lẻ
   │  - sửa lỗi chính tả/dấu do OCR
   │  - chuẩn hóa tên + gắn E-number nếu có
   │  - dịch/gắn nhãn song ngữ VI-EN
   │  output: List[NormalizedIngredient]  (JSON, xem schema mục 5.2)
   ▼
[3] Entity Linking
   │  - candidate generation: embedding similarity (multilingual-e5/LaBSE) trên FAISS index
   │    chứa toàn bộ label của FoodOn + Open Food Facts
   │  - re-rank/disambiguation: LLM chọn candidate đúng nhất trong top-k
   │  output: List[LinkedIngredient]  (xem schema mục 5.3)
   ▼
[4] Classification
   │  - lấy category có sẵn từ FoodOn/OFF (additive, allergen, category...)
   │  - hoặc map theo taxonomy tự định nghĩa (xem mục 1.3)
   │  output: List[ClassifiedIngredient]  (xem schema mục 5.4)
   ▼
[Kết quả cuối]
```

### 1.3. Taxonomy phân loại (ĐÃ CHỐT — 27/09/2026)

Phân loại **đa nhãn (multi-label)** — một ingredient có thể thuộc nhiều nhóm cùng lúc, gồm 4 nhóm:

| Nhãn | Định nghĩa | Nguồn tham chiếu gợi ý |
|---|---|---|
| **Phụ gia** (Additive) | Chất thêm vào với mục đích công nghệ (bảo quản, tạo màu, tạo mùi, tạo ngọt...) | OFF `additives_tags`, danh mục phụ gia VN (QCVN/Thông tư BYT), E-number Codex |
| **Dinh dưỡng** (Nutritional) | Thành phần có giá trị dinh dưỡng (vitamin, khoáng chất, protein, chất xơ...) | OFF nutrient taxonomy, USDA FoodData Central |
| **Chất gây dị ứng** (Allergen) | Nằm trong danh sách dị nguyên phổ biến (14 nhóm dị nguyên EU hoặc danh mục VN tương đương) | OFF `allergens_tags` |
| **Phụ gia cần lưu ý liều lượng** | Phụ gia có giới hạn ADI (Acceptable Daily Intake) theo JECFA/Codex, cần cảnh báo liều dùng | JECFA ADI database — **không có sẵn trong FoodOn/OFF, cần tự xây bảng tra riêng** |

⚠️ **Lưu ý thiết kế:** "Phụ gia cần lưu ý liều lượng" là **tập con** của "Phụ gia" (không loại trừ lẫn nhau). Một ingredient có thể vừa là "Phụ gia", vừa "Cần lưu ý liều lượng", vừa "Chất gây dị ứng" cùng lúc. Vì vậy annotation và metric đánh giá theo hướng **multi-label** (tính P/R/F1 riêng cho từng nhãn), không dùng accuracy đơn nhãn duy nhất (xem cập nhật ở mục 6).

➡️ Vì OFF/FoodOn không có nhãn "cần lưu ý liều lượng", sau bước Entity Linking (ra `kb_id`/E-number) cần thêm **bước tra chéo phụ** qua bảng ADI tự xây (JECFA/Codex) — coi đây là sub-step riêng trong Classification (mục 3.5), không phải một phần của Entity Linking chính.

*(Nếu sau này muốn đổi sang 4 lớp loại trừ nhau thay vì đa nhãn, cần sửa lại schema mục 5.4 và cách tính metric mục 6.)*

---

## 2. Datasets

| Dataset | Vai trò | Dùng cho pipeline |
|---|---|---|
| Bộ ảnh bao bì tự thu thập (VN) | **Dataset chính** — train/dev/test cho toàn bộ hệ thống | Tất cả (P0–V2, Control) |
| Open Food Facts (ảnh + ingredient text + taxonomy, incl. ~2.600 ingredient tag VN) | KB cho Entity Linking + nguồn nhãn category ground-truth | P1, Main (KB); tham chiếu nhãn cho toàn bộ |
| FoodOn ontology (OWL, ~34–47k class) | KB thứ hai cho Entity Linking | P1, Main |
| HalalBench (2026) | Benchmark đánh giá OCR đa ngôn ngữ | Đánh giá module OCR độc lập |
| Food Packaging OCR Dataset (Mendeley 2026) | Fine-tune/đánh giá OCR detection+recognition | Giai đoạn 0, module OCR |
| Food Products Ingredient Dataset (Mendeley 2024) | Tham chiếu taxonomy phân loại | Thiết kế taxonomy (mục 1.3) |
| PhoNER_COVID19 / VLSP NER | Pretrain/warm-start nếu làm NER fine-tuned tiếng Việt | Pipeline phụ (nếu triển khai thêm) |
| **JECFA/Codex ADI database** (tự biên soạn từ nguồn công khai JECFA) | Bảng tra E-number ↔ giới hạn ADI — **không có sẵn dataset đóng gói, cần tự tổng hợp** | Sub-step "tra ADI" trong Classification (mục 3.5), phục vụ nhãn "Phụ gia cần lưu ý liều lượng" |

---

## 3. Stack công nghệ theo từng bước pipeline

### 3.1. OCR (P0, P1, P2, Main)
- **Engine chính:** PaddleOCR-VL (0.9B) — *[cần benchmark & chốt ở GĐ0]*
- **Phương án thay thế:** VietOCR (recognition) + PaddleOCR (detection)
- **Baseline so sánh:** EasyOCR, Tesseract (`pytesseract` + `vie.traineddata`)
- **Metric đo:** CER/WER qua package `jiwer`

### 3.2. Rule/Dictionary (P0, P1)
- Matching: `flashtext` (Aho-Corasick) hoặc spaCy `EntityRuler`/`PhraseMatcher`
- Từ điển: tự biên soạn (danh mục phụ gia VN theo QCVN/Thông tư Bộ Y tế + E-number Codex)

### 3.3. LLM chuẩn hóa (P2, Main)
- API: Claude / GPT / Gemini (chọn 1 làm chính, ghi rõ model version dùng trong thí nghiệm)
- Structured output: Pydantic schema + function calling/structured output của API
- Orchestration (nếu cần multi-step prompt): LangChain hoặc code thuần

### 3.4. Entity Linking (P1, Main)
- Embedding: `multilingual-e5` hoặc `LaBSE` hoặc `BGE-M3`
- Vector index: FAISS (local) — có thể thay Qdrant/Chroma nếu cần persist
- Truy cập KB: package `openfoodfacts` (Python) hoặc REST API; `owlready2`/`rdflib` để load FoodOn OWL
- Re-rank: LLM (top-k candidate → chọn 1)

### 3.5. Classification (tất cả pipeline)
- P0/P1: rule-based hoặc `scikit-learn` (Logistic Regression/SVM/RandomForest) — output đa nhãn (multi-label), không phải 1 nhãn/ingredient
- P2/Main: LLM zero/few-shot prompting theo taxonomy đã chốt (mục 1.3), yêu cầu LLM trả về đủ 4 cờ nhãn (không chỉ 1 nhãn)
- Nguồn nhãn "Phụ gia"/"Dinh dưỡng"/"Dị ứng": category có sẵn từ OFF taxonomy khi có thể, thay vì tự suy diễn
- **Sub-step riêng — tra ADI:** sau khi có `kb_id`/E-number từ Entity Linking, tra chéo qua **bảng ADI tự xây** (từ JECFA/Codex, cần biên soạn ở Giai đoạn 0/1) để gắn nhãn "Phụ gia cần lưu ý liều lượng"; áp dụng cho mọi pipeline có E-number đã chuẩn hóa (P1, Main, và có thể cả V1/V2 nếu VLM trả về E-number)

### 3.6. VLM (V1, V2)
- V1 (API lớn): Claude / GPT-4o-5 / Gemini 2.5-3 Pro (vision)
- V2 (local nhỏ): PaddleOCR-VL (0.9B) hoặc Qwen3-VL bản nhỏ (7-8B)
- Serving local: Ollama (thử nghiệm nhanh) / vLLM (throughput) / llama.cpp (máy yếu)
- **Bắt buộc:** V1, V2 và Main phải dùng chung 1 schema output (mục 5.4) để so sánh công bằng

### 3.7. Công cụ dùng chung
- Annotation: Label Studio hoặc Doccano
- Metrics: `jiwer` (OCR), `seqeval` (NER/extraction), `scikit-learn.metrics` (classification)
- Experiment tracking: MLflow hoặc Weights & Biases
- Containerization: Docker (đảm bảo môi trường nhất quán giữa các pipeline)

---

## 4. Danh sách package dự kiến (requirements.txt nháp)

```
# OCR
paddleocr
vietocr
easyocr
pytesseract

# LLM / API
anthropic
openai
google-generativeai
pydantic
langchain          # nếu cần orchestration

# Entity Linking
sentence-transformers   # multilingual-e5 / LaBSE / BGE-M3
faiss-cpu                # hoặc faiss-gpu
owlready2
rdflib
openfoodfacts

# Classification / NLP
scikit-learn
spacy
flashtext
seqeval

# Eval & tracking
jiwer
mlflow

# VLM local serving
# (cài qua Ollama/vLLM riêng, không qua pip)
```

*(Cập nhật danh sách này khi thêm/bớt thư viện trong quá trình triển khai.)*

---

## 5. Data schema (JSON) giữa các bước

### 5.1. OCR output
```json
{
  "image_id": "string",
  "raw_text": "string",
  "bounding_boxes": [
    {"text": "string", "bbox": [0,0,0,0], "confidence": 0.0}
  ]
}
```

### 5.2. LLM chuẩn hóa output
```json
{
  "image_id": "string",
  "ingredients": [
    {
      "raw_span": "string",
      "normalized_name_vi": "string",
      "normalized_name_en": "string",
      "e_number": "string or null",
      "order_in_list": 0
    }
  ]
}
```

### 5.3. Entity Linking output
```json
{
  "image_id": "string",
  "ingredients": [
    {
      "normalized_name_vi": "string",
      "linked_kb": "foodon | openfoodfacts | none",
      "kb_id": "string or null",
      "kb_label": "string or null",
      "link_confidence": 0.0,
      "candidates_considered": ["kb_id_1", "kb_id_2"]
    }
  ]
}
```

### 5.4. Classification output (output cuối — dùng chung cho mọi pipeline kể cả V1/V2)
```json
{
  "image_id": "string",
  "pipeline": "P0 | P1 | P2 | Main | V1 | V2 | Control",
  "ingredients": [
    {
      "name": "string",
      "labels": {
        "is_additive": true,
        "is_nutritional": false,
        "is_allergen": false,
        "is_dosage_caution": false
      },
      "adi_value": "number or null",
      "adi_unit": "mg/kg thể trọng/ngày, hoặc null",
      "kb_id": "string or null"
    }
  ]
}
```
*(`labels` là đa nhãn — nhiều cờ có thể `true` cùng lúc, xem taxonomy mục 1.3. `adi_value`/`adi_unit` chỉ điền khi `is_dosage_caution = true`.)*

---

## 6. Kế hoạch đánh giá (Evaluation plan)

| Tầng | Metric | Công cụ | Áp dụng cho |
|---|---|---|---|
| OCR | CER, WER | `jiwer` | Module OCR độc lập + so với Control |
| Trích xuất ingredient | Precision, Recall, F1 (mức entity) | `seqeval` | P0–Main, V1, V2 |
| Entity Linking | Accuracy@1, Recall@5, MRR | code tùy chỉnh | P1, Main |
| Classification | Precision/Recall/F1 **riêng cho từng nhãn** (Phụ gia, Dinh dưỡng, Dị ứng, Cần lưu ý liều lượng) + Macro-F1 tổng, do đây là bài toán đa nhãn | `scikit-learn.metrics` (multilabel: `classification_report(..., target_names=[...])`) | Tất cả pipeline |
| Vận hành | Chi phí/1000 ảnh, latency trung bình, khả năng chạy offline | log thủ công | Tất cả, đặc biệt V1 vs V2 |

**Câu hỏi nghiên cứu cần trả lời qua so sánh:**
1. P0 → P2: giá trị của LLM (không có EL) là bao nhiêu?
2. P1 → Main: giá trị của LLM khi đã có EL là bao nhiêu?
3. P0 → P1: giá trị của Entity Linking (không có LLM) là bao nhiêu?
4. P2 → Main: giá trị của Entity Linking khi đã có LLM là bao nhiêu?
5. Main vs V1/V2: pipeline nhiều bước có thắng VLM end-to-end không, và đánh đổi (cost/latency) ra sao?
6. Control vs Main: bao nhiêu % lỗi của Main đến từ OCR so với từ LLM/EL/Classification?

---

## 7. Môi trường & hạ tầng

- **Python version:** *(điền khi chốt, khuyến nghị ≥3.10)*
- **GPU:** cần cho V2 nếu chạy Qwen3-VL nhỏ (khuyến nghị ≥16GB VRAM); PaddleOCR-VL có thể chạy CPU
- **Docker:** 1 image dùng chung cho toàn bộ pipeline để đảm bảo so sánh công bằng
- **API keys cần chuẩn bị:** *(điền provider LLM/VLM đã chọn)*
- **Lưu trữ:** ảnh gốc + annotation + kết quả từng pipeline nên tách thư mục rõ ràng, ví dụ:
```
data/
  raw_images/
  annotations/
    gold_ocr/
    gold_ingredients/
    gold_kb_links/
    gold_categories/
results/
  P0/
  P1/
  P2/
  Main/
  V1/
  V2/
  Control/
```

---

## 8. Xử lý dữ liệu (Data Processing)

### 8.1. Tiền xử lý ảnh (trước OCR/VLM)

| Kỹ thuật | Mục đích | Công cụ | Áp dụng |
|---|---|---|---|
| Deskew / hiệu chỉnh phối cảnh | Bao bì chụp nghiêng/cong (chai, lon) làm méo dòng chữ | OpenCV (`cv2.warpPerspective`), `deskew` | P0–Main (trước OCR), nên làm nhẹ cho V1/V2 |
| Tăng tương phản (CLAHE) | Ảnh thiếu sáng/không đều làm mờ chữ | `cv2.createCLAHE` | P0–Main |
| Khử nhiễu (denoise) | Ảnh điện thoại ISO cao nhiều noise | `cv2.fastNlMeansDenoising` | P0–Main |
| Super-resolution (tùy chọn) | Chữ trên bao bì rất nhỏ, ảnh gốc mờ | Real-ESRGAN — cẩn trọng vì có thể sinh ảo giác ký tự | Chỉ dùng khi ảnh thực sự kém |
| Phát hiện & crop vùng "Thành phần" | Giảm nhiễu do OCR/VLM xử lý cả logo, hình trang trí | Heuristic theo từ khóa + bounding box của OCR | P0–Main |
| Binarization | Một số OCR cổ điển cần ảnh nhị phân | `cv2.adaptiveThreshold` | Chỉ cần cho Tesseract, không cần cho PaddleOCR-VL/VietOCR |

### 8.2. Hậu xử lý văn bản (sau OCR, trước LLM/Entity Linking)

| Kỹ thuật | Mục đích | Công cụ | Áp dụng |
|---|---|---|---|
| **Chuẩn hóa Unicode NFC** | Tiếng Việt có 2 cách encode dấu → cùng 1 chữ ra 2 chuỗi khác nhau, gây lỗi matching âm thầm | `unicodedata.normalize('NFC', text)` | **Bắt buộc cho mọi pipeline**, kể cả trước khi đưa vào LLM |
| Loại ký tự nhiễu OCR | OCR sinh ký tự rác ở biên vùng crop | Regex cleanup tùy chỉnh | P0–Main |
| Tách câu ingredient list thành từng mục | Tránh tách nhầm bên trong ngoặc, vd "(E211, E202)" | Regex có xử lý ngoặc (P0/P1); LLM tự xử lý (P2/Main) | P0–Main |
| Spell correction lỗi OCR phổ biến | Cải thiện tỷ lệ match dictionary/KB | SymSpell (từ điển VN tự xây) cho P0/P1; LLM tự sửa ở P2/Main | P0–Main |
| Tokenization tiếng Việt | Cần cho bước rule-based/NER | `underthesea` hoặc `pyvi` | P0, P1 |

### 8.3. Tăng cường dữ liệu (Data Augmentation)

| Loại | Kỹ thuật | Dùng khi nào |
|---|---|---|
| Augment ảnh | Xoay nhẹ, warp phối cảnh, đổi ánh sáng, blur, glare giả lập | Chỉ nếu **fine-tune** module OCR — công cụ `albumentations` |
| Sinh dữ liệu tổng hợp | Render text tiếng Việt (từ danh sách nguyên liệu thật) lên nền bao bì giả lập, nhiều font | Nếu bộ ảnh thật thu thập ít (dưới vài trăm) |
| Augment text | Đồng nghĩa thay thế, back-translation VI-EN-VI | Chỉ nếu fine-tune NER/classifier riêng — công cụ `nlpaug` |

⚠️ Augmentation ảnh chỉ có ý nghĩa nếu **train/fine-tune** model OCR hoặc classifier. Nếu dùng toàn bộ model pretrained (PaddleOCR-VL, LLM API, VLM API) thì **ưu tiên thu thập thêm ảnh thật** thay vì augment giả lập.

### 8.4. Làm sạch & kiểm soát chất lượng dữ liệu (QC)

| Kỹ thuật | Mục đích | Công cụ |
|---|---|---|
| Phát hiện ảnh mờ/không đọc được | Loại trước khi annotate | Laplacian variance (`cv2.Laplacian(img, cv2.CV_64F).var()`) |
| De-duplicate | Tránh trùng lặp gây leakage train/test | Perceptual hashing (`imagehash`) hoặc so khớp text đã OCR |
| Đo inter-annotator agreement | Đảm bảo gold label đáng tin cậy, đặc biệt quan trọng với taxonomy đa nhãn | Cohen's Kappa / Krippendorff's Alpha (`sklearn.metrics.cohen_kappa_score`) |

### 8.5. Xử lý mất cân bằng nhãn (Class Imbalance)

Với taxonomy đa nhãn ở mục 1.3, phân bố gần như chắc chắn lệch ("Phụ gia" xuất hiện nhiều hơn hẳn "Dinh dưỡng"/"Cần lưu ý liều lượng").

| Kỹ thuật | Áp dụng ở đâu |
|---|---|
| Multi-label stratified split khi chia train/dev/test | `skmultilearn.model_selection.iterative_train_test_split` |
| Class weighting trong loss | Nếu fine-tune classifier (P0/P1 dạng scikit-learn/PhoBERT) |
| Oversampling nhóm thiểu số | Chỉ cho pipeline có train riêng, không áp dụng cho nhánh LLM prompting |
| Few-shot examples cân bằng 4 nhãn trong prompt | P2, Main — tránh LLM thiên vị đoán "Phụ gia" cho mọi trường hợp |

### 8.6. Chia tập dữ liệu (Train/Dev/Test split)

- **Split theo sản phẩm, không theo ảnh** — nếu 1 sản phẩm có nhiều ảnh (nhiều góc chụp), toàn bộ ảnh của sản phẩm phải nằm cùng 1 tập để tránh data leakage
- Multi-label stratified split (xem 8.5)
- Cân nhắc thêm **1 tập test riêng cho sản phẩm có ingredient không có trong FoodOn/OFF**, để đánh giá khả năng generalize thực sự của Entity Linking thay vì chỉ test trên sản phẩm dễ match

### 8.7. Tiền xử lý Knowledge Base (FoodOn + Open Food Facts) — riêng cho Entity Linking

- Chuẩn hóa label KB: lowercase, bỏ ký tự đặc biệt, strip HTML/markup còn sót trong taxonomy OFF
- Loại bỏ label trùng/synonym dư thừa trước khi build FAISS index
- Merge label từ FoodOn + OFF theo cùng 1 format thống nhất trước khi encode embedding, tránh 2 KB dùng 2 chuẩn khác nhau gây nhiễu candidate

### 8.8. Data versioning

- Dùng **DVC** (hoặc Git LFS) để track version của: bộ ảnh, file annotation, bảng ADI tự xây, taxonomy — vì các thành phần này sẽ thay đổi/mở rộng nhiều lần, cần biết annotation nào tương ứng version taxonomy nào

---

## 9. Annotation guideline (tóm tắt — chi tiết đầy đủ nằm ở file riêng khi soạn)

- Định nghĩa "1 ingredient entity" = một cụm từ được liệt kê như một thành phần riêng biệt trong danh sách (kể cả khi có mô tả kèm theo trong ngoặc, ví dụ "Chất bảo quản (E211)")
- Với ingredient ghép (ví dụ "dầu thực vật (dầu cọ, dầu nành)"): *(quy định cách xử lý — điền khi chốt guideline chi tiết)*
- Với case không có KB match phù hợp: gán `linked_kb: none` thay vì ép match sai

---

## 10. Các quyết định thiết kế còn mở (Open decisions)

> Theo dõi các điểm cần quyết định trong quá trình làm, cập nhật khi đã chốt.

| Vấn đề | Trạng thái | Quyết định |
|---|---|---|
| OCR engine chính thức | ⬜ Chưa chốt | |
| LLM provider chính thức (P2, Main) | ⬜ Chưa chốt | |
| Taxonomy phân loại cuối cùng | 🟢 Đã chốt | Đa nhãn: Phụ gia / Dinh dưỡng / Chất gây dị ứng / Phụ gia cần lưu ý liều lượng — xem mục 1.3 |
| Cách biên soạn bảng ADI (JECFA/Codex) | ⬜ Chưa chốt | Cần quyết định nguồn crawl/tổng hợp cụ thể ở Giai đoạn 0 |
| VLM nhỏ cho V2 | ⬜ Chưa chốt | |
| Số lượng ảnh test chính thức | ⬜ Chưa chốt | |
| Có làm synthetic data / augmentation hay không | ⬜ Chưa chốt | Phụ thuộc số lượng ảnh thật thu thập được ở GĐ0 (xem mục 8.3) |
| Chọn `multilingual-e5` / `LaBSE` / `BGE-M3` cho embedding EL | ⬜ Chưa chốt | Cần benchmark nhanh trên vài trăm cặp tên nguyên liệu VI ↔ label FoodOn/OFF |

---

## 11. Changelog

| Ngày | Phiên bản | Nội dung thay đổi |
|---|---|---|
| 27/09/2026 | 1.0 | Khởi tạo spec từ thiết kế pipeline + dataset + tool đã thống nhất |
| 27/09/2026 | 1.1 | Thêm mục 8 "Xử lý dữ liệu" (tiền xử lý ảnh, hậu xử lý text, augmentation, QC, class imbalance, train/test split, tiền xử lý KB, data versioning); đổi số thứ tự các mục 8→9 (Annotation), 9→10 (Open decisions), 10→11 (Changelog) |
| | | |
