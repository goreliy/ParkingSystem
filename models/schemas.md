# JSON Schemas

## config.json
```json
{
  "schema_version": 1,
  "bot_token": "",
  "allowed_chats": [
    {
      "chat_id": 123456789,
      "username": "user123",
      "first_name": "John",
      "is_admin": false
    }
  ],
  "occupancy_minutes": 5,
  "confidence_threshold": 0.5,
  "update_hz": 1.0,
  "streaming": {
    "enabled": true,
    "ffmpeg_path": "ffmpeg",
    "targets": [
      {
        "alias": "main_group",
        "chat_id": -1001234567890,
        "title": "Parking Monitor Group",
        "rtmp_url": "rtmp://example.com/live",
        "stream_key": "secret_key"
      }
    ],
    "one_active_stream": true
  }
}
```

## cameras.json
```json
{
  "cameras": [
    {
      "id": "cam_001",
      "name": "Main Entrance",
      "rtsp_url": "rtsp://user:pass@192.168.1.100:554/stream",
      "assigned_space_ids": ["space_001"]
    }
  ]
}
```

## spaces.json
```json
{
  "spaces": [
    {
      "id": "space_001",
      "name": "Ground Floor",
      "camera_ids": ["cam_001", "cam_002"],
      "next_spot_number": 1,
      "spot_numbering_scheme": "sequential"
    }
  ]
}
```

**Новые поля:**
- `next_spot_number` (int): Следующий доступный номер места для сквозной нумерации
- `spot_numbering_scheme` (string): Схема нумерации - "sequential" для последовательной (1, 2, 3...) или "grid" для сетки (A1, A2, B1...)

## spots.json
```json
{
  "spots": [
    {
      "id": "spot_001",
      "space_id": "space_001",
      "camera_id": "cam_001",
      "type": "parking",
      "label": "A1",
      "spot_number": 1,
      "rect": {
        "x1": 100,
        "y1": 100,
        "x2": 200,
        "y2": 200
      },
      "alternative_views": [
        {
          "camera_id": "cam_002",
          "rect": {
            "x1": 150,
            "y1": 120,
            "x2": 250,
            "y2": 220
          }
        }
      ],
      "created_by": "manual",
      "created_at": "2025-11-13T10:00:00Z"
    }
  ]
}
```

**Новые поля:**
- `camera_id` (string): ID камеры, с которой было создано это место
- `spot_number` (int): Уникальный номер места в пределах зоны (для сквозной нумерации)
- `alternative_views` (array): Альтернативные координаты этого же места с других камер
- `created_by` (string): "manual" или "auto_markup" - способ создания
- `created_at` (string ISO8601): Время создания места

## state.json
```json
{
  "spaces": {
    "space_001": {
      "total_spots": 10,
      "occupied_spots": 3,
      "free_spots": 7,
      "spots": {
        "spot_001": {
          "occupied": true,
          "detected_at": "2025-11-12T10:30:00Z",
          "occupied_since": "2025-11-12T10:35:00Z",
          "sequential_number": 1
        }
      }
    }
  },
  "active_stream": null
}
```

