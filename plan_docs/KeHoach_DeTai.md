# KẾ HOẠCH THỰC HIỆN ĐỀ TÀI
## OCR & Phân loại thành phần trên bao bì sản phẩm

**Cập nhật lần cuối:** 27/09/2026
**Trạng thái tổng thể:** 🔴 Chưa bắt đầu

> File này dùng để **theo dõi tiến độ**. Cách dùng: tick `[x]` vào các mục đã xong, cập nhật cột "Trạng thái" ở mỗi giai đoạn, và ghi chú vào phần "Nhật ký cập nhật" ở cuối file mỗi khi có quyết định/thay đổi quan trọng.

---

## 1. Mục tiêu đề tài

Xây dựng và so sánh các pipeline OCR nhận diện + phân loại thành phần trên bao bì sản phẩm, nhằm đề xuất và chứng minh giá trị của pipeline chính:

```
Image → OCR → LLM chuẩn hóa → Entity Linking → FoodOn/Open Food Facts → Classification
```

so với các baseline không có LLM, không có Entity Linking, và so với các baseline VLM end-to-end.

---

## 2. Bộ pipeline cần xây dựng (tham chiếu nhanh)

| Mã | Tên | Trích xuất | Grounding (KB) | Vai trò |
|---|---|---|---|---|
| P0 | Baseline | Rule/Dictionary | Không | Sàn dưới cùng |
| P1 | Rule + EL | Rule/Dictionary | Có (FoodOn/OFF) | Đo riêng giá trị của EL |
| P2 | LLM only | LLM | Không | Đo riêng giá trị của LLM |
| **Main** | **Pipeline chính** | **LLM** | **Có (FoodOn/OFF)** | **Đóng góp chính của đề tài** |
| V1 | VLM-E2E lớn (API) | VLM trực tiếp | Không | So sánh với hướng end-to-end mạnh |
| V2 | VLM-E2E nhỏ (local) | VLM trực tiếp | Không | So sánh trade-off chi phí/triển khai |
| Control | Gold-OCR → Main | LLM (input = OCR đã sửa tay) | Có | Đo % lỗi đến từ OCR |

*(Xem chi tiết kiến trúc, công cụ, dataset ở file `TechnicalSpec_DeTai.md`.)*

---

## 3. Lộ trình theo giai đoạn

### 🔲 Giai đoạn 0 — Chuẩn bị dữ liệu & môi trường (Tuần 1–2)
**Trạng thái:** ⬜ Chưa bắt đầu

- [ ] Thu thập ảnh bao bì thật (mục tiêu ≥300–500 ảnh, đa dạng loại sản phẩm/góc chụp/độ nét)
- [ ] QC dữ liệu thô: lọc ảnh mờ (Laplacian variance), de-duplicate (imagehash) — *TechnicalSpec mục 8.4*
- [ ] Xây pipeline tiền xử lý ảnh: deskew, CLAHE, denoise, crop vùng "Thành phần" — *mục 8.1*
- [ ] Quyết định có cần synthetic data / augmentation hay không (phụ thuộc số ảnh thật thu thập được) — *mục 8.3*
- [ ] Viết annotation guideline (định nghĩa rõ: thế nào là 1 "entity" ingredient, cách xử lý case mơ hồ)
- [ ] Annotate gold OCR text (transcript sửa tay)
- [ ] Annotate gold ingredient list (tách mục)
- [ ] Annotate gold KB link (FoodOn ID / OFF tag) cho từng ingredient
- [ ] Annotate gold category (nhãn phân loại cuối)
- [ ] Đo inter-annotator agreement (nếu có ≥2 người gán nhãn)
- [x] Chốt taxonomy classification cuối cùng — đa nhãn: **Phụ gia / Dinh dưỡng / Chất gây dị ứng / Phụ gia cần lưu ý liều lượng** (chi tiết ở `TechnicalSpec_DeTai.md` mục 1.3)
- [ ] Biên soạn bảng tra ADI (JECFA/Codex) cho nhãn "Phụ gia cần lưu ý liều lượng" — không có sẵn dataset đóng gói, cần tự tổng hợp
- [ ] Benchmark nhanh 2–3 OCR engine (PaddleOCR-VL, VietOCR+PaddleOCR, EasyOCR) trên tập nhỏ, chốt 1 engine dùng xuyên suốt
- [ ] Implement hậu xử lý text sau OCR: chuẩn hóa Unicode NFC (bắt buộc), loại ký tự nhiễu, spell correction — *mục 8.2*
- [ ] Chuẩn hóa & merge label KB (FoodOn + OFF) về cùng 1 format trước khi build FAISS index — *mục 8.7*
- [ ] Thiết kế train/dev/test split: theo sản phẩm (tránh leakage) + multi-label stratified — *mục 8.5, 8.6*
- [ ] Setup data versioning (DVC hoặc Git LFS) cho ảnh/annotation/bảng ADI/taxonomy — *mục 8.8*
- [ ] Setup môi trường dev (Docker, requirements.txt, repo structure)

