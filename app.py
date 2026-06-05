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
    if hasattr(sys, '_MEIPASS'):
        return sys._MEIPASS
    return os.path.dirname(os.path.abspath(__file__))

base_path = get_base_path()

# Ensure packages directory is in sys.path so we can import markitdown
sys.path.insert(0, os.path.join(base_path, 'packages', 'markitdown'))
sys.path.insert(0, os.path.join(base_path, 'packages', 'markitdown', 'src'))

try:
    from markitdown import MarkItDown
except ImportError:
    try:
        from markitdown.markitdown import MarkItDown
    except ImportError:
        import markitdown
        from markitdown import MarkItDown

app = Flask(__name__, 
            template_folder=os.path.join(base_path, 'templates'), 
            static_folder=os.path.join(base_path, 'static'))

# Uploads thư mục nằm cạnh file exe hoặc file script gốc
if hasattr(sys, '_MEIPASS'):
    executable_dir = os.path.dirname(sys.executable)
    UPLOAD_FOLDER = os.path.join(executable_dir, 'uploads')
else:
    UPLOAD_FOLDER = os.path.join(base_path, 'uploads')

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

markitdown_client = MarkItDown()
ocr_reader = None

def get_ocr_reader():
    global ocr_reader
    if ocr_reader is None:
        try:
            import easyocr
            print("Dang tai/khoi tao model EasyOCR (vi, en)...")
            ocr_reader = easyocr.Reader(['vi', 'en'])
            print("Khoi tao EasyOCR thanh cong.")
        except Exception as e:
            print(f"Khong the khoi tao EasyOCR: {e}")
    return ocr_reader

def sort_ocr_results_smart(results):
    if not results:
        return ""
        
    valid_results = []
    for item in results:
        try:
            box, text = item
            if len(box) >= 4 and text.strip():
                left = box[0][0]
                top = box[0][1]
                width = box[1][0] - box[0][0]
                valid_results.append({
                    'left': left,
                    'top': top,
                    'width': width,
                    'text': text.strip()
                })
        except Exception:
            pass
            
    if not valid_results:
        return ""
        
    max_right = max(item['left'] + item['width'] for item in valid_results)
    
    spanning = []
    columns = []
    for item in valid_results:
        if item['width'] > max_right * 0.65:
            spanning.append(item)
        else:
            columns.append(item)
            
    groups = []
    for item in columns:
        item_left = item['left']
        item_right = item['left'] + item['width']
        
        merged = False
        for g in groups:
            g_left = min(x['left'] for x in g)
            g_right = max(x['left'] + x['width'] for x in g)
            
            if max(item_left, g_left) < min(item_right, g_right):
                g.append(item)
                merged = True
                break
        if not merged:
            groups.append([item])
            
    for g in groups:
        g.sort(key=lambda x: x['top'])
        
    all_groups = []
    for item in spanning:
        all_groups.append({
            'top': item['top'],
            'text': item['text']
        })
    for g in groups:
        min_top = min(x['top'] for x in g)
        col_text = "\n\n".join(x['text'] for x in g)
        all_groups.append({
            'top': min_top,
            'text': col_text
        })
        
    all_groups.sort(key=lambda x: x['top'])
    
    return "\n\n".join(item['text'] for item in all_groups)

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
        results = reader.readtext(img_np, paragraph=True)
        page_text = sort_ocr_results_smart(results)
        
        if page_text.strip():
            ocr_pages.append(f"## Trang {i+1}\n\n{page_text}")
        else:
            ocr_pages.append(f"## Trang {i+1}\n\n*(Trang trống hoặc không nhận diện được chữ)*")
            
    return "\n\n".join(ocr_pages)

def transcribe_audio_free_local(file_path):
    import speech_recognition as sr
    from pydub import AudioSegment
    from pydub.effects import normalize
    import tempfile
    
    sound = AudioSegment.from_file(file_path)
    
    # 1. TĂNG CƯỜNG ÂM THANH (AUDIO ENHANCEMENT):
    # Chuẩn hóa âm lượng (normalization) đưa biên độ âm thanh về mức tối đa mà không bị vỡ/méo tiếng.
    # Giúp các đoạn nói nhỏ, thầm thì được khuếch đại rõ ràng lên.
    try:
        sound = normalize(sound)
        print("Da tu dong tang cuong va chuan hoa am luong (Normalize) cho file am thanh.")
    except Exception as norm_err:
        print(f"Khong the chuan hoa am luong: {norm_err}")
        
    sound = sound.set_frame_rate(16000).set_channels(1)
    
    # Chia nhỏ mỗi đoạn 30 giây để tránh lỗi timeout của Google API và nhận diện tốt hơn
    chunk_length_ms = 30000
    overlap_ms = 1000  # 1 giây chồng chéo giữa các đoạn để không bị mất chữ ở điểm cắt
    
    chunks = []
    duration_ms = len(sound)
    start = 0
    while start < duration_ms:
        end = min(start + chunk_length_ms, duration_ms)
        chunks.append(sound[start:end])
        start += chunk_length_ms - overlap_ms
        
    recognizer = sr.Recognizer()
    # Cấu hình lọc tạp âm nhạy hơn
    recognizer.dynamic_energy_threshold = True
    
    full_transcript = []
    
    for idx, chunk in enumerate(chunks):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_file:
            tmp_path = tmp_file.name
        try:
            chunk.export(tmp_path, format="wav")
            with sr.AudioFile(tmp_path) as source:
                # Tự động điều chỉnh ngưỡng ồn cho từng phân đoạn nhỏ
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio_data = recognizer.record(source)
                try:
                    text = recognizer.recognize_google(audio_data, language="vi-VN")
                    if text.strip():
                        start_sec = (idx * (chunk_length_ms - overlap_ms)) // 1000
                        minutes = start_sec // 60
                        seconds = start_sec % 60
                        timestamp = f"[{minutes:02d}:{seconds:02d}]"
                        full_transcript.append(f"{timestamp} {text}")
                except sr.UnknownValueError:
                    # Ghi chú phân đoạn không nghe rõ thay vì bỏ trống hoàn toàn
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
        'mp3': 'audio/mp3',
        'wav': 'audio/wav',
        'm4a': 'audio/m4a',
        'mp4': 'video/mp4'
    }
    mime_type = mime_map.get(ext, 'application/octet-stream')
    file_size = os.path.getsize(file_path)
    display_name = os.path.basename(file_path)
    
    # 1. Start Resumable Upload session
    upload_url_init = f"https://generativelanguage.googleapis.com/upload/v1beta/files?key={api_key}"
    headers_init = {
        "X-Goog-Upload-Protocol": "resumable",
        "X-Goog-Upload-Command": "start",
        "X-Goog-Upload-Header-Content-Length": str(file_size),
        "X-Goog-Upload-Header-Content-Type": mime_type,
        "Content-Type": "application/json"
    }
    body_init = {
        "file": {
            "display_name": display_name
        }
    }
    
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
        "X-Goog-Upload-Command": "upload, finalize"
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
                        {
                            "fileData": {
                                "fileUri": file_uri,
                                "mimeType": mime_type
                            }
                        }
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_file():
    if 'file' not in request.files:
        return jsonify({'error': 'Không tìm thấy file gửi lên.'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'Chưa chọn file.'}), 400
    
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
    file.save(file_path)
    
    ext = file.filename.split('.')[-1].lower()
    gemini_key = request.headers.get('X-Gemini-Key')
    docintel_endpoint = request.headers.get('X-DocIntel-Endpoint')
    cu_endpoint = request.headers.get('X-CU-Endpoint')
    
    try:
        # Cấu hình client động dựa trên Endpoint Azure nếu có
        client_kwargs = {}
        if docintel_endpoint:
            client_kwargs['docintel_endpoint'] = docintel_endpoint
        if cu_endpoint:
            client_kwargs['cu_endpoint'] = cu_endpoint
        local_client = MarkItDown(**client_kwargs) if client_kwargs else markitdown_client

        # Neu la file am thanh, uu tien Gemini API neu co Key, nguoc lai dung transcriber local mien phi
        if ext in ['mp3', 'wav', 'm4a', 'mp4']:
            if gemini_key:
                print(f"Tien hanh transcribe {file.filename} qua Gemini API...")
                markdown_content = transcribe_audio_via_gemini(file_path, gemini_key, ext)
                markdown_content = f"# Kết Quả Trích Xuất Lời Thoại (Gemini AI)\n\n" + markdown_content
            else:
                print(f"Tien hanh transcribe {file.filename} mien phi local...")
                try:
                    ocr_content = transcribe_audio_free_local(file_path)
                    markdown_content = f"# Kết Quả Trích Xuất Lời Thoại (Miễn Phí Local)\n\n> **Lưu ý**: Hệ thống đang sử dụng Google Speech API miễn phí (không cần API Key) bằng cách chia nhỏ file âm thanh.\n\n" + ocr_content
                except Exception as local_err:
                    print(f"Lỗi khi transcribe local: {local_err}")
                    result = local_client.convert(file_path, keep_data_uris=True)
                    markdown_content = result.text_content
        
        elif ext in ['png', 'jpg', 'jpeg']:
            reader = get_ocr_reader()
            if reader is not None:
                print(f"Dang chay OCR cho file: {file.filename}")
                results = reader.readtext(file_path, paragraph=True)
                markdown_content = sort_ocr_results_smart(results)
                
                if not markdown_content.strip():
                    markdown_content = "# Kết Quả Trích Xuất Chữ (OCR)\n\nKhông tìm thấy chữ nào trong hình ảnh này."
                else:
                    markdown_content = "# Kết Quả Trích Xuất Chữ (OCR)\n\n" + markdown_content
            else:
                result = local_client.convert(file_path, keep_data_uris=True)
                markdown_content = result.text_content
                if not markdown_content.strip():
                    markdown_content = "# Kết Quả\n\nKhông trích xuất được thông tin từ hình ảnh."
        else:
            print(f"Dang convert file {file.filename} bang MarkItDown...")
            result = local_client.convert(file_path, keep_data_uris=True)
            markdown_content = result.text_content
            
            # Kiểm tra xem có phải PDF dạng ảnh quét (scanned PDF) không
            if ext == 'pdf':
                cleaned_text = "".join(c for c in markdown_content if c.isalnum())
                if len(cleaned_text) < 150:
                    print("Nhận diện PDF dạng scan (quá ít chữ). Tiến hành chạy OCR...")
                    try:
                        ocr_content = ocr_pdf_via_easyocr(file_path)
                        markdown_content = f"# Kết Quả Trích Xuất PDF (OCR Tự Động)\n\n> **Lưu ý**: Tài liệu này được xác định là ảnh quét (Scanned PDF). Hệ thống đã tự động chạy EasyOCR tiếng Việt để trích xuất nội dung.\n\n" + ocr_content
                    except Exception as ocr_err:
                        print(f"Lỗi khi OCR PDF: {ocr_err}")
                        markdown_content += f"\n\n> **Lưu ý**: Tài liệu này có vẻ là PDF dạng quét (Scanned PDF) nhưng lỗi khi chạy OCR: {str(ocr_err)}"
            
            # Neu convert ra bi loi hoac rong va la file am thanh ma khong co key
            if ext in ['mp3', 'wav', 'm4a', 'mp4'] and "[No speech detected]" in markdown_content:
                markdown_content += "\n\n> **Lưu ý**: Đối với file âm thanh dài hoặc dung lượng lớn, hãy nhập **Gemini API Key** ở góc phải màn hình để sử dụng AI transcribe tiếng Việt chính xác."
        
        return jsonify({
            'markdown': markdown_content,
            'filename': file.filename,
            'preview_url': f'/uploads/{file.filename}'
        })
    except Exception as e:
        print(f"Loi khi convert {file.filename}: {e}")
        return jsonify({'error': f'Lỗi khi convert: {str(e)}'}), 500

@app.route('/convert_url', methods=['POST'])
def convert_url():
    data = request.get_json()
    url = data.get('url')
    if not url:
        return jsonify({'error': 'Không tìm thấy URL.'}), 400
        
    docintel_endpoint = request.headers.get('X-DocIntel-Endpoint')
    cu_endpoint = request.headers.get('X-CU-Endpoint')
    
    # Chuẩn hóa URL YouTube nếu có dạng uppercase hoặc viết tắt
    import re
    yt_pattern = r'(?:https?://)?(?:[a-zA-Z0-9-]+\.)?(?:youtube\.com/(?:watch\?v=|embed/|v/)|youtu\.be/)([^?&/\s]+)'
    match = re.search(yt_pattern, url, re.IGNORECASE)
    if match:
        video_id = match.group(1)
        url = f"https://www.youtube.com/watch?v={video_id}"
        print(f"Da chuan hoa URL YouTube thanh: {url}")
        
    try:
        client_kwargs = {}
        if docintel_endpoint:
            client_kwargs['docintel_endpoint'] = docintel_endpoint
        if cu_endpoint:
            client_kwargs['cu_endpoint'] = cu_endpoint
        local_client = MarkItDown(**client_kwargs) if client_kwargs else markitdown_client
        
        print(f"Dang convert URL: {url}...")
        result = local_client.convert(url)
        return jsonify({
            'markdown': result.text_content,
            'filename': url,
            'preview_url': None
        })
    except Exception as e:
        print(f"Loi khi convert URL {url}: {e}")
        return jsonify({'error': f'Lỗi khi convert URL: {str(e)}'}), 500

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    print("Khởi động server tại http://127.0.0.1:5000")
    app.run(debug=False, host='127.0.0.1', port=5000)
