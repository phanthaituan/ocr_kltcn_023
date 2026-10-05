# KẾ HOẠCH CHI TIẾT THỰC HIỆN ĐỀ TÀI
## OCR & Phân loại thành phần trên bao bì sản phẩm

**Phiên bản:** 1.0 — Tổng hợp từ `KeHoach_DeTai.md` + `TechnicalSpec_DeTai.md`
**Cập nhật lần cuối:** 27/09/2026

> File này là **bản thực thi chi tiết** — mỗi bước có: hành động cụ thể, công cụ, nơi chạy (Local/Kaggle), và output kỳ vọng. Dùng để làm theo trực tiếp, không cần mở lại 2 file gốc trừ khi cần tra chi tiết kỹ thuật sâu hơn (schema JSON, danh sách package...).

---

## 0. Tổng quan nhanh

**Mục tiêu:** So sánh 7 pipeline để chứng minh giá trị của pipeline chính `Image → OCR → LLM chuẩn hóa → Entity Linking → FoodOn/OFF → Classification`.

| Mã | Trích xuất | Grounding | Vai trò |
|---|---|---|---|
| P0 | Rule/Dictionary | Không | Sàn dưới cùng |
| P1 | Rule/Dictionary | FoodOn+OFF | Đo giá trị riêng của EL |
| P2 | LLM | Không | Đo giá trị riêng của LLM |
| **Main** | **LLM** | **FoodOn+OFF** | **Đóng góp chính** |
| V1 | VLM API lớn | Không (E2E) | So sánh end-to-end mạnh |
| V2 | VLM local nhỏ | Không (E2E) | Trade-off chi phí/triển khai |
| Control | LLM | FoodOn+OFF (input = gold OCR) | Đo % lỗi từ OCR |

**Taxonomy phân loại (đa nhãn):** Phụ gia / Dinh dưỡng / Chất gây dị ứng / Phụ gia cần lưu ý liều lượng (không loại trừ nhau).

**Phần cứng:** Local (i7-12700H, RTX 3060 6GB, 16GB RAM) + Kaggle (P100 16GB hoặc 2×T4, ~30 GPU-giờ/tuần, session ≤~9-12h). Nguyên tắc: **local làm mọi việc vừa 6GB VRAM** (OCR nhẹ, rule-based, EL inference, LLM/VLM API, classification nhẹ); **Kaggle chỉ dùng khi cần** VLM cỡ 7-8B (nếu chọn Qwen3-VL cho V2) hoặc fine-tune.

---

## GIAI ĐOẠN 0 — Chuẩn bị & Xử lý dữ liệu (Tuần 1–2)

### Bước 0.1 — Thu thập dữ liệu
| | |
|---|---|
| Hành động | Thu thập ≥300–500 ảnh bao bì thật, đa dạng loại sản phẩm/góc chụp/độ nét/ánh sáng |
| Nguồn | Tự chụp tại siêu thị/cửa hàng, hoặc crawl có kiểm soát từ sàn TMĐT |
| Nơi chạy | Local (thủ công) |
| Output | Thư mục `data/raw_images/` |

### Bước 0.2 — QC dữ liệu thô
| | |
|---|---|
| Hành động | Lọc ảnh mờ (ngưỡng Laplacian variance), de-duplicate ảnh trùng (perceptual hashing) |
| Công cụ | `cv2.Laplacian(img, cv2.CV_64F).var()`; package `imagehash` |
| Nơi chạy | Local (CPU, nhẹ) |
| Output | Danh sách ảnh đạt chuẩn → `data/raw_images_clean/` |

### Bước 0.3 — Tiền xử lý ảnh
| | |
|---|---|
| Hành động | Deskew/hiệu chỉnh phối cảnh → CLAHE tăng tương phản → denoise → crop vùng "Thành phần" (dựa bounding box OCR sơ bộ hoặc heuristic từ khóa) |
| Công cụ | OpenCV (`warpPerspective`, `createCLAHE`, `fastNlMeansDenoising`), package `deskew` |
| Nơi chạy | Local (CPU đủ, không cần GPU) |
| Output | `data/preprocessed_images/` |
| Ghi chú | Super-resolution (Real-ESRGAN) chỉ áp dụng nếu ảnh thực sự kém chất lượng |

