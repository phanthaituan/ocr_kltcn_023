Tình trạng hiện tại

Đã xong: có ViFoodLabel (600 ảnh, core subset 521 ảnh), đã parse label, đã có allergen_final, đã gom unique_terms.csv, đã sinh adi_template.csv (168 mã INS).

Chưa xong: nhãn ADI, gold KB, split, OCR benchmark, KB đã chuẩn hóa. Các việc này chia thành 3 luồng làm song song được.

Cần chuẩn bị
Cần chuẩn bị	Dùng cho
Quyết định định nghĩa nhãn ADI (đề xuất: numeric → gán nhãn, not_specified/unknown → không gán)	Luồng A
Truy cập cơ sở dữ liệu JECFA (FAO/WHO) và Codex GSFA để tra ADI	Luồng A
Tải FoodOn (file OWL) và taxonomy Open Food Facts (additives, ingredients, allergens)	Luồng B
Môi trường Python cài sẵn PaddleOCR, VietOCR, EasyOCR, jiwer, sentence-transformers, faiss-cpu	Luồng C và Giai đoạn 1
Git repo + DVC (hoặc Git LFS) để version ảnh, label, bảng ADI	Tất cả
API key LLM/VLM (chỉ cần khi sang Giai đoạn 2-3, chưa gấp)	Sau này
Việc cần làm
Luồng A: nhãn ADI (làm trước, vì chặn việc split)
Chốt định nghĩa nhãn ADI.
Liếc 30 dòng đầu của adi_template.csv, xác nhận các mã INS đúng là phụ gia.
Điền ADI cho khoảng 100 mã đầu (phủ ~95% lượt), ghi nguồn từng dòng. 68 mã còn lại để unknown.
Duyệt additive_no_code.csv: hương liệu đánh unknown, nhận ra chất nào (maltodextrin...) thì ghi tên.
Báo mình để viết script join, tính has_dosage_caution cho 521 ảnh.
Luồng B: Knowledge Base và gold KB
Tải và chuẩn hóa FoodOn + OFF về một format chung (kb_id, nguồn, tên EN/VI, từ đồng nghĩa).
Phần additive: map mã INS sang ID dạng en:e621 của OFF, gần như tự động.
Phần ingredient: so khớp chuỗi đơn giản 1.659 chuỗi với KB, ghi lại % tìm được candidate. Số này cho biết KB đủ dùng hay cần từ điển bổ sung.
Duyệt tay ưu tiên chuỗi tần suất cao để tạo gold KB, gán none khi không có ID phù hợp.
Luồng C: OCR benchmark (độc lập, làm lúc nào cũng được)
Chạy PaddleOCR-VL, VietOCR+PaddleOCR, EasyOCR trên ảnh core subset (có thể thử 50 ảnh trước).
Chấm bằng tỷ lệ chuỗi gold xuất hiện trong output OCR (sau chuẩn hóa NFC, chữ thường), vì labels/ không có chuỗi chữ theo thứ tự đọc nên CER/WER chuẩn không tính được.
Chốt một engine dùng cố định cho P0 đến Main.

Máy bạn (RTX 3060, thường 6GB VRAM) đủ chạy cả 3 engine, chưa cần Kaggle ở giai đoạn này.

Sau khi A hoàn tất
Chốt train/dev/test split trên 521 ảnh, multi-label stratified theo đủ 4 nhãn, split theo sản phẩm. Dev và test mỗi tập khoảng 52 ảnh, nên kiểm tra nhãn ADI có đủ mẫu dương trong hai tập này không.
Dựng từ điển P0/P1 chỉ từ tập train hoặc từ nguồn ngoài, để tránh baseline biết trước đáp án của tập test.
Setup data versioning cho base pool, split, bảng ADI, KB.

Xong các bước này là kết thúc Giai đoạn 0, chuyển sang Giai đoạn 1 (build P0, P1).

Thứ tự ưu tiên

Bắt đầu ngay Luồng A bước 1-3 vì đây là đường găng. Trong lúc tra JECFA, chạy Luồng C ở chế độ nền hoặc làm xen kẽ khi cần nghỉ khỏi việc tra cứu. Luồng B làm sau khi có thời gian, chỉ cần xong trước khi sang Giai đoạn 1.

Việc mình có thể làm giúp ngay
Cập nhật 3 file kế hoạch theo các số liệu thật (600 ảnh, 521 core, 168 mã INS, cơ chế allergen 2 nguồn, nguyên tắc tránh leakage khi dựng từ điển) và sửa schema mục 5.4 sang mức ảnh cho nhãn dị ứng.
Viết script OCR benchmark (chạy 3 engine, tính tỷ lệ phủ chuỗi gold).
Viết script join additive với bảng ADI khi bạn điền xong.

Bạn muốn mình làm việc nào trước?