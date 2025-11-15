# 🅿️ Parking Monitor System

A comprehensive parking space monitoring system using computer vision (YOLOv8/v12), Flask web interface, and Telegram bot integration for remote management.

## Features

- 📹 **RTSP Camera Support** - Monitor multiple cameras with automatic reconnection
- 🤖 **AI Vehicle Detection** - YOLOv8/v12 for accurate vehicle detection
- ⏱️ **Smart Occupancy Detection** - Configurable timer-based occupancy threshold
- 📱 **Telegram Bot** - Remote monitoring and admin commands
- 🎥 **RTMP Streaming** - Stream camera feeds to Telegram groups/channels
- 🌐 **Real-time Dashboard** - Live updates via Server-Sent Events (SSE)
- 💾 **Simple Storage** - JSON-based data storage (no database required)
- 🖥️ **Cross-platform** - Works on Windows and Linux
- 🔢 **Sequential Numbering** - Automatic numbering of occupied spots
- 📊 **Statistics** - Real-time parking statistics and analytics

## Architecture

```
parking-monitor/
├── backend/
│   ├── api/            # REST API endpoints
│   ├── bot/            # Telegram bot and stream manager
│   ├── services/       # Core services (video, detection, state)
│   ├── storage/        # JSON storage layer
│   ├── templates/      # HTML templates
│   └── app.py          # Main application
├── data/               # JSON data files
├── logs/               # Application logs
├── models/             # Schema documentation
├── deploy/             # Deployment configs (systemd)
├── requirements.txt    # Python dependencies
├── run_windows.ps1     # Windows run script
└── run_linux.sh        # Linux run script
```

## Requirements

### Software
- **Python 3.10+**
- **FFmpeg** (for streaming features)
- **OpenCV** (installed via requirements.txt)
- **CUDA/cuDNN** (optional, for GPU acceleration)

### Hardware
- **CPU**: Multi-core processor (4+ cores recommended)
- **RAM**: 4GB minimum, 8GB+ recommended
- **GPU**: Optional NVIDIA GPU for faster detection
- **Network**: Stable internet connection for Telegram bot

## Installation

### Windows

