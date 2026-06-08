import os
import sys
import time
import requests

# Initialize static_ffmpeg so pydub can find the binary on Windows
try:
    import static_ffmpeg

    static_ffmpeg.add_paths()
    print("Static FFmpeg initialized successfully.")
except Exception as e:
    print(f"Không thể khởi tạo static_ffmpeg: {e}")

from flask import Flask, request, jsonify, render_template, send_from_directory


def get_base_path():
    if hasattr(sys, "_MEIPASS"):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))


base_path = get_base_path()

VERSION = "1.0.0"
REPO_OWNER = "khoaiprovip123"
REPO_NAME = "markitdown-studio"


def check_for_updates():
    try:
        url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "MarkItDown-Studio-App",
        }
        response = requests.get(url, headers=headers, timeout=5)
        if response.status_code == 200:
            data = response.json()
            latest_version = data.get("tag_name", "").lstrip("v")
            if latest_version and latest_version != VERSION:
                assets = data.get("assets", [])
                download_url = None
                for asset in assets:
                    name = asset.get("name", "").lower()
                    if name.endswith(".zip") or name.endswith(".exe"):
                        download_url = asset.get("browser_download_url")
                        break
                return {
                    "update_available": True,
                    "current_version": VERSION,
                    "latest_version": latest_version,
                    "download_url": download_url,
                    "release_notes": data.get("body", ""),
                }
    except Exception as e:
        print(f"Lỗi kiểm tra cập nhật: {e}")
    return {"update_available": False, "current_version": VERSION}


# Ensure packages directory is in sys.path so we can import markitdown
sys.path.insert(0, os.path.join(base_path, "packages", "markitdown"))
sys.path.insert(0, os.path.join(base_path, "packages", "markitdown", "src"))

try:
    from markitdown import MarkItDown
except ImportError:
    try:
        from markitdown.markitdown import MarkItDown
    except ImportError:
        import markitdown
        from markitdown import MarkItDown

app = Flask(
    __name__,
    template_folder=os.path.join(base_path, "templates"),
    static_folder=os.path.join(base_path, "static"),
)

# Uploads thư mục nằm cạnh file exe hoặc file script gốc
if hasattr(sys, "_MEIPASS"):
    executable_dir = os.path.dirname(sys.executable)
    UPLOAD_FOLDER = os.path.join(executable_dir, "uploads")
else:
    UPLOAD_FOLDER = os.path.join(base_path, "uploads")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

if hasattr(sys, "_MEIPASS"):
    executable_dir = os.path.dirname(sys.executable)
    CONFIG_FILE_PATH = os.path.join(executable_dir, "config.json")
else:
    CONFIG_FILE_PATH = os.path.join(base_path, "config.json")


def load_settings_file():
    import json

    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_settings_file(data):
    import json

    try:
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception:
        return False


markitdown_client = MarkItDown()
ocr_reader = None


def get_ocr_reader():
    global ocr_reader
    if ocr_reader is None:
        try:
            import easyocr

            print("Dang tai/khoi tao model EasyOCR (vi, en)...")
            ocr_reader = easyocr.Reader(["vi", "en"])
            print("Khoi tao EasyOCR thanh cong.")
        except Exception as e:
            print(f"Khong the khoi tao EasyOCR: {e}")
    return ocr_reader


import uuid
import threading

conversion_tasks = {}


