# Video Creator — Automatic Product Video Generator

Tạo video sản phẩm 1080×1920 (9:16 vertical) tự động từ ảnh, text, nhạc nền.
Tích hợp PocketBase job queue để chạy concurrent rendering trên Mac M4 16GB.

## Architecture

```
Marketing Hub (UI)  ──► PocketBase (video_jobs) ──► pb_worker.py
       │                                                │
  Tạo job với ảnh,                              ProcessPoolExecutor
  text, nhạc nền                                  (2-3 concurrent)
       │                                                │
  Realtime progress  ◄──────────────────────  slideshow_engine
       │                                        MoviePy + ffmpeg
  Video preview                                  VideoToolbox HW
```

## Quick Start

### 1. Cài dependencies

```bash
cd video-creater
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### 2. Chạy worker

```bash
PB_ADMIN_EMAIL=admin@example.com \
PB_ADMIN_PASSWORD=yourpassword \
./start.sh
```

Hoặc dùng `start_all.sh` ở root (đã tích hợp sẵn).

### 3. Tạo video từ UI

1. Mở Marketing Hub → **Video Generator** (sidebar)
2. Click **Tạo Video**
3. Nhập intro text, outro text, chọn variant (A/B/C)
4. Thêm 2-10 sản phẩm (ảnh + tên + hook)
5. Submit → worker tự động render → xem video khi xong

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PB_URL` | `http://localhost:8090` | PocketBase URL |
| `PB_ADMIN_EMAIL` | *required* | PB admin email |
| `PB_ADMIN_PASSWORD` | *required* | PB admin password |
| `MAX_WORKERS` | auto (2-3) | Concurrent render processes |
| `POLL_INTERVAL` | `5` | Seconds between queue checks |
| `LEASE_SECONDS` | `600` | Job lease duration (10 min) |
| `BASE_TMP` | `/tmp/video-jobs` | Temp directory for renders |

## Variant Profiles

| Variant | Style | Speed | Motion |
|---------|-------|-------|--------|
| **A** | Energetic | Fast cuts | High |
| **B** | Smooth | Medium | Gentle |
| **C** | Dramatic | Slow reveal | Cinematic |

## Hardware Encoder

Worker tự động detect `h264_videotoolbox` (Apple Silicon HW encoder).
Nếu không có, fallback sang `libx264` (software).

- **VideoToolbox**: Nhanh hơn ~3x, dùng ít CPU → chạy được 3 workers
- **libx264**: Chậm hơn, CPU-bound → max 2 workers

## File Structure

```
video-creater/
├── start.sh              # Startup script
├── pb_worker.py          # Main coordinator (poll → claim → render → upload)
├── pb_client.py          # PocketBase REST client (httpx)
├── requirements.txt      # Python dependencies
├── slideshow_engine/     # Core rendering engine
│   ├── config.py         # RenderContext, encoder detection
│   ├── pipeline.py       # render_single_variant()
│   ├── data_input.py     # Content parsing + validation
│   ├── visuals.py        # Image processing (blur, motion)
│   ├── tts.py            # Text-to-speech (edge-tts)
│   └── hook_outro.py     # Intro/outro animations
├── slideshow_moviepy.py  # CLI entry point (standalone)
├── assets/fonts/         # BeVietnamPro-Bold.ttf
├── bg_music.mp3          # Default background music
├── logo.webp             # Default logo
└── docs/
    ├── agent_integration.md  # MCP agent usage guide
    └── README.md             # This file
```

## Job Lifecycle

```
queued → claimed → rendering → uploading → done
                                         ↘ failed (retry up to max_attempts)
```

- **queued**: Job created, waiting for worker
- **claimed**: Worker locked the job (lease-based)
- **rendering**: Video being generated (progress 0-100%)
- **uploading**: MP4 being uploaded to PocketBase
- **done**: Video ready for download/preview
- **failed**: Error after max retries (default 3)

## Agent Integration

AI agents can create video jobs via MCP bridge without any code changes:

```json
{
  "tool": "create_record",
  "arguments": {
    "collection": "video_jobs",
    "data": {
      "workspace_id": "<id>",
      "status": "queued",
      "input_json": {
        "intro_text": "Top sản phẩm",
        "outro_text": "Mua ngay!",
        "products": [
          {"image": "p1.jpg", "text": "SP 1", "hook": "Giảm 50%"},
          {"image": "p2.jpg", "text": "SP 2", "hook": "Mới"}
        ]
      }
    }
  }
}
```

See [agent_integration.md](agent_integration.md) for full details.