1. **Install Python 3.10+**
   - Download from [python.org](https://www.python.org/downloads/)
   - Make sure to check "Add Python to PATH" during installation

2. **Install FFmpeg** (optional, for streaming)
   - Download from [ffmpeg.org](https://ffmpeg.org/download.html)
   - Extract and add to PATH

3. **Clone/Download the project**
   ```powershell
   cd D:\parking-monitor
   ```

4. **Run the application**
   ```powershell
   .\run_windows.ps1
   ```

The script will:
- Create a virtual environment
- Install Python dependencies
- Check for FFmpeg
- Start the application

### Linux

1. **Install dependencies**
   ```bash
   # Ubuntu/Debian
   sudo apt-get update
   sudo apt-get install python3 python3-pip python3-venv ffmpeg
   
   # CentOS/RHEL
   sudo yum install python3 python3-pip ffmpeg
   ```

2. **Clone/Download the project**
   ```bash
   cd /opt/parking-monitor
   ```

3. **Make script executable**
   ```bash
   chmod +x run_linux.sh
   ```

4. **Run the application**
   ```bash
   ./run_linux.sh
   ```

### Linux - Systemd Service (Production)

1. **Create user**
   ```bash
   sudo useradd -r -s /bin/false parking
   ```

2. **Set permissions**
   ```bash
   sudo chown -R parking:parking /opt/parking-monitor
   sudo mkdir -p /var/log/parking-monitor
   sudo chown parking:parking /var/log/parking-monitor
   ```

3. **Install service**
   ```bash
   sudo cp deploy/systemd/parking.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable parking
   sudo systemctl start parking
   ```

4. **Check status**
   ```bash
   sudo systemctl status parking
   sudo journalctl -u parking -f
   ```

## Configuration

### Web Interface

Access the web interface at `http://localhost:5000`

1. **Setup** (`/setup`)
   - Add cameras with RTSP URLs
   - Create parking spaces
   - Define parking spots by clicking on camera views
   - Assign cameras to spaces

2. **Dashboard** (`/dashboard`)
   - View real-time parking status
   - Monitor all spaces and spots
   - See annotated camera views

3. **Configuration** (`/config`)
   - Configure Telegram bot token
   - Manage chat permissions (admin/user)
   - Setup RTMP streaming targets
   - Adjust occupancy detection parameters

### Telegram Bot

1. **Create a bot**
   - Talk to [@BotFather](https://t.me/BotFather) on Telegram
   - Send `/newbot` and follow instructions
   - Copy the bot token

2. **Configure in web UI**
   - Go to Configuration page
   - Enter bot token
   - Save and restart application

3. **Register users**
   - Send `/start` to your bot
   - User will appear in Configuration page
   - Set admin privileges in web UI

### Telegram Bot Commands

**User Commands:**
- `/help` - Show all commands
- `/spaces` - List all parking spaces
- `/space <id>` - Get space details and statistics
- `/image_camera <camera_id>` - Get camera snapshot
- `/image_space <space_id>` - Get annotated space image

**Admin Commands:**
- `/add_camera <name> <rtsp_url>` - Add new camera
- `/list_cameras` - List all cameras
- `/add_space <name>` - Create parking space
- `/assign_camera <space_id> <camera_id>` - Assign camera to space
- `/add_spot <space_id> <type> <label> <x1,y1;x2,y2>` - Add parking spot
- `/move_spot <spot_id> <x1,y1;x2,y2>` - Move parking spot
- `/delete_spot <spot_id>` - Delete parking spot
- `/set_occupancy_minutes <N>` - Set occupancy threshold
- `/start_stream <camera_id> [target]` - Start RTMP stream
- `/stop_stream` - Stop active stream
- `/stream_status` - Check stream status

### RTMP Streaming to Telegram

1. **Create Telegram group/channel**
   - Create a group or channel
   - Add your bot as admin
   - Start a video chat

2. **Get RTMP credentials**
   - Telegram provides RTMP URL and stream key when you start streaming
   - Note: This feature requires Telegram Premium or business account

3. **Configure in web UI**
   - Go to Configuration > Streaming
   - Add target with alias, chat_id, RTMP URL, and stream key
   - Save configuration

4. **Start streaming**
   - Via bot: `/start_stream <camera_id> [target_alias]`
   - Via API: `POST /api/stream/start`
   - Only one stream can be active at a time

## API Endpoints

### Cameras
- `GET /api/cameras` - List cameras
- `POST /api/cameras` - Create camera
- `GET /api/cameras/<id>` - Get camera
- `PUT /api/cameras/<id>` - Update camera
- `DELETE /api/cameras/<id>` - Delete camera

### Spaces
- `GET /api/spaces` - List spaces
- `POST /api/spaces` - Create space
- `GET /api/spaces/<id>` - Get space
- `PUT /api/spaces/<id>` - Update space
- `DELETE /api/spaces/<id>` - Delete space
- `POST /api/spaces/<id>/assign_camera` - Assign camera

### Spots
- `GET /api/spots` - List spots (filter by `?space_id=`)
- `POST /api/spots` - Create spot
- `PUT /api/spots/<id>` - Update spot
- `DELETE /api/spots/<id>` - Delete spot

### State & Monitoring
- `GET /api/state` - Get all spaces summary
- `GET /api/state/spaces/<id>` - Get space details
- `GET /api/events` - SSE stream for real-time updates
- `GET /api/snapshot/camera/<id>` - Get camera snapshot
- `GET /api/snapshot/space/<id>?annotated=1` - Get annotated space image

### Configuration
- `GET /api/config` - Get configuration
- `GET /api/config/bot` - Get bot config
- `PUT /api/config/bot` - Update bot config
- `GET /api/config/streaming` - Get streaming config
- `PUT /api/config/streaming` - Update streaming config
- `PUT /api/config/occupancy` - Update occupancy settings

### Streaming
- `GET /api/stream/status` - Get active stream status
- `POST /api/stream/start` - Start stream
- `POST /api/stream/stop` - Stop stream

## YOLO Model

By default, the system uses `yolov8n.pt` (nano model) from Ultralytics. On first run, it will download automatically.

**Supported models:**
- `yolov8n.pt` - Fastest, lowest accuracy
- `yolov8s.pt` - Small
- `yolov8m.pt` - Medium
- `yolov8l.pt` - Large
- `yolov8x.pt` - Extra large, highest accuracy

To use a different model, modify `backend/services/detector.py`:
```python
self.model = YOLO("yolov8s.pt")  # Change model here
```

## RTSP Camera Examples

**Generic RTSP:**
```
rtsp://username:password@192.168.1.100:554/stream
```

**Hikvision:**
```
rtsp://admin:password@192.168.1.100:554/Streaming/Channels/101
```

**Dahua:**
```
rtsp://admin:password@192.168.1.100:554/cam/realmonitor?channel=1&subtype=0
```

**Axis:**
```
rtsp://admin:password@192.168.1.100/axis-media/media.amp
```

**Test with VLC:**
```bash
vlc rtsp://your-camera-url
```

## Troubleshooting

### Camera not connecting
- Verify RTSP URL with VLC
- Check network connectivity
- Ensure camera supports RTSP
- Try `rtsp_transport tcp` (already configured)

### YOLO detection not working
- Check logs for errors
- Ensure sufficient RAM (4GB+)
- Try smaller model (`yolov8n.pt`)
- Verify OpenCV installation

### Bot not responding
- Check bot token is correct
- Ensure bot is started (check logs)
- Verify internet connection
- Send `/start` to register chat

### Streaming fails
- Verify FFmpeg is installed: `ffmpeg -version`
- Check RTMP URL and stream key
- Ensure only one stream is active
- Check FFmpeg logs in application logs

### Performance issues
- Reduce `update_hz` in configuration
- Use smaller YOLO model
- Reduce number of cameras
- Use GPU acceleration if available

## Development

### Project Structure
- `backend/api/` - Flask blueprints for REST API
- `backend/services/` - Core business logic
- `backend/storage/` - JSON storage with locking
- `backend/bot/` - Telegram bot and FFmpeg manager

### Adding Features
1. Add service logic in `backend/services/`
2. Create API endpoints in `backend/api/`
3. Update templates in `backend/templates/`
4. Update TODO tasks

### Logging
Logs are stored in `logs/parking.log`. Configure level in `backend/app.py`:
```python
logging.basicConfig(level=logging.DEBUG)  # More verbose
```

## License

This project is provided as-is for educational and commercial use.

## Support

For issues and questions:
- Check logs in `logs/parking.log`
- Review this README
- Check API endpoint responses

## Credits

- **YOLOv8** by Ultralytics
- **Flask** web framework
- **OpenCV** for video processing
- **pyTelegramBotAPI** for Telegram integration
- **FFmpeg** for video streaming

---

**Version:** 1.0.0  
**Last Updated:** 2025-11-12

