# KẾ HOẠCH 4 TUẦN (05/10 – 01/11/2026)
## Nhận diện 4 nhóm chất: Dinh dưỡng / Dị ứng / Phụ gia / Phụ gia cần lưu ý

**Cập nhật lần cuối:** 04/10/2026
**Quỹ giờ:** T2–T6: 4h/ngày · T7, CN: 10h+/ngày · Tuần 02–08/11: đệm nộp bài (hạn đề cương 08/11)

> File này là **bản làm việc**: bạn tick `[x]`, đổi ngày, thêm/bớt việc trực tiếp ở đây. Ghi mỗi thay đổi vào "Nhật ký điều chỉnh" cuối file. Khi cần tôi lập lại lịch, nhắn "đọc lại plan". Hai file `KeHoach_ChiTiet_ThucHien.md` và `KeHoach_DeTai.md` còn mô tả bản 7 pipeline/9 tuần, bản này **thay thế** cho phạm vi và lịch trong thời gian còn lại.

---

## Phạm vi đã chốt

| Mục | Quyết định |
|---|---|
| 4 nhóm | Phụ gia · Phụ gia cần lưu ý · Dị ứng · Dinh dưỡng (đa nhãn) |
| Hệ thống so sánh | **Baseline** (=P0), **P2**, **Main**, **V1**. Bỏ P1, V2, Control, Kaggle |
| Dị ứng | Mức **ảnh** (contains + may_contain), duyệt 60 ảnh mẫu, chỉ báo cáo F1 nhóm ≥ 10 ảnh |
| Phụ gia cần lưu ý | `true` nếu JECFA có ADI **số**; `false` nếu "not specified"; `null` nếu chưa tra (loại khỏi đánh giá) |
| Dinh dưỡng | Chất bổ sung vai trò dinh dưỡng (vitamin, khoáng, chất xơ, đạm tách chiết, omega, probiotics). Nguyên liệu nền = `false`. `muối i-ốt` = `true` |
| Baseline | Từ điển lấy từ nguồn ngoài (INS/Codex, từ khóa dị nguyên, OFF), không dựng từ gold |
| Đánh giá | Toàn bộ 521 ảnh core + ~100 ảnh làm xấu + 30–50 ảnh tự chụp |
| Cải tiến (yêu cầu đề cương) | Tiền xử lý ảnh thích nghi + LLM re-rank cho Entity Linking, đo bằng ablation Baseline → P2 → Main |

**Cần chốt sớm:** LLM/VLM provider + ngân sách (trước T2 19/10) · các bạn còn lại có làm cùng không?

---

## TUẦN 1 (05–11/10): Dữ liệu nhãn + OCR
**Mốc:** `gold_categories/` đủ 521 file · ≥ 100 mã ADI có `source` · OCR engine đã chốt · FoodOn/OFF đã parse

- [ ] **T2 05/10 (4h):** `git config` + commit đầu · guideline 4 nhãn (`AnnotationGuideline.md`) · parser mã INS (`src/common/ins.py`)
- [ ] **T3 06/10 (4h):** `build_term_labels.py` → `gold_term_labels.csv` (3.094 dòng)
- [ ] **T4 07/10 (4h):** `validate_adi.py` · nhập ADI top 50
- [ ] **T5 08/10 (4h):** nhập ADI 51–100 · hương liệu = `unknown`
- [ ] **T6 09/10 (4h):** duyệt `is_nutritional` theo tần suất giảm dần (phủ ≥ 80% lượt)
- [ ] **T7 10/10 (10h):** `build_gold_categories.py` · benchmark OCR 3 engine trên 50 ảnh (chạy nền) · duyệt 60 ảnh mẫu dị ứng
- [ ] **CN 11/10 (10h):** chốt OCR engine · OCR cache 521 ảnh (nền) · tải FoodOn + OFF, `build_kb.py`

## TUẦN 2 (12–18/10): Tiền xử lý, Entity Linking, Baseline
**Mốc:** có bảng P/R/F1 của Baseline · FAISS top-5 đúng ≥ 70% term mẫu

