# Project: MarkItDown (Microsoft)

## Overview
MarkItDown là một công cụ Python nhẹ dùng để chuyển đổi các định dạng file khác nhau (PDF, Word, Excel, PowerPoint, v.v.) sang Markdown để sử dụng với LLM và các đường ống phân tích văn bản.

## Tech Stack
- **Ngôn ngữ:** Python 3.10+
- **Kiến trúc:** Monorepo (sử dụng thư mục `packages/`)
- **Dependencies chính:** beautifulsoup4, markdownify, magika, onnxruntime.

## Thiết lập và Chạy
Môi trường ảo đã được thiết lập tại `.venv`.

### Kích hoạt môi trường (PowerShell):
```powershell
.\.venv\Scripts\Activate.ps1
```

### Lệnh chạy chính:
```bash
markitdown <tên_file>
# Ví dụ: markitdown example.pdf -o example.md
```

### Cài đặt bổ sung (nếu cần):
Dự án có nhiều gói bổ trợ trong thư mục `packages/`:
- `packages/markitdown`: Gói lõi (Đã cài đặt).
- `packages/markitdown-mcp`: Gói hỗ trợ Model Context Protocol.
- `packages/markitdown-ocr`: Hỗ trợ OCR.

## Quy ước phát triển
- Sử dụng chế độ cài đặt editable (`pip install -e ...`) cho các gói trong `packages/` để cập nhật code ngay lập tức.
- Tuân thủ các quy tắc bảo mật được nêu trong `SECURITY.md`.

---
*Dự án đã được tự động thiết lập bởi Gemini CLI.*