**Deliverable:** bộ dữ liệu đã annotate + OCR engine đã chốt

---

### 🔲 Giai đoạn 1 — Baseline P0, P1 (Tuần 3–4)
**Trạng thái:** ⬜ Chưa bắt đầu

- [ ] Xây dựng từ điển nguyên liệu + danh mục phụ gia/E-number (VN + Codex)
- [ ] Implement matching rule-based (FlashText / spaCy EntityRuler)
- [ ] Build P0 hoàn chỉnh: OCR → Dictionary matching → Classification (rule hoặc scikit-learn)
- [ ] Setup embedding model đa ngôn ngữ (multilingual-e5/LaBSE) cho Entity Linking
- [ ] Setup vector index (FAISS) cho FoodOn + Open Food Facts
- [ ] Implement candidate generation + linking logic
- [ ] Build P1 hoàn chỉnh: P0 + Entity Linking
- [ ] Chạy thử P0, P1 trên tập dev, log kết quả sơ bộ

**Deliverable:** P0, P1 chạy được end-to-end trên tập dev

---

### 🔲 Giai đoạn 2 — Pipeline LLM: P2, Main (Tuần 5–6)
**Trạng thái:** ⬜ Chưa bắt đầu

- [ ] Prompt engineering cho bước LLM chuẩn hóa (tách mục, sửa lỗi OCR, dịch/gắn nhãn song ngữ)
- [ ] Định nghĩa structured output schema (Pydantic) cho output của LLM
- [ ] Build P2 hoàn chỉnh: OCR → LLM → Classification (zero/few-shot)
- [ ] Tích hợp Entity Linking (đã có từ Giai đoạn 1) vào sau bước LLM
- [ ] Thêm bước re-rank candidate EL bằng LLM (disambiguation)
- [ ] Build Main hoàn chỉnh: OCR → LLM → EL → FoodOn/OFF → Classification
- [ ] Chạy thử P2, Main trên tập dev, so sánh sơ bộ với P0/P1

**Deliverable:** P2, Main chạy được end-to-end trên tập dev

---

### 🔲 Giai đoạn 3 — VLM baselines: V1, V2 (Tuần 7)
**Trạng thái:** ⬜ Chưa bắt đầu

- [ ] Setup API cho V1 (Claude/GPT/Gemini vision) + thiết kế prompt structured output
- [ ] Setup local serving cho V2 (Ollama/vLLM/llama.cpp) với PaddleOCR-VL hoặc Qwen3-VL nhỏ
- [ ] Thống nhất schema output giữa V1, V2 và pipeline Main (để so sánh công bằng)
- [ ] Chạy thử V1, V2 trên tập dev
- [ ] Đo sơ bộ chi phí/latency của V1 vs V2

**Deliverable:** V1, V2 chạy được end-to-end trên tập dev

---

### 🔲 Giai đoạn 4 — Control & Đánh giá tổng hợp (Tuần 8)
**Trạng thái:** ⬜ Chưa bắt đầu

- [ ] Chạy Gold-OCR ablation (Main với input = gold OCR text)
- [ ] Chạy toàn bộ 7 pipeline trên tập test chính thức (không đụng vào từ đầu)
- [ ] Tính metrics từng tầng: CER/WER (OCR), P/R/F1 (extraction), Accuracy@1/Recall@5/MRR (EL), Accuracy/Macro-F1 (classification)
- [ ] Đo chi phí & latency từng pipeline
- [ ] Error analysis: chọn mẫu lỗi điển hình của từng pipeline, phân loại nguyên nhân lỗi (OCR/LLM/EL/Classification)
- [ ] Tổng hợp bảng so sánh toàn diện giữa 7 pipeline