def transcribe_audio_free_local_with_progress(file_path, task_id):
    import speech_recognition as sr
    from pydub import AudioSegment
    from pydub.effects import normalize
    from pydub.silence import detect_nonsilent
    import tempfile

    sound = AudioSegment.from_file(file_path)

    try:
        sound = normalize(sound)
    except Exception:
        pass

    sound = sound.set_frame_rate(16000).set_channels(1)

    duration_ms = len(sound)
    dbfs = sound.dBFS
    silence_thresh = max(dbfs - 16, -45)

    ranges = []
    try:
        ranges = detect_nonsilent(
            sound, min_silence_len=900, silence_thresh=silence_thresh
        )
    except Exception as e:
        print(f"Lỗi khi chạy detect_nonsilent: {e}")

    chunks_to_process = []
    if ranges:
        current_start = None
        current_end = None
        max_chunk_duration = 35000  # 35 seconds max

        for start, end in ranges:
            if current_start is None:
                current_start = start
                current_end = end
            else:
                if end - current_start > max_chunk_duration:
                    pad_start = max(0, current_start - 300)
                    pad_end = min(duration_ms, current_end + 300)
                    chunks_to_process.append((pad_start, sound[pad_start:pad_end]))
                    current_start = start
                    current_end = end
                else:
                    current_end = end
        if current_start is not None:
            pad_start = max(0, current_start - 300)
            pad_end = min(duration_ms, current_end + 300)
            chunks_to_process.append((pad_start, sound[pad_start:pad_end]))
    else:
        # Fallback to fixed interval if no ranges detected
        chunk_length_ms = 30000
        overlap_ms = 3000
        start = 0
        while start < duration_ms:
            end = min(start + chunk_length_ms, duration_ms)
            chunks_to_process.append((start, sound[start:end]))
            start += chunk_length_ms - overlap_ms

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True

    full_transcript = []
    total_chunks = len(chunks_to_process)

    conversion_tasks[task_id].update(
        {
            "total_chunks": total_chunks,
            "current_chunk": 0,
            "progress": 0,
            "message": f"ĐANG GỠ BĂNG (Tổng số: {total_chunks} phân đoạn)...",
        }
    )

    has_adjusted = False

    for idx, (start_ms, chunk) in enumerate(chunks_to_process):
        if conversion_tasks[task_id].get("status") == "failed":
            raise Exception("Tác vụ đã bị hủy bởi người dùng.")
        current_num = idx + 1
        progress = int((current_num / total_chunks) * 100)
        conversion_tasks[task_id].update(
            {
                "current_chunk": current_num,
                "progress": progress,
                "message": f"Đang gỡ băng... (Phân đoạn {current_num}/{total_chunks})",
            }
        )

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_path = tmp_file.name
        try:
            chunk.export(tmp_path, format="wav")
            with sr.AudioFile(tmp_path) as source:
                if not has_adjusted:
                    recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    has_adjusted = True
                audio_data = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio_data, language="vi-VN")
                    if text.strip():
                        start_sec = start_ms // 1000
                        minutes = start_sec // 60
                        seconds = start_sec % 60
                        timestamp = f"[{minutes:02d}:{seconds:02d}]"
                        full_transcript.append(f"{timestamp} {text}")
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    raise Exception(f"Lỗi kết nối dịch vụ Google Speech: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    if not full_transcript:
        return "Không nhận diện được giọng nói trong tệp âm thanh này bằng phương thức offline miễn phí."

    return "\n\n".join(full_transcript)


def ocr_pdf_via_easyocr_with_progress(file_path, task_id):
    import pypdfium2 as pdfium
    import numpy as np

    reader = get_ocr_reader()
    if reader is None:
        raise Exception("Không thể khởi tạo OCR Reader (EasyOCR).")

    pdf = pdfium.PdfDocument(file_path)
    total_pages = len(pdf)
    ocr_pages = []

    conversion_tasks[task_id].update(
        {
            "total_chunks": total_pages,
            "current_chunk": 0,
            "progress": 0,
            "message": f"Phát hiện PDF quét. Bắt đầu OCR (Tổng số: {total_pages} trang)...",
        }
    )

    for i, page in enumerate(pdf):
        if conversion_tasks[task_id].get("status") == "failed":
            raise Exception("Tác vụ đã bị hủy bởi người dùng.")
        current_num = i + 1
        progress = int((current_num / total_pages) * 100)
        conversion_tasks[task_id].update(
            {
                "current_chunk": current_num,
                "progress": progress,
                "message": f"Đang nhận diện chữ... (Trang {current_num}/{total_pages})",
            }
        )

        pil_img = page.render(scale=2).to_pil()
        img_np = np.array(pil_img)
        results = reader.readtext(img_np, paragraph=False)
        page_text = sort_ocr_results_smart(results)

        if page_text.strip():
            ocr_pages.append(f"## Trang {i+1}\n\n{page_text}")
        else:
            ocr_pages.append(
                f"## Trang {i+1}\n\n*(Trang trống hoặc không nhận diện được chữ)*"
            )

    return "\n\n".join(ocr_pages)


def ocr_base64_images_in_markdown(markdown_text, task_id=None):
    import re
    import base64
    import io
    import numpy as np
    from PIL import Image

    pattern = (
        r"!\[(.*?)\]\(data:image\/([a-zA-Z0-9+.-]+);base64,([a-zA-Z0-9+/=\s\r\n]+?)\)"
    )
    matches = list(re.finditer(pattern, markdown_text))

    if not matches:
        return markdown_text

    reader = get_ocr_reader()
    if reader is None:
        return markdown_text

    new_markdown = markdown_text
    total_imgs = len(matches)

    if task_id and task_id in conversion_tasks:
        conversion_tasks[task_id].update(
            {
                "total_chunks": total_imgs,
                "current_chunk": 0,
                "message": f"Phát hiện {total_imgs} hình ảnh nhúng. Bắt đầu OCR...",
            }
        )

    for idx, match in enumerate(matches):
        if task_id and conversion_tasks.get(task_id, {}).get("status") == "failed":
            break

        alt_text = match.group(1)
        img_format = match.group(2)
        base64_data = (
            match.group(3).replace("\r", "").replace("\n", "").replace(" ", "")
        )

        if task_id and task_id in conversion_tasks:
            conversion_tasks[task_id].update(
                {
                    "current_chunk": idx + 1,
                    "progress": int(((idx + 1) / total_imgs) * 100),
                    "message": f"Đang OCR hình ảnh {idx + 1}/{total_imgs}...",
                }
            )

        try:
            img_bytes = base64.b64decode(base64_data)
            pil_img = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            img_np = np.array(pil_img)

            results = reader.readtext(img_np, paragraph=False)
            ocr_text = sort_ocr_results_smart(results)

            if ocr_text.strip():
                replacement = f"\n\n*[Hình ảnh OCR - {alt_text or 'Không có tiêu đề'}]:\n{ocr_text}\n[Hết OCR]*\n\n"
            else:
                replacement = f"\n\n*[Hình ảnh - {alt_text or 'Không có tiêu đề'} (Không phát hiện chữ)]*\n\n"
        except Exception as e:
            print(f"Lỗi OCR ảnh nhúng thứ {idx+1}: {e}")
            replacement = f"\n\n*[Hình ảnh - {alt_text or 'Không có tiêu đề'} (Lỗi OCR: {str(e)})]*\n\n"

        raw_match_str = match.group(0)
        new_markdown = new_markdown.replace(raw_match_str, replacement)

    return new_markdown


def async_convert_worker(
    task_id, file_path, ext, gemini_key, docintel_endpoint, cu_endpoint, filename
):
    try:
        client_kwargs = {}
        if docintel_endpoint:
            client_kwargs["docintel_endpoint"] = docintel_endpoint
        if cu_endpoint:
            client_kwargs["cu_endpoint"] = cu_endpoint
        local_client = (
            MarkItDown(**client_kwargs) if client_kwargs else markitdown_client
        )

        # 1. AUDIO FILES
        if ext in ["mp3", "wav", "m4a", "mp4"]:
            if gemini_key:
                conversion_tasks[task_id].update(
                    {"message": "Đang tải tệp lên Gemini AI...", "progress": 30}
                )
                markdown_content = transcribe_audio_via_gemini(
                    file_path, gemini_key, ext
                )
                markdown_content = (
                    f"# Kết Quả Trích Xuất Lời Thoại (Gemini AI)\n\n" + markdown_content
                )
                conversion_tasks[task_id]["progress"] = 100
            else:
                markdown_content = transcribe_audio_free_local_with_progress(
                    file_path, task_id
                )

        # 2. IMAGE FILES (OCR)
        elif ext in ["png", "jpg", "jpeg"]:
            conversion_tasks[task_id].update(
                {"message": "Đang khởi động EasyOCR...", "progress": 10}
            )
            reader = get_ocr_reader()
            if reader is not None:
                conversion_tasks[task_id].update(
                    {
                        "message": "Đang tiến hành trích xuất OCR tiếng Việt...",
                        "progress": 50,
                    }
                )
                results = reader.readtext(file_path, paragraph=False)
                markdown_content = sort_ocr_results_smart(results)
                if not markdown_content.strip():
                    markdown_content = "# Kết Quả Trích Xuất Chữ (OCR)\n\nKhông tìm thấy chữ nào trong hình ảnh này."
                else:
                    markdown_content = (
                        "# Kết Quả Trích Xuất Chữ (OCR)\n\n" + markdown_content
                    )
                conversion_tasks[task_id]["progress"] = 100
            else:
                markdown_content = local_client.convert(
                    file_path, keep_data_uris=True
                ).text_content
                if not markdown_content.strip():
                    markdown_content = (
                        "# Kết Quả\n\nKhông trích xuất được thông tin từ hình ảnh."
                    )
                conversion_tasks[task_id]["progress"] = 100

        # 3. OTHER DOCUMENTS (PDF, Word, Excel, etc.)
        else:
            conversion_tasks[task_id].update(
                {"message": "Đang đọc và phân tích tài liệu...", "progress": 20}
            )
            result = local_client.convert(file_path, keep_data_uris=True)
            markdown_content = result.text_content

            # Check for scanned PDF
            if ext == "pdf":
                cleaned_text = "".join(c for c in markdown_content if c.isalnum())
                if len(cleaned_text) < 150:
                    try:
                        ocr_content = ocr_pdf_via_easyocr_with_progress(
                            file_path, task_id
                        )
                        markdown_content = (
                            f"# Kết Quả Trích Xuất PDF (OCR Tự Động)\n\n> **Lưu ý**: Tài liệu này được xác định là ảnh quét (Scanned PDF). Hệ thống đã tự động chạy EasyOCR tiếng Việt để trích xuất nội dung.\n\n"
                            + ocr_content
                        )
                    except Exception as ocr_err:
                        markdown_content += f"\n\n> **Lưu ý**: Tài liệu này có vẻ là PDF dạng quét (Scanned PDF) nhưng lỗi khi chạy OCR: {str(ocr_err)}"
            elif ext in ["docx", "pptx", "xlsx"]:
                try:
                    markdown_content = ocr_base64_images_in_markdown(
                        markdown_content, task_id
                    )
                except Exception as img_ocr_err:
                    print(f"Lỗi khi OCR ảnh nhúng trong tài liệu: {img_ocr_err}")

            conversion_tasks[task_id]["progress"] = 100

        conversion_tasks[task_id].update(
            {
                "status": "completed",
                "progress": 100,
                "markdown": markdown_content,
                "preview_url": f"/uploads/{filename}",
            }
        )
    except Exception as e:
        import traceback

        traceback.print_exc()
        conversion_tasks[task_id].update({"status": "failed", "error": str(e)})


def sort_ocr_results_smart(results):
    if not results:
        return ""

    items = []
    for item in results:
        try:
            if len(item) == 3:
                box, text, conf = item
            elif len(item) == 2:
                box, text = item
            else:
                continue
            text = text.strip()
            if not text:
                continue
            xs = [p[0] for p in box]
            ys = [p[1] for p in box]
            left, right = min(xs), max(xs)
            top, bottom = min(ys), max(ys)
            height = bottom - top
            items.append(
                {
                    "left": left,
                    "top": top,
                    "right": right,
                    "bottom": bottom,
                    "height": height,
                    "text": text,
                }
            )
        except Exception:
            continue

    if not items:
        return ""

    # --- Bước 2: Nhóm theo dòng (Y-overlap) ---
    items.sort(key=lambda x: x["top"])
    lines = []
    for item in items:
        placed = False
        for line in lines:
            line_top = min(x["top"] for x in line)
            line_bottom = max(x["bottom"] for x in line)
            line_height = line_bottom - line_top
            overlap_top = max(item["top"], line_top)
            overlap_bottom = min(item["bottom"], line_bottom)
            if overlap_bottom > overlap_top:  # có overlap dọc
                overlap_ratio = (overlap_bottom - overlap_top) / max(
                    item["height"], line_height, 1
                )
                if overlap_ratio > 0.4:  # overlap >= 40% -> cùng dòng
                    line.append(item)
                    placed = True
                    break
        if not placed:
            lines.append([item])

    # Sort từng dòng theo X
    for line in lines:
        line.sort(key=lambda x: x["left"])

    # Sort các dòng theo top
    lines.sort(key=lambda line: min(x["top"] for x in line))

    output_lines = []
    for line in lines:
        line_text = " ".join(x["text"] for x in line)
        output_lines.append(line_text)

    # --- Bước 5: Post-process thành Markdown ---
    return postprocess_ocr_to_markdown(output_lines)


def postprocess_ocr_to_markdown(lines):
    """
    Chuyển danh sách text lines thô từ OCR thành Markdown cấu trúc quiz hoàn hảo:
    - Gộp các dòng text bị ngắt quãng (dòng tiếp theo bắt đầu bằng chữ thường)
    - Loại bỏ UI noise điện thoại
    - Định dạng câu hỏi (bold)
    - Định dạng hướng dẫn (italic)
    - Định dạng đáp án/checkbox (danh sách checkbox - [ ])
    """
    import re

    # Patterns loại bỏ artifacts UI điện thoại
    ui_noise_patterns = [
        r"^\d{1,2}:\d{2}",  # giờ: 09:29
        r"^[\d]{1,3}%$",  # pin %
        r"^[·•·⋅\*]{1,5}$",  # signal dots
        r"^[\↑↓⬆⬇⬛●○◉]{1,3}$",  # icons
        r"^\d+\s*[↑↓]\s*\d*$",  # network speed
        r"(?i)^wifi",  # wifi text
        r'^"\s*\?',  # rác phổ biến
        r"^[\W_]+$",  # chỉ có ký tự đặc biệt
    ]

    # 1. Lọc noise trước
    cleaned_lines = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        is_noise = False
        for pat in ui_noise_patterns:
            if re.match(pat, line):
                is_noise = True
                break
        if is_noise:
            continue
        cleaned_lines.append(line)

    # 2. Gộp các dòng bị xuống dòng nửa chừng (khi dòng tiếp theo bắt đầu bằng chữ thường hoặc dấu câu)
    merged_lines = []
    for line in cleaned_lines:
        if merged_lines and (
            line[0].islower() or (line[0] in ".,)?:" and not line.startswith("..."))
        ):
            merged_lines[-1] = merged_lines[-1] + " " + line
        else:
            merged_lines.append(line)

    # 3. Định dạng Markdown
    md_lines = []
    for line in merged_lines:
        # Câu hỏi: bắt đầu bằng số (ví dụ: "3. Bạn nên...")
        q_match = re.match(r"^(\d{1,3})[.\)\-]?\s+(.+)", line)
        if q_match:
            num, content = q_match.groups()
            md_lines.append(f"\n\n**{num}. {content}**\n")
            continue

        # Đáp án/Hướng dẫn dạng standalone
        if re.match(
            r"^(Đúng|Sai|True|False|Chọn một\.|Chọn một|Chọn hai\.|Chọn hai|Điền vào chỗ trống\.?)$",
            line,
            re.IGNORECASE,
        ):
            md_lines.append(f"\n*{line}*\n")
            continue

        # Checkbox/Radio button
        # Nếu dòng đã có định dạng danh sách thì giữ nguyên
        if re.match(r"^[\s]*[-*+]\s+", line) or re.match(r"^[\s]*\d+\.\s+", line):
            md_lines.append(line)
        else:
            # Clean các ký tự circle/square của OCR nếu còn sót lại ở đầu dòng
            clean = re.sub(r"^[\s]*[☐□▢▣◻◼⬜⬛✗O◯○☑✓✔☒✅✗✘●◉■▪xX]\s*", "", line).strip()
            md_lines.append(f"- [ ] {clean}")

    return "\n".join(md_lines)


def ocr_pdf_via_easyocr(file_path):
    import pypdfium2 as pdfium
    import numpy as np

    reader = get_ocr_reader()
    if reader is None:
        raise Exception("Không thể khởi tạo OCR Reader (EasyOCR).")

    pdf = pdfium.PdfDocument(file_path)
    ocr_pages = []

    for i, page in enumerate(pdf):
        print(f"Dang chay OCR trang {i+1}/{len(pdf)}...")
        # Render page to PIL image
        pil_img = page.render(scale=2).to_pil()
        # Convert PIL image to numpy array
        img_np = np.array(pil_img)
        # Run EasyOCR
        results = reader.readtext(img_np, paragraph=False)
        page_text = sort_ocr_results_smart(results)

        if page_text.strip():
            ocr_pages.append(f"## Trang {i+1}\n\n{page_text}")
        else:
            ocr_pages.append(
                f"## Trang {i+1}\n\n*(Trang trống hoặc không nhận diện được chữ)*"
            )

    return "\n\n".join(ocr_pages)


def transcribe_audio_free_local(file_path):
    import speech_recognition as sr
    from pydub import AudioSegment
    from pydub.effects import normalize
    from pydub.silence import detect_nonsilent
    import tempfile

    sound = AudioSegment.from_file(file_path)

    # 1. TĂNG CƯỜNG ÂM THANH (AUDIO ENHANCEMENT):
    try:
        sound = normalize(sound)
        print(
            "Da tu dong tang cuong va chuan hoa am luong (Normalize) cho file am thanh."
        )
    except Exception as norm_err:
        print(f"Khong the chuan hoa am luong: {norm_err}")

    sound = sound.set_frame_rate(16000).set_channels(1)

    duration_ms = len(sound)
    dbfs = sound.dBFS
    silence_thresh = max(dbfs - 16, -45)

    ranges = []
    try:
        ranges = detect_nonsilent(
            sound, min_silence_len=900, silence_thresh=silence_thresh
        )
    except Exception as e:
        print(f"Lỗi khi chạy detect_nonsilent: {e}")

    chunks_to_process = []
    if ranges:
        current_start = None
        current_end = None
        max_chunk_duration = 35000  # 35 seconds max

        for start, end in ranges:
            if current_start is None:
                current_start = start
                current_end = end
            else:
                if end - current_start > max_chunk_duration:
                    pad_start = max(0, current_start - 300)
                    pad_end = min(duration_ms, current_end + 300)
                    chunks_to_process.append((pad_start, sound[pad_start:pad_end]))
                    current_start = start
                    current_end = end
                else:
                    current_end = end
        if current_start is not None:
            pad_start = max(0, current_start - 300)
            pad_end = min(duration_ms, current_end + 300)
            chunks_to_process.append((pad_start, sound[pad_start:pad_end]))
    else:
        # Fallback to fixed interval if no ranges detected
        chunk_length_ms = 30000
        overlap_ms = 3000
        start = 0
        while start < duration_ms:
            end = min(start + chunk_length_ms, duration_ms)
            chunks_to_process.append((start, sound[start:end]))
            start += chunk_length_ms - overlap_ms

    recognizer = sr.Recognizer()
    recognizer.dynamic_energy_threshold = True

    full_transcript = []
    has_adjusted = False

    for idx, (start_ms, chunk) in enumerate(chunks_to_process):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_path = tmp_file.name
        try:
            chunk.export(tmp_path, format="wav")
            with sr.AudioFile(tmp_path) as source:
                if not has_adjusted:
                    recognizer.adjust_for_ambient_noise(source, duration=0.5)
                    has_adjusted = True
                audio_data = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio_data, language="vi-VN")
                    if text.strip():
                        start_sec = start_ms // 1000
                        minutes = start_sec // 60
                        seconds = start_sec % 60
                        timestamp = f"[{minutes:02d}:{seconds:02d}]"
                        full_transcript.append(f"{timestamp} {text}")
                except sr.UnknownValueError:
                    pass
                except sr.RequestError as e:
                    raise Exception(f"Lỗi kết nối dịch vụ Google Speech: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

    if not full_transcript:
        return "Không nhận diện được giọng nói trong file âm thanh này bằng phương thức offline miễn phí."

    return "\n\n".join(full_transcript)


def transcribe_audio_via_gemini(file_path, api_key, ext):
    # Mapping extension to standard mime type
    mime_map = {
        "mp3": "audio/mp3",
        "wav": "audio/wav",
        "m4a": "audio/m4a",
        "mp4": "video/mp4",
    }
    mime_type = mime_map.get(ext, "application/octet-stream")
    file_size = os.path.getsize(file_path)
    display_name = os.path.basename(file_path)

    # 1. Start Resumable Upload session
    upload_url_init = (
        f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
    )
    headers_init = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json",
    }
    body_init = {"file": {"display_name": display_name}}

    print(f"Bat dau upload file {display_name} len Gemini API...")
    res_init = requests.post(upload_url_init, headers=headers_init, json=body_init)
    if res_init.status_code != 200:
        raise Exception(f"Không thể khởi tạo session upload Gemini: {res_init.text}")

    upload_url = res_init.headers.get("Upload-Url")
    if not upload_url:
        raise Exception("Không lấy được Upload-Url từ Gemini API.")

    # 2. Upload file bytes
    headers_upload = {
        "Content-Length": str(file_size),
        "X-Goog-Upload-Offset": "0",
        "X-Goog-Upload-Command": "upload, finalize",
    }

    with open(file_path, "rb") as f:
        res_upload = requests.put(upload_url, headers=headers_upload, data=f)

    if res_upload.status_code != 200:
        raise Exception(f"Upload file lên Gemini thất bại: {res_upload.text}")

    file_info = res_upload.json().get("file")
    file_uri = file_info.get("uri")
    file_name = file_info.get("name")

    try:
        # Wait 3 seconds for processing
        print("File da upload. Cho model xu ly transcript...")
        time.sleep(3)

        # 3. Transcribe via gemini-1.5-flash
        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
        body_generate = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": "Hãy nghe file âm thanh cuộc họp này và trích xuất lại toàn bộ lời thoại (transcribe) sang văn bản tiếng Việt một cách chi tiết và chính xác nhất, có phân chia theo mốc thời gian hoặc người nói (nếu có thể nhận dạng được)."
                        },
                        {"fileData": {"fileUri": file_uri, "mimeType": mime_type}},
                    ]
                }
            ]
        }

        res_generate = requests.post(gemini_url, json=body_generate)
        if res_generate.status_code != 200:
            raise Exception(f"Lỗi gọi model Gemini: {res_generate.text}")

        content_resp = res_generate.json()
        text_result = content_resp["candidates"][0]["content"]["parts"][0]["text"]
        return text_result
    finally:
        # 4. Clean up file on cloud
        try:
            delete_url = f"https://generativelanguage.googleapis.com/v1beta/{file_name}?key={api_key}"
            requests.delete(delete_url)
            print("Da xoa file tam tren cloud Gemini.")
        except Exception as e:
            print(f"Lỗi xóa file tạm: {e}")