### Bước 0.4 — Chốt OCR engine
| | |
|---|---|
| Hành động | Benchmark nhanh PaddleOCR-VL vs VietOCR+PaddleOCR vs EasyOCR trên ~30-50 ảnh mẫu, đo CER/WER |
| Công cụ | `jiwer` |
| Nơi chạy | Local (RTX 3060 6GB đủ cho cả 3 engine) |
| Output | Quyết định ghi vào mục 9 (Open decisions) của `TechnicalSpec_DeTai.md` |

### Bước 0.5 — Viết annotation guideline
| | |
|---|---|
| Hành động | Định nghĩa rõ: thế nào là 1 "ingredient entity", cách xử lý ingredient ghép (vd "dầu thực vật (dầu cọ, dầu nành)"), cách gán khi không có KB match |
| Nơi chạy | Local (tài liệu) |
| Output | Guideline document (phần mở rộng của mục 8, TechnicalSpec) |

### Bước 0.6 — Annotate dữ liệu gold
| | |
|---|---|
| Hành động | Gán nhãn: gold OCR text (sửa tay), gold ingredient list (tách mục), gold KB link (FoodOn ID/OFF tag), gold category (4 nhãn đa nhãn) |
| Công cụ | Label Studio hoặc Doccano |
| Nơi chạy | Local (giao diện annotate chạy nhẹ, không cần GPU) |
| Output | `data/annotations/{gold_ocr, gold_ingredients, gold_kb_links, gold_categories}/` |
| Ghi chú | Nếu có ≥2 người annotate, đo Cohen's Kappa để kiểm tra độ đồng thuận |

### Bước 0.7 — Hậu xử lý text (chuẩn bị cho bước LLM/EL sau này)
| | |
|---|---|
| Hành động | Chuẩn hóa Unicode NFC (bắt buộc), loại ký tự nhiễu OCR, xây SymSpell cho lỗi chính tả phổ biến |
| Công cụ | `unicodedata.normalize('NFC', ...)`, `symspellpy` |
| Nơi chạy | Local |
| Output | Module text cleaning tái sử dụng cho toàn bộ pipeline P0–Main |

### Bước 0.8 — Biên soạn bảng ADI (JECFA/Codex)
| | |
|---|---|
| Hành động | Tổng hợp bảng E-number ↔ giới hạn ADI từ JECFA/Codex (không có dataset đóng gói sẵn, cần tự crawl/tổng hợp thủ công hoặc bán tự động) |
| Nơi chạy | Local |
| Output | `data/adi_table.csv` — phục vụ nhãn "Phụ gia cần lưu ý liều lượng" |

### Bước 0.9 — Chuẩn hóa Knowledge Base (FoodOn + OFF)
| | |
|---|---|
| Hành động | Tải FoodOn (OWL) + Open Food Facts taxonomy → chuẩn hóa label (lowercase, bỏ ký tự đặc biệt, strip markup) → merge 2 KB về cùng format |
| Công cụ | `owlready2`/`rdflib` (FoodOn), package `openfoodfacts` (OFF) |
| Nơi chạy | Local |
| Output | `kb/foodon_off_merged.json` |

### Bước 0.10 — Chia train/dev/test
| | |
|---|---|
| Hành động | Split theo **sản phẩm** (không theo ảnh, tránh leakage) + multi-label stratified split để tỷ lệ 4 nhãn đồng đều giữa các tập |
| Công cụ | `skmultilearn.model_selection.iterative_train_test_split` |
| Nơi chạy | Local |
| Output | `data/splits/{train, dev, test}.json` |
| Ghi chú | Cân nhắc thêm 1 tập test riêng cho ingredient không có trong FoodOn/OFF để đo khả năng generalize của EL |

### Bước 0.11 — Quyết định augmentation/synthetic data
| | |
|---|---|
| Hành động | Nếu số ảnh thật <300: cân nhắc sinh thêm synthetic (render text VI lên nền bao bì giả lập); nếu đủ, bỏ qua bước này |
| Nơi chạy | Local |
| Output | Cập nhật Open decisions trong TechnicalSpec |

### Bước 0.12 — Setup môi trường & data versioning
| | |
|---|---|
| Hành động | Tạo Docker image dùng chung; setup DVC/Git LFS để track version ảnh/annotation/bảng ADI/taxonomy; viết `requirements.txt` (theo mục 4, TechnicalSpec) |
| Nơi chạy | Local |
| Output | Repo sẵn sàng, môi trường tái lập được |

**✅ Deliverable Giai đoạn 0:** bộ dữ liệu đã annotate + OCR engine đã chốt + KB đã chuẩn hóa + môi trường dev sẵn sàng.

---

## GIAI ĐOẠN 1 — Build P0, P1 (Tuần 3–4)

### Bước 1.1 — Xây từ điển nguyên liệu/phụ gia
| | |
|---|---|
| Hành động | Biên soạn danh mục phụ gia VN (QCVN/Thông tư BYT) + E-number Codex thành từ điển tra cứu |
| Nơi chạy | Local |
| Output | `dict/additive_dictionary.json` |

### Bước 1.2 — Implement rule-based matching
| | |
|---|---|
| Hành động | Matching tên ingredient trong text đã OCR/chuẩn hóa với từ điển |
| Công cụ | `flashtext` (Aho-Corasick) hoặc spaCy `EntityRuler` |
| Nơi chạy | Local (CPU thuần) |
| Output | Module `match_dictionary.py` |

### Bước 1.3 — Build P0 hoàn chỉnh
| | |
|---|---|
| Hành động | Ghép: OCR (đã chốt ở GĐ0) → Dictionary matching → Classification rule-based/`scikit-learn` (đa nhãn) |
| Nơi chạy | Local |
| Output | Pipeline P0 chạy end-to-end, output theo schema mục 5.4 (TechnicalSpec) |

### Bước 1.4 — Setup Entity Linking
| | |
|---|---|
| Hành động | Encode toàn bộ label KB (đã chuẩn hóa ở bước 0.9) bằng embedding đa ngôn ngữ → build FAISS index |
| Công cụ | `sentence-transformers` (multilingual-e5/LaBSE/BGE-M3), `faiss-cpu` |
| Nơi chạy | Local (RTX 3060 6GB đủ cho encode 1 lần toàn bộ KB) |
| Output | `kb/faiss_index.bin` |

### Bước 1.5 — Implement candidate generation + linking
| | |
|---|---|
| Hành động | Với mỗi ingredient đã match ở P0, encode và tìm top-k candidate gần nhất trong FAISS index |
| Nơi chạy | Local |
| Output | Module `entity_linking.py` |

### Bước 1.6 — Build P1 hoàn chỉnh
| | |
|---|---|
| Hành động | Ghép: P0 + Entity Linking (không dùng LLM re-rank, chỉ dùng similarity top-1) |
| Nơi chạy | Local |
| Output | Pipeline P1 chạy end-to-end |

### Bước 1.7 — Chạy thử P0, P1 trên tập dev
| | |
|---|---|
| Hành động | Log kết quả sơ bộ, kiểm tra lỗi pipeline trước khi sang giai đoạn sau |
| Nơi chạy | Local |
| Output | `results/P0/dev_results.json`, `results/P1/dev_results.json` |

**✅ Deliverable Giai đoạn 1:** P0, P1 chạy được end-to-end trên tập dev.

---

## GIAI ĐOẠN 2 — Build P2, Main (Tuần 5–6)

### Bước 2.1 — Prompt engineering cho bước LLM chuẩn hóa
| | |
|---|---|
| Hành động | Thiết kế prompt: tách mục ingredient, sửa lỗi OCR, chuẩn hóa tên + E-number, dịch/gắn nhãn song ngữ VI-EN |
| Công cụ | API LLM đã chọn (Claude/GPT/Gemini) |
| Nơi chạy | Local (chỉ cần gọi API, không cần GPU) |
| Output | Prompt template + few-shot examples |

### Bước 2.2 — Định nghĩa structured output schema
| | |
|---|---|
| Hành động | Định nghĩa Pydantic schema khớp với mục 5.2 (TechnicalSpec), ép LLM trả JSON đúng format |
| Nơi chạy | Local |
| Output | `schemas/llm_normalize_schema.py` |

### Bước 2.3 — Build P2 hoàn chỉnh
| | |
|---|---|
| Hành động | Ghép: OCR → LLM chuẩn hóa → LLM classification trực tiếp (zero/few-shot, đa nhãn, few-shot cân bằng giữa 4 nhãn) |
| Nơi chạy | Local |
| Output | Pipeline P2 chạy end-to-end |

### Bước 2.4 — Tích hợp Entity Linking vào sau LLM
| | |
|---|---|
| Hành động | Dùng lại module `entity_linking.py` (Giai đoạn 1) nhưng input là output đã chuẩn hóa bởi LLM thay vì output dictionary |
| Nơi chạy | Local |
| Output | Module tái sử dụng, không cần viết lại |