**Deliverable:** bảng kết quả đầy đủ + phân tích lỗi

---

### 🔲 Giai đoạn 5 — Viết báo cáo (Tuần 9+)
**Trạng thái:** ⬜ Chưa bắt đầu

- [ ] Tổng hợp kết quả thành bảng biểu, biểu đồ
- [ ] Viết báo cáo/luận văn (methodology, kết quả, thảo luận, hạn chế)
- [ ] Chuẩn bị slide trình bày
- [ ] Review nội bộ trước khi nộp/bảo vệ

**Deliverable:** báo cáo hoàn chỉnh + slide

---

## 4. Rủi ro & phương án dự phòng

| Rủi ro | Mức độ | Phương án dự phòng |
|---|---|---|
| OCR tiếng Việt lỗi nhiều trên ảnh chất lượng thấp | Cao | Đã có Gold-OCR control để tách lỗi; nếu cần, thêm bước VLM-sửa-lỗi trước LLM |
| FoodOn/OFF thiếu nhãn tiếng Việt → Entity Linking sai nhiều | Cao | Xây từ điển bổ sung nội bộ (VN ↔ FoodOn/OFF ID) cho nguyên liệu phổ biến không có trong KB |
| Annotate dữ liệu tốn thời gian hơn dự kiến | Trung bình | Ưu tiên annotate tập test nhỏ chất lượng cao trước, mở rộng tập train/dev sau nếu còn thời gian |
| Chi phí API LLM/VLM vượt ngân sách | Trung bình | Giới hạn số lượng ảnh test cho V1 (API lớn), ưu tiên chạy local cho các vòng thử nghiệm sơ bộ |
| Không đủ GPU để chạy VLM local (V2) | Thấp/Trung bình | Ưu tiên PaddleOCR-VL (0.9B, chạy được cả CPU) thay vì VLM lớn hơn |

---

## 5. Bảng theo dõi tiến độ tổng thể

| Giai đoạn | Trạng thái | % Hoàn thành | Ghi chú |
|---|---|---|---|
| GĐ0 — Chuẩn bị dữ liệu | ⬜ Chưa bắt đầu | 0% | |
| GĐ1 — P0, P1 | ⬜ Chưa bắt đầu | 0% | |
| GĐ2 — P2, Main | ⬜ Chưa bắt đầu | 0% | |
| GĐ3 — V1, V2 | ⬜ Chưa bắt đầu | 0% | |
| GĐ4 — Đánh giá tổng hợp | ⬜ Chưa bắt đầu | 0% | |
| GĐ5 — Báo cáo | ⬜ Chưa bắt đầu | 0% | |

*Chú thích trạng thái: ⬜ Chưa bắt đầu · 🟡 Đang làm · 🟢 Hoàn thành · 🔴 Bị chặn/trễ*

---

## 6. Nhật ký cập nhật

> Ghi lại mỗi khi có quyết định quan trọng, thay đổi kế hoạch, hoặc mốc hoàn thành.

| Ngày | Nội dung cập nhật |
|---|---|
| 27/09/2026 | Khởi tạo kế hoạch từ đề xuất pipeline đã thống nhất (P0, P1, P2, Main, V1, V2, Gold-OCR control) |
| 27/09/2026 | Chốt taxonomy phân loại đa nhãn: Phụ gia / Dinh dưỡng / Chất gây dị ứng / Phụ gia cần lưu ý liều lượng. Bổ sung task xây bảng ADI (JECFA/Codex) vì FoodOn/OFF không có sẵn nhãn này. Đã cập nhật schema & metric trong `TechnicalSpec_DeTai.md`. |
| 27/09/2026 | Bổ sung mục 8 "Xử lý dữ liệu" vào `TechnicalSpec_DeTai.md` (tiền xử lý ảnh, hậu xử lý text, augmentation, QC, class imbalance, train/test split, tiền xử lý KB, data versioning) và checklist tương ứng vào Giai đoạn 0 của kế hoạch này. |
| | |