@app.route("/api/config", methods=["GET", "POST"])
def handle_config():
    if request.method == "POST":
        data = request.get_json() or {}
        if save_settings_file(data):
            return jsonify({"success": True})
        return jsonify({"error": "Không thể ghi tệp cấu hình."}), 500
    else:
        return jsonify(load_settings_file())


@app.route("/")
def index():
    return render_template("index.html", version=VERSION)


@app.route("/convert", methods=["POST"])
def convert_file():
    if "file" not in request.files:
        return jsonify({"error": "Không tìm thấy file gửi lên."}), 400
    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Chưa chọn file."}), 400

    file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(file_path)

    ext = file.filename.split(".")[-1].lower()
    gemini_key = request.headers.get("X-Gemini-Key")
    docintel_endpoint = request.headers.get("X-DocIntel-Endpoint")
    cu_endpoint = request.headers.get("X-CU-Endpoint")

    server_config = load_settings_file()
    if not gemini_key:
        gemini_key = server_config.get("gemini_api_key")
    if not docintel_endpoint:
        docintel_endpoint = server_config.get("docintel_endpoint")
    if not cu_endpoint:
        cu_endpoint = server_config.get("cu_endpoint")

    task_id = str(uuid.uuid4())
    conversion_tasks[task_id] = {
        "status": "processing",
        "progress": 0,
        "message": "Đang chuẩn bị xử lý tệp...",
        "filename": file.filename,
        "total_chunks": 0,
        "current_chunk": 0,
    }

    thread = threading.Thread(
        target=async_convert_worker,
        args=(
            task_id,
            file_path,
            ext,
            gemini_key,
            docintel_endpoint,
            cu_endpoint,
            file.filename,
        ),
    )
    thread.daemon = True
    thread.start()

    return jsonify({"task_id": task_id, "filename": file.filename})