### Bước 2.5 — Thêm bước re-rank bằng LLM
| | |
|---|---|
| Hành động | Với top-k candidate từ FAISS, dùng LLM chọn candidate đúng nhất (disambiguation) |
| Nơi chạy | Local (API call) |
| Output | Module `llm_rerank.py` |

### Bước 2.6 — Build Main hoàn chỉnh
| | |
|---|---|
| Hành động | Ghép: OCR → LLM chuẩn hóa → EL (candidate gen + LLM re-rank) → tra bảng ADI → Classification |
| Nơi chạy | Local |
| Output | Pipeline **Main** chạy end-to-end — đây là pipeline trung tâm của đề tài |

### Bước 2.7 — Chạy thử P2, Main trên tập dev
| | |
|---|---|
| Hành động | So sánh sơ bộ với P0/P1 để phát hiện lỗi/bất thường sớm |
| Nơi chạy | Local |
| Output | `results/P2/dev_results.json`, `results/Main/dev_results.json` |

**✅ Deliverable Giai đoạn 2:** P2, Main chạy được end-to-end trên tập dev.

---

## GIAI ĐOẠN 3 — Build V1, V2 (Tuần 7)

### Bước 3.1 — Setup V1 (VLM API lớn)
| | |
|---|---|
| Hành động | Setup API (Claude/GPT/Gemini vision), thiết kế prompt yêu cầu structured output khớp schema mục 5.4 |
| Nơi chạy | Local (chỉ cần API call) |
| Output | Module `v1_vlm_api.py` |

### Bước 3.2 — Quyết định model cho V2
| | |
|---|---|
| Hành động | Chọn giữa PaddleOCR-VL (0.9B, chạy tốt local) hoặc Qwen3-VL 7-8B (cần VRAM >6GB) |
| Nơi chạy | Quyết định tại Local |
| Output | Ghi vào Open decisions (TechnicalSpec) |

### Bước 3.3a — Nếu chọn PaddleOCR-VL cho V2
| | |
|---|---|
| Hành động | Setup local serving, thiết kế prompt/schema output giống V1 |
| Nơi chạy | **Local** (nhẹ, RTX 3060 6GB đủ) |
| Output | Module `v2_vlm_local.py` |

### Bước 3.3b — Nếu chọn Qwen3-VL 7-8B cho V2
| | |
|---|---|
| Hành động | Setup notebook Kaggle riêng, cài đặt qua Ollama/vLLM, load model ở 8-bit hoặc full nếu VRAM cho phép |
| Nơi chạy | **Kaggle** (16GB VRAM, tách notebook riêng để quản lý quota giờ) |
| Output | Kaggle notebook `v2_qwen3vl.ipynb`, code đồng bộ qua GitHub |
| Lưu ý | Bật Internet toggle nếu cần tải model/API; dùng Kaggle Secrets cho API key nếu có |

### Bước 3.4 — Thống nhất schema output V1/V2/Main
| | |
|---|---|
| Hành động | Đảm bảo cả 3 pipeline trả cùng format JSON (mục 5.4) để so sánh công bằng |
| Nơi chạy | Local |
| Output | Schema validator dùng chung |

### Bước 3.5 — Chạy thử V1, V2 trên tập dev
| | |
|---|---|
| Hành động | Đo sơ bộ chất lượng + chi phí/latency |
| Nơi chạy | V1: Local; V2: Local hoặc Kaggle tùy lựa chọn ở 3.2 |
| Output | `results/V1/dev_results.json`, `results/V2/dev_results.json` |

**✅ Deliverable Giai đoạn 3:** V1, V2 chạy được end-to-end trên tập dev.

---

## GIAI ĐOẠN 4 — Control & Đánh giá tổng hợp (Tuần 8)

### Bước 4.1 — Chạy Gold-OCR ablation (Control)
| | |
|---|---|
| Hành động | Chạy Main với input = gold OCR text (thay vì OCR thật) để đo cận trên lý thuyết |
| Nơi chạy | Local |
| Output | `results/Control/test_results.json` |

### Bước 4.2 — Chạy toàn bộ 7 pipeline trên tập test chính thức
| | |
|---|---|
| Hành động | Batch run P0, P1, P2, Main, V1, V2, Control trên tập test (chưa từng đụng tới trước đó) |
| Nơi chạy | P0/P1/P2/Main/V1/Control: **Local**; V2 nếu là Qwen3-VL: **Kaggle** |
| Output | `results/{pipeline}/test_results.json` cho cả 7 pipeline |

### Bước 4.3 — Tính metrics từng tầng
| | |
|---|---|
| Hành động | CER/WER (OCR) → P/R/F1 (extraction) → Accuracy@1/Recall@5/MRR (EL) → P/R/F1 đa nhãn + Macro-F1 (classification) |
| Công cụ | `jiwer`, `seqeval`, `scikit-learn.metrics` |
| Nơi chạy | Local |
| Output | Bảng kết quả tổng hợp |

### Bước 4.4 — Đo chi phí & latency
| | |
|---|---|
| Hành động | Log chi phí API/1000 ảnh, latency trung bình, khả năng chạy offline cho từng pipeline |
| Nơi chạy | Local |
| Output | Bảng so sánh vận hành |

### Bước 4.5 — Error analysis
| | |
|---|---|
| Hành động | Chọn mẫu lỗi điển hình mỗi pipeline, phân loại nguyên nhân (OCR/LLM/EL/Classification) dựa trên so sánh với Control |
| Nơi chạy | Local |
| Output | Báo cáo phân tích lỗi |

### Bước 4.6 — Trả lời 6 câu hỏi nghiên cứu
| | |
|---|---|
| Hành động | Dùng bảng kết quả để trả lời các câu hỏi P0→P2, P1→Main, P0→P1, P2→Main, Main vs V1/V2, Control vs Main (xem mục 6, TechnicalSpec) |
| Nơi chạy | Local |
| Output | Phần "Kết quả & Thảo luận" của báo cáo |

**✅ Deliverable Giai đoạn 4:** bảng kết quả đầy đủ + phân tích lỗi cho cả 7 pipeline.

---

## GIAI ĐOẠN 5 — Viết báo cáo (Tuần 9+)

| Bước | Hành động |
|---|---|
| 5.1 | Tổng hợp kết quả thành bảng biểu, biểu đồ |
| 5.2 | Viết báo cáo/luận văn: methodology → kết quả → thảo luận → hạn chế |
| 5.3 | Chuẩn bị slide trình bày |
| 5.4 | Review nội bộ trước khi nộp/bảo vệ |

**✅ Deliverable Giai đoạn 5:** báo cáo hoàn chỉnh + slide.

---

## Bảng phân bổ Local vs Kaggle (tổng hợp)

| Nhóm công việc | Local | Kaggle |
|---|---|---|
| Dev/debug code, test mẫu nhỏ | ✅ Luôn luôn | |
| OCR (PaddleOCR-VL/VietOCR), Rule-based, Classification nhẹ | ✅ | |
| Entity Linking (embedding + FAISS) | ✅ | |
| LLM API (P2, Main), VLM API (V1) | ✅ | |
| V2 nếu chọn PaddleOCR-VL | ✅ | |
| V2 nếu chọn Qwen3-VL 7-8B | | ✅ (VRAM 16GB) |
| Fine-tune (nếu làm thêm NER/classifier) | | ✅ |
| Batch chạy full test set (trừ V2 nặng) | ✅ | |

---

## Timeline tổng thể

| Tuần | Giai đoạn | Trọng tâm |
|---|---|---|
| 1–2 | GĐ0 | Dữ liệu, xử lý dữ liệu, môi trường |
| 3–4 | GĐ1 | P0, P1 |
| 5–6 | GĐ2 | P2, Main (pipeline chính) |
| 7 | GĐ3 | V1, V2 |
| 8 | GĐ4 | Control + đánh giá tổng hợp |
| 9+ | GĐ5 | Báo cáo |

---

## Ghi chú sử dụng file này

- File này **không thay thế** `KeHoach_DeTai.md` (theo dõi tiến độ % / trạng thái) và `TechnicalSpec_DeTai.md` (chi tiết kỹ thuật: schema, dataset, package) — 3 file bổ trợ nhau:
  - `KeHoach_ChiTiet_ThucHien.md` (file này): **làm gì, theo thứ tự nào, ở đâu**
  - `KeHoach_DeTai.md`: **theo dõi đã làm tới đâu**
  - `TechnicalSpec_DeTai.md`: **tra cứu chi tiết kỹ thuật khi cần**
- Khi có thay đổi thiết kế lớn, nên cập nhật đồng bộ cả 3 file.
