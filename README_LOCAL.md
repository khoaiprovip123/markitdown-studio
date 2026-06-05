# Hướng Dẫn Cài Đặt và Vận Hành MarkItDown Studio (Local)

Tài liệu này hướng dẫn cách thiết lập môi trường và chạy ứng dụng đối chiếu tài liệu **MarkItDown Studio** trực tiếp trên máy tính cá nhân của bạn.

---

## 1. Yêu Cầu Hệ Thống
* **Hệ điều hành**: Windows (đã được cấu hình tối ưu kéo thả).
* **Python**: Phiên bản từ 3.10 trở lên.

---

## 2. Các Bước Cài Đặt Môi Trường

### Bước 2.1: Mở Terminal tại thư mục dự án
Mở PowerShell hoặc Command Prompt tại thư mục `markitdown`.

### Bước 2.2: Kích hoạt môi trường ảo (Virtual Environment)
```powershell
.\.venv\Scripts\Activate.ps1
```

### Bước 2.3: Cài đặt các thư viện bổ trợ (Nếu chưa có)
Chạy lệnh sau để đảm bảo tất cả các thư viện cần thiết (OCR, Âm thanh, PDF, giao diện Web) được cài đặt đầy đủ:
```powershell
pip install flask easyocr pypdfium2 static-ffmpeg pydub SpeechRecognition requests numpy pillow
```

### Bước 2.4: Khởi tạo thư viện FFmpeg (Dành cho xử lý âm thanh)
Ứng dụng sẽ tự động cấu hình đường dẫn FFmpeg khi khởi chạy thông qua thư viện `static_ffmpeg`:
```powershell
python -c "import static_ffmpeg; static_ffmpeg.add_paths()"
```

---

## 3. Khởi Chạy Ứng Dụng

Sau khi kích hoạt môi trường ảo, chạy ứng dụng bằng lệnh:
```powershell
python app.py
```

Khi Terminal hiển thị dòng sau, ứng dụng đã khởi động thành công:
```text
Khởi động server tại http://127.0.0.1:5000
 * Running on http://127.0.0.1:5000
```

Truy cập địa chỉ [http://127.0.0.1:5000](http://127.0.0.1:5000) trên trình duyệt web của bạn.

---

## 4. Các Tính Năng Nổi Bật và Cách Sử Dụng

### 4.1. Chuyển đổi và Đối chiếu Tài liệu
* **Kéo thả trực tiếp**: Kéo file tài liệu của bạn (PDF, Word, Excel, PowerPoint, Ảnh, Audio) thả trực tiếp vào khung **Tài Liệu Gốc** bên trái.
* **Xem trước**: File gốc hiển thị ở bên trái (PDF, ảnh, audio phát trực tiếp). Kết quả Markdown hiển thị ở bên phải.

### 4.2. Thanh Kéo Chia Đôi Màn Hình (Resizer)
* **Kéo thả mượt mà**: Rê chuột vào thanh phân cách giữa hai màn hình và kéo để thay đổi kích thước hiển thị. Tính năng này được tối ưu chống giật lag khi di qua khung PDF.
* **Chia đều 50/50**: Nhấp đúp chuột (Double click) vào thanh phân cách để đưa giao diện về chế độ chia đều màn hình tự động.
* **Cuộn đồng bộ (Sync Scroll)**: Tích chọn ô "Cuộn đồng bộ" trên toolbar để cả hai bên tự động cuộn cùng nhau, giúp dễ so sánh nội dung.

### 4.3. Tìm Kiếm & Highlight Từ Khóa
* Nhập từ khóa cần tìm vào ô tìm kiếm ở thanh công cụ phía trên.
* Kết quả sẽ được tô màu trực tiếp (màu cam/đỏ) trong bản Markdown bên phải.
* Nhấp nút `▲` hoặc `▼` để di chuyển nhanh giữa các vị trí từ khóa tìm được.

### 4.4. Trích Xuất File PDF Scan (Ảnh Quét)
* Hệ thống sẽ tự động phân tích kết quả chuyển đổi. Nếu nhận diện tài liệu là PDF dạng scan (quá ít chữ gốc), ứng dụng sẽ tự động kích hoạt tiến trình OCR tiếng Việt cục bộ (bằng `pypdfium2` và `easyocr`) để bóc tách chữ mà không bị lỗi trang trống.

### 4.5. Chuyển Đổi Âm Thanh (Audio Transcription) Sang Văn Bản
* **Lựa chọn 1 (Miễn phí hoàn toàn)**: Thả file âm thanh trực tiếp vào ứng dụng. File sẽ tự động được chia nhỏ thành các đoạn 1 phút để nhận diện tiếng Việt miễn phí (thông qua Google Speech API), đính kèm mốc thời gian `[phút:giây]`.
* **Lựa chọn 2 (Độ chính xác cao bằng AI)**: Nhập **Gemini API Key** ở góc phải màn hình trước khi tải file âm thanh lên để sử dụng mô hình Gemini 1.5 Flash (chuyên nghiệp và có độ chính xác cao nhất).