@app.route("/task_status/<task_id>", methods=["GET", "POST"])
def task_status(task_id):
    task = conversion_tasks.get(task_id)
    if not task:
        return jsonify({"error": "Không tìm thấy tác vụ."}), 404

    if request.method == "POST":
        data = request.get_json() or {}
        action = data.get("action")
        if action == "cancel":
            task["status"] = "failed"
            task["error"] = "Đã hủy bởi người dùng"
            return jsonify({"success": True, "message": "Tác vụ đã được hủy."})

    return jsonify(task)


def get_yt_transcript_via_ytdlp(video_id):
    import yt_dlp
    import os
    import glob
    import re
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        ydl_opts = {
            "writesubtitles": True,
            "writeautomaticsub": True,
            "skip_download": True,
            "outtmpl": os.path.join(temp_dir, "%(id)s"),
            "subtitlesformat": "vtt",
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
            except Exception as e:
                print(f"Download subtitles failed: {e}")
                return None

        files = glob.glob(os.path.join(temp_dir, f"{video_id}.*"))
        if not files:
            return None

        sub_file = None
        for lang in [".vi.vtt", ".en.vtt"]:
            for f in files:
                if f.endswith(lang):
                    sub_file = f
                    break
            if sub_file:
                break
        if not sub_file:
            sub_file = files[0]

        with open(sub_file, "r", encoding="utf-8") as f:
            content = f.read()

        lines = []
        blocks = content.split("\n\n")
        for block in blocks:
            block = block.strip()
            if (
                not block
                or block.startswith("WEBVTT")
                or block.startswith("Kind:")
                or block.startswith("Language:")
            ):
                continue
            block_lines = block.split("\n")
            if len(block_lines) > 1 and "-->" in block_lines[0]:
                text_lines = block_lines[1:]
            else:
                text_lines = block_lines
            for line in text_lines:
                line = re.sub(r"<[^>]+>", "", line)
                line = line.strip()
                if line and (not lines or lines[-1] != line):
                    lines.append(line)
        return " ".join(lines)


@app.route("/convert_url", methods=["POST"])
def convert_url():
    data = request.get_json()
    url = data.get("url")
    if not url:
        return jsonify({"error": "Không tìm thấy URL."}), 400

    docintel_endpoint = request.headers.get("X-DocIntel-Endpoint")
    cu_endpoint = request.headers.get("X-CU-Endpoint")

    # Chuẩn hóa URL YouTube nếu có dạng uppercase hoặc viết tắt
    import re

    yt_pattern = r"(?:https?://)?(?:[a-zA-Z0-9-]+\.)?(?:youtube\.com/(?:watch\?v=|embed/|v/)|youtu\.be/)([^?&/\s]+)"
    match = re.search(yt_pattern, url, re.IGNORECASE)

    if match:
        video_id = match.group(1)
        url = f"https://www.youtube.com/watch?v={video_id}"
        print(
            f"Da chuan hoa URL YouTube thanh: {url}. Dang lay transcript qua yt-dlp..."
        )
        try:
            transcript = get_yt_transcript_via_ytdlp(video_id)
            if transcript:
                return jsonify(
                    {
                        "markdown": f"# Phụ Đề Video YouTube ({video_id})\n\n{transcript}",
                        "filename": url,
                        "preview_url": None,
                    }
                )
        except Exception as yt_err:
            print(f"Lỗi khi lấy phụ đề YouTube qua yt-dlp: {yt_err}")

    try:
        client_kwargs = {}
        if docintel_endpoint:
            client_kwargs["docintel_endpoint"] = docintel_endpoint
        if cu_endpoint:
            client_kwargs["cu_endpoint"] = cu_endpoint
        local_client = (
            MarkItDown(**client_kwargs) if client_kwargs else markitdown_client
        )

        print(f"Dang convert URL: {url}...")
        result = local_client.convert(url)
        return jsonify(
            {"markdown": result.text_content, "filename": url, "preview_url": None}
        )
    except Exception as e:
        print(f"Loi khi convert URL {url}: {e}")
        return jsonify({"error": f"Lỗi khi convert URL: {str(e)}"}), 500


@app.route("/api/check_update", methods=["GET"])
def check_update_endpoint():
    res = check_for_updates()
    return jsonify(res)


@app.route("/api/apply_update", methods=["POST"])
def apply_update_endpoint():
    data = request.get_json() or {}
    download_url = data.get("download_url")
    if not download_url:
        return jsonify({"error": "Không có link tải cập nhật."}), 400

    try:
        import subprocess
        import tempfile
        import zipfile
        import shutil

        is_zip = download_url.lower().endswith(".zip")

        # 1. Tải file cập nhật mới
        temp_dir = tempfile.gettempdir()
        file_ext = ".zip" if is_zip else ".exe"
        temp_file_path = os.path.join(temp_dir, f"markitdown_studio_update{file_ext}")

        print(f"Đang tải bản cập nhật từ: {download_url}...")
        response = requests.get(download_url, stream=True, timeout=60)
        response.raise_for_status()
        with open(temp_file_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # 2. Xử lý đường dẫn exe đang chạy
        current_exe = sys.executable
        # Nếu đang chạy bằng python thì không thay thế exe
        if (
            not current_exe.endswith(".exe")
            or "python" in os.path.basename(current_exe).lower()
        ):
            return jsonify(
                {
                    "success": True,
                    "message": "Đã tải thành công bản cập nhật (chế độ Dev: chỉ tải, không replace exe/zip).",
                }
            )

        current_dir = os.path.dirname(current_exe)
        exe_name = os.path.basename(current_exe)

        is_setup = (
            "setup" in download_url.lower() or "installer" in download_url.lower()
        )

        if is_zip:
            # Giải nén zip ra một thư mục tạm riêng
            extract_dir = os.path.join(temp_dir, "markitdown_studio_extracted")
            if os.path.exists(extract_dir):
                shutil.rmtree(extract_dir)
            os.makedirs(extract_dir, exist_ok=True)

            print(f"Giải nén tệp cập nhật zip vào {extract_dir}...")
            with zipfile.ZipFile(temp_file_path, "r") as zip_ref:
                zip_ref.extractall(extract_dir)

            # Kiểm tra xem có thư mục con MarkItDownStudio hay không
            source_dir = extract_dir
            subfolders = [
                f
                for f in os.listdir(extract_dir)
                if os.path.isdir(os.path.join(extract_dir, f))
            ]
            if len(subfolders) == 1 and subfolders[0].lower() == "markitdownstudio":
                source_dir = os.path.join(extract_dir, subfolders[0])

            # Tạo batch script để sao chép thư mục
            bat_content = f"""@echo off
chcp 65001 > nul
echo Dang cap nhat phien ban moi cho MarkItDown Studio...
timeout /t 2 /nobreak > nul
:loop
taskkill /f /im "{exe_name}" > nul 2>&1
xcopy "{source_dir}" "{current_dir}" /E /I /Y /Q > nul 2>&1
if errorlevel 1 (
    timeout /t 1 /nobreak > nul
    goto loop
)
start "" "{current_exe}"
rd /s /q "{extract_dir}" > nul 2>&1
del "{temp_file_path}" > nul 2>&1
(goto) 2>nul & del "%~f0"
"""
        elif is_setup:
            # Trường hợp file Setup Installer (.exe)
            bat_content = f"""@echo off
chcp 65001 > nul
echo Dang khoi dong trinh cai dat cap nhat MarkItDown Studio...
timeout /t 2 /nobreak > nul
taskkill /f /im "{exe_name}" > nul 2>&1
start "" "{temp_file_path}"
(goto) 2>nul & del "%~f0"
"""
        else:
            # Trường hợp file đơn .exe
            bat_content = f"""@echo off
chcp 65001 > nul
echo Dang cap nhat ung dung MarkItDown Studio...
timeout /t 2 /nobreak > nul
:loop
taskkill /f /im "{exe_name}" > nul 2>&1
del "{current_exe}" > nul 2>&1
if exist "{current_exe}" (
    timeout /t 1 /nobreak > nul
    goto loop
)
copy "{temp_file_path}" "{current_exe}" > nul
start "" "{current_exe}"
del "{temp_file_path}" > nul
(goto) 2>nul & del "%~f0"
"""

        bat_path = os.path.join(temp_dir, "update_markitdown.bat")
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(bat_content)

        print("Đang kích hoạt script cập nhật và tắt ứng dụng...")
        subprocess.Popen([bat_path], shell=True)

        # Shutdown Flask server
        def shutdown():
            time.sleep(1)
            os._exit(0)

        import threading

        threading.Thread(target=shutdown).start()

        return jsonify(
            {
                "success": True,
                "message": "Đang tiến hành tự động cập nhật và khởi động lại ứng dụng...",
            }
        )
    except Exception as e:
        print(f"Lỗi khi thực hiện cập nhật: {e}")
        return jsonify({"error": f"Lỗi cập nhật: {str(e)}"}), 500


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


if __name__ == "__main__":
    print("Khởi động server tại http://127.0.0.1:5000")
    app.run(debug=False, host="127.0.0.1", port=5000)