- [ ] **T2 12/10 (4h):** `preprocess.py` (CLAHE, deskew, denoise)
- [ ] **T3 13/10 (4h):** `text_clean.py` (NFC, lọc nhiễu) · tách vùng "Thành phần"
- [ ] **T4 14/10 (4h):** benchmark embedding (bge-m3 / e5 / LaBSE) trên 300 term · build FAISS
- [ ] **T5 15/10 (4h):** `linker.py` · `gold_kb_links` bán tự động top 200 term
- [ ] **T6 16/10 (4h):** Baseline (`baseline.py`)
- [ ] **T7 17/10 (10h):** mã đánh giá (P/R/F1 từng nhãn, Macro-F1, Acc@1, Recall@5) · chạy Baseline 521 ảnh
- [ ] **CN 18/10 (10h):** chụp 30–50 ảnh thật · script làm xấu 100 ảnh · prompt LLM v1

## TUẦN 3 (19–25/10): LLM, Main, P2, V1
**Mốc (cut-line):** có P/R/F1 cho Baseline, P2, Main, V1

- [ ] **T2 19/10 (4h):** chốt LLM provider · schema Pydantic · thử 20 ảnh, ước chi phí
- [ ] **T3 20/10 (4h):** LLM chuẩn hóa + phân loại 4 nhãn (`normalizer.py`)
- [ ] **T4 21/10 (4h):** LLM re-rank EL · tra ADI/dị nguyên
- [ ] **T5 22/10 (4h):** ghép Main + P2 · debug 40 ảnh
- [ ] **T6 23/10 (4h):** V1 (VLM API, cùng schema)
- [ ] **T7 24/10 (10h):** chạy full 521 ảnh cho P2, Main, V1 (theo lô, retry, log chi phí)
- [ ] **CN 25/10 (10h):** 100 ảnh làm xấu × (có/không tiền xử lý) · 30–50 ảnh thật · ablation

## TUẦN 4 (26/10–01/11): Phân tích, giao diện, báo cáo
**Mốc:** demo chạy với ảnh mới · báo cáo gần hoàn chỉnh

- [ ] **T2 26/10 (4h):** tổng hợp bảng kết quả, biểu đồ
- [ ] **T3 27/10 (4h):** phân tích lỗi (OCR/LLM/EL/ADI)
- [ ] **T4 28/10 (4h):** giao diện Streamlit/Gradio
- [ ] **T5 29/10 (4h):** hoàn thiện demo, thử ảnh thật
- [ ] **T6 30/10 (4h):** báo cáo: Mô tả dữ liệu + Phương pháp
- [ ] **T7 31/10 (10h):** báo cáo: Thực nghiệm, Kết quả, Thảo luận, Hạn chế
- [ ] **CN 01/11 (10h):** slide · rà soát · đối chiếu thang điểm đề cương

## ĐỆM (02–08/11)
- [ ] Sửa theo góp ý GVHD · tập trình bày · nộp

---

## Cắt giảm khi trễ (không cắt Main)

| Khi nào | Cắt gì |
|---|---|
| Trễ cuối Tuần 1 | ADI chỉ top 50 · duyệt dinh dưỡng chỉ term tần suất cao |
| Trễ cuối Tuần 2 | Bỏ benchmark 3 embedding, chọn `bge-m3` · Baseline chạy 200 ảnh |
| Trễ giữa Tuần 3 | Bỏ V1 (hoặc chạy 150 ảnh) |
| Trễ cuối Tuần 3 | Chỉ so Baseline, P2, Main · ảnh làm xấu giảm còn 50 |
| Trễ Tuần 4 | Giao diện tối giản (upload + bảng kết quả) |

## Quy tắc làm việc
- Ngày thường: việc cần tập trung, kết thúc bằng thứ chạy được. Cuối tuần: chạy dài + tích hợp, làm việc thủ công khi máy chạy nền.
- Cache OCR một lần cho 521 ảnh, mọi hệ thống dùng chung.
- Cuối ngày ghi 15 phút quyết định/số liệu. Commit mỗi tối.

## Nhật ký điều chỉnh

| Ngày | Thay đổi | Lý do |
|---|---|---|
| 04/10/2026 | Khởi tạo bản 4 tuần, thu hẹp từ 7 xuống 4 hệ thống | Còn 4 tuần, nhãn thu hẹp còn 4 nhóm |
| | | |
