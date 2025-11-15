# Структура классов системы мониторинга парковки

## Обзор архитектуры

Система построена на модульной архитектуре с четким разделением ответственности между компонентами.

```
┌─────────────────────────────────────────────────────────────┐
│                    Flask Application                         │
│                    (backend/app.py)                          │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
        ▼                   ▼                   ▼
┌──────────────┐   ┌──────────────┐   ┌──────────────┐
│   Storage    │   │   Services   │   │   API Layer  │
│              │   │              │   │              │
│ JSONStore    │◄──│ VideoProc    │◄──│ Blueprints   │
│              │   │ Detector     │   │              │
│              │   │ StateManager │   │              │
│              │   │ AutoMarkup   │   │              │
└──────────────┘   └──────────────┘   └──────────────┘
```

---

## 1. Модель данных: Camera (Камера)

### Назначение
Представляет физическую IP-камеру с RTSP потоком.

### Структура
```python
{
    "id": str,                      # Уникальный идентификатор
    "name": str,                    # Человекочитаемое название
    "rtsp_url": str,                # RTSP URL для подключения
    "assigned_space_ids": [str]     # Список зон, к которым привязана камера
}
```

### Пример
```json
{
    "id": "cam_734a0917",
    "name": "Двор - Камера 1",
    "rtsp_url": "rtsp://admin:pass@192.168.1.100:554/stream1",
    "assigned_space_ids": ["space_abc123", "space_def456"]
}
```

### Класс VideoProcessor

Управляет захватом видео с одной камеры.

```python
class VideoProcessor:
    """Обрабатывает видеопоток с RTSP камеры."""
    
    # Атрибуты
    camera_id: str                      # ID камеры
    rtsp_url: str                       # RTSP URL
    cap: cv2.VideoCapture               # OpenCV захват
    latest_frame: np.ndarray            # Последний кадр
    frame_lock: threading.Lock          # Блокировка для thread-safety
    running: bool                       # Флаг работы
    thread: threading.Thread            # Поток захвата
    last_frame_time: float              # Timestamp последнего кадра
    fps: float                          # Текущий FPS
    
    # Методы
    def start()                         # Запустить захват
    def stop()                          # Остановить захват
    def get_latest_frame() -> np.ndarray  # Получить последний кадр
    def is_alive() -> bool              # Проверка активности
```

### Класс VideoProcessorManager

Управляет множеством камер.

```python
class VideoProcessorManager:
    """Менеджер для управления несколькими камерами."""
    
    processors: Dict[str, VideoProcessor]  # camera_id -> processor
    lock: threading.Lock
    
    def add_camera(camera_id, rtsp_url)      # Добавить камеру
    def remove_camera(camera_id)             # Удалить камеру
    def get_frame(camera_id) -> np.ndarray   # Получить кадр
    def is_camera_alive(camera_id) -> bool   # Проверить статус
    def stop_all()                           # Остановить все
```

---

## 2. Модель данных: Space (Парковочная зона)

### Назначение
Логическая группировка парковочных мест (например, "Первый этаж", "Двор", "Улица").

### Структура
```python
{
    "id": str,                          # Уникальный идентификатор
    "name": str,                        # Название зоны
    "camera_ids": [str],                # Камеры, наблюдающие за зоной
    "next_spot_number": int,            # Следующий номер для сквозной нумерации
    "spot_numbering_scheme": str        # "sequential" или "grid"
}
```

### Пример
```json
{
    "id": "space_abc123",
    "name": "Двор - Парковка",
    "camera_ids": ["cam_734a0917", "cam_560403c0"],
    "next_spot_number": 25,
    "spot_numbering_scheme": "sequential"
}
```

### Отношения
- **1 Space → N Cameras** (one-to-many): Одна зона может наблюдаться многими камерами
- **1 Space → N Spots** (one-to-many): Одна зона содержит множество парковочных мест

### Сквозная нумерация

**Проблема**: При наличии нескольких камер на одну зону нужна единая нумерация.

**Решение**: Поле `next_spot_number` хранит следующий доступный номер.

```python
# При создании нового места:
space = get_space("space_abc123")
new_spot_number = space["next_spot_number"]  # 25
new_spot_label = f"A{new_spot_number}"       # "A25"

# После создания:
space["next_spot_number"] = 26
save_space(space)
```

---

## 3. Модель данных: Spot (Парковочное место)

### Назначение
Конкретное парковочное место с координатами на изображении камеры.

### Структура
```python
{
    "id": str,                          # Уникальный идентификатор
    "space_id": str,                    # ID зоны
    "camera_id": str,                   # ID основной камеры (с которой создано)
    "type": str,                        # "parking" или "nopark"
    "label": str,                       # Метка (A1, A2, B1...)
    "spot_number": int,                 # Сквозной номер в зоне
    "rect": {                           # Координаты на кадре основной камеры
        "x1": int, "y1": int,
        "x2": int, "y2": int
    },
    "alternative_views": [              # Координаты с других камер
        {
            "camera_id": str,
            "rect": { x1, y1, x2, y2 }
        }
    ],
    "created_by": str,                  # "manual" или "auto_markup"
    "created_at": str                   # ISO8601 timestamp
}
```

### Пример
```json
{
    "id": "spot_xyz789",
    "space_id": "space_abc123",
    "camera_id": "cam_734a0917",
    "type": "parking",
    "label": "A12",
    "spot_number": 12,
    "rect": {
        "x1": 450,
        "y1": 300,
        "x2": 650,
        "y2": 600
    },
    "alternative_views": [
        {
            "camera_id": "cam_560403c0",
            "rect": {
                "x1": 320,
                "y1": 280,
                "x2": 520,
                "y2": 580
            }
        }
    ],
    "created_by": "auto_markup",
    "created_at": "2025-11-13T18:30:45Z"
}
```

### Множественные ракурсы (alternative_views)

**Проблема**: Одно физическое парковочное место может быть видно с нескольких камер.

**Решение**: Основное место хранит `rect` для основной камеры, а `alternative_views[]` содержит координаты этого же места на других камерах.

#### Workflow создания с множественными камерами:

```
Камера 1 видит место на координатах (100,200,300,500)
    ↓
Создается Spot с camera_id=cam_1, rect=(100,200,300,500)
    ↓
Камера 2 видит ЭТО ЖЕ место на координатах (150,180,350,480)
    ↓
НЕ создается новый Spot, вместо этого:
    ↓
Добавляется в spot.alternative_views:
    {camera_id: "cam_2", rect: (150,180,350,480)}
```

### Детекция с множественными ракурсами

```python
# Система проверяет ВСЕ ракурсы места
spot = get_spot("spot_xyz789")

# Основная камера
if spot["camera_id"] == current_camera_id:
    check_occupancy_in_rect(spot["rect"])

# Альтернативные ракурсы
for alt_view in spot["alternative_views"]:
    if alt_view["camera_id"] == current_camera_id:
        check_occupancy_in_rect(alt_view["rect"])
```

---

## 4. Класс Detector (Детектор транспорта)

### Назначение
Обертка над YOLO для детекции транспортных средств.

### Класс Detection
```python
@dataclass
class Detection:
    """Одна детекция транспортного средства."""
    
    bbox: Tuple[int, int, int, int]    # (x1, y1, x2, y2)
    confidence: float                   # Уверенность (0-1)
    class_name: str                     # "car", "truck", "bus", "motorcycle"
```

### Класс Detector
```python
class Detector:
    """Детектор транспорта с использованием YOLO."""
    
    VEHICLE_CLASSES = ['car', 'truck', 'bus', 'motorcycle']
    
    model: YOLO                         # YOLOv8 модель
    confidence_threshold: float         # Порог уверенности
    
    # Методы
    def detect(frame) -> List[Detection]
        """Найти все машины на кадре."""
    
    def detect_in_roi(frame, roi) -> bool
        """Проверить наличие машины в конкретной зоне."""
    
    def get_detections_in_rois(frame, rois) -> Dict[str, bool]
        """Пакетная проверка множества зон."""
```

---

## 5. Система автоматической разметки

### Класс VehicleTracker

Отслеживает машины на последовательности кадров.

```python
class VehicleTracker:
    """Трекер для определения стабильно стоящих машин."""
    
    # Атрибуты
    stability_seconds: int                              # Минимальное время стабильности
    detections_history: Dict[str, List[Tuple]]         # История детекций по камерам
    
    # Методы
    def add_frame_detections(camera_id, detections)
        """Добавить детекции с кадра."""
    
    def get_stable_vehicles(camera_id) -> List[StableVehicle]
        """Получить список стабильных машин."""
        # Алгоритм:
        # 1. Группирует детекции с IoU > 0.7
        # 2. Проверяет временной диапазон >= stability_seconds
        # 3. Усредняет bbox всех детекций в группе
        # 4. Возвращает только стабильные
    
    def clear_camera(camera_id)
        """Очистить историю камеры."""
```

### Класс StableVehicle
```python
@dataclass
class StableVehicle:
    """Стабильно стоящая машина."""
    
    bbox: Tuple[int, int, int, int]     # Усредненный bbox
    confidence: float                   # Средняя уверенность
    stability_score: float              # Доля кадров где присутствует (0-1)
    detections_count: int               # Количество детекций
    first_seen: float                   # Timestamp первой детекции
    last_seen: float                    # Timestamp последней детекции
```

### Класс SpotProposal
```python
@dataclass
class SpotProposal:
    """Предложение парковочного места."""
    
    index: int                          # Индекс в списке предложений
    camera_id: str                      # ID камеры
    bbox: Tuple[int, int, int, int]     # Оригинальный bbox машины
    suggested_rect: Dict                # Стандартизированный rect
    confidence: float                   # Уверенность детекции
    stability_score: float              # Стабильность (0-1)
    is_valid: bool                      # Флаг валидности
    exclude_reason: Optional[str]       # Причина исключения
    suggested_label: str                # Предложенная метка
```

### Класс AutoMarkupSession
```python
class AutoMarkupSession:
    """Сессия автоматической разметки."""
    
    session_id: str                     # Уникальный ID сессии
    space_id: str                       # ID зоны
    camera_id: str                      # ID камеры для анализа
    mode: str                           # "single"|"average"|"duration"
    settings: Dict                      # Настройки анализа
    status: str                         # "analyzing"|"completed"|"error"|"cancelled"
    started_at: datetime                # Время начала
    completed_at: Optional[datetime]    # Время завершения
    progress: int                       # Прогресс 0-100%
    frames_analyzed: int                # Количество обработанных кадров
    vehicles_found: int                 # Найдено машин
    proposals: List[SpotProposal]       # Список предложений
    preview_frame: np.ndarray           # Кадр для превью
    error_message: Optional[str]        # Сообщение об ошибке
```

### Класс AutoMarkupService
```python
class AutoMarkupService:
    """Сервис автоматической разметки парковочных мест."""
    
    # Зависимости
    store: JSONStore
    video_manager: VideoProcessorManager
    detector: Detector
    
    # Внутреннее состояние
    sessions: Dict[str, AutoMarkupSession]
    lock: threading.Lock
    
    # Методы
    def start_analysis(space_id, mode, ...) -> str
        """Запустить анализ, вернуть session_id."""
    
    def get_analysis_progress(session_id) -> Dict
        """Получить текущий прогресс."""
    
    def get_proposals(session_id) -> Dict
        """Получить список предложений."""
    
    def get_preview_image(session_id) -> np.ndarray
        """Получить изображение с разметкой."""
    
    def apply_proposals(session_id, approved_indices, ...) -> Dict
        """Применить одобренные предложения."""
    
    def cancel_analysis(session_id) -> bool
        """Отменить анализ."""
```

---

## 6. Связи между сущностями

### Camera ↔ Space (Many-to-Many)

```
Camera 1 ────────┐
                 ├──→ Space A
Camera 2 ────────┤
                 └──→ Space B
Camera 3 ────────────→ Space B
```

**Реализация**:
- `Camera.assigned_space_ids` - список зон
- `Space.camera_ids` - список камер

### Space → Spot (One-to-Many)

```
Space A
  ├── Spot A1
  ├── Spot A2
  ├── Spot A3
  └── ...
```

**Фильтрация**: `spots.filter(s => s.space_id === space_id)`

### Camera → Spot (One-to-Many с альтернативными ракурсами)

```
Camera 1 (основная для Spot A1)
  ├── Spot A1 (rect на Camera 1)
  │     └── alternative_view (rect на Camera 2)
  ├── Spot A2 (rect на Camera 1)
  └── Spot A3 (rect на Camera 1)

Camera 2 (основная для Spot B1)
  └── Spot B1 (rect на Camera 2)
        └── alternative_view (rect на Camera 1)
```

**Логика**:
- Каждый Spot имеет одну основную камеру (`spot.camera_id`)
- Может иметь дополнительные ракурсы в `alternative_views[]`

---

## 7. Жизненный цикл автоматической разметки

### Фаза 1: Инициализация
```
Админ выбирает:
├── Space ID
├── Режим анализа (single/average/duration)
├── Параметры (размер места, время стабильности)
└── Нажимает "Запустить"
    ↓
Создается AutoMarkupSession
    session_id = "markup_abc123"
    status = "analyzing"
    ↓
Запускается фоновый поток анализа
```

### Фаза 2: Анализ

#### Режим "single" (быстрый)
```
1. Получить 1 кадр с камеры
2. Запустить detector.detect(frame)
3. Для каждой найденной машины:
   - Применить стандартный размер
   - Проверить валидность
   - Создать SpotProposal
4. status = "completed"
```

#### Режим "average" (усредненный)
```
1. Создать VehicleTracker(stability_seconds=30)
2. На протяжении 30 секунд:
   - Каждую секунду брать кадр
   - Детектировать машины
   - tracker.add_frame_detections()
3. Получить tracker.get_stable_vehicles()
4. Для каждой стабильной машины:
   - Применить стандартный размер
   - Проверить валидность
   - Создать SpotProposal
5. status = "completed"
```

#### Режим "duration" (глубокий)
```
1. Создать VehicleTracker(stability_seconds=настроено)
2. На протяжении N минут:
   - Каждые 5 секунд брать кадр
   - Детектировать машины
   - tracker.add_frame_detections()
3. Получить tracker.get_stable_vehicles()
4. Создать предложения
5. status = "completed"
```

### Фаза 3: Просмотр предложений

```
GET /api/auto-markup/proposals/{session_id}
    ↓
Возвращает список SpotProposal[]
    ↓
Frontend отображает:
├── Preview изображение с разметкой
├── Список предложений с чекбоксами
└── Кнопки "Исключить"/"Включить"
    ↓
Админ выбирает какие места создать
```

### Фаза 4: Применение

```
POST /api/auto-markup/apply
Body: {
    approved_indices: [0, 2, 5, 7],
    label_prefix: "A",
    auto_number: true
}
    ↓
Для каждого одобренного предложения:
├── Получить Space.next_spot_number
├── Создать новый Spot
│   ├── spot_number = next_spot_number
│   ├── label = f"{prefix}{next_spot_number}"
│   ├── camera_id = proposal.camera_id
│   └── rect = proposal.suggested_rect
├── next_spot_number++
└── Сохранить
    ↓
Обновить Space.next_spot_number
    ↓
Инициализировать состояние spots
    ↓
Вернуть { created_spots: 4, spot_ids: [...] }
```

---

## 8. Алгоритмы

### Алгоритм группировки детекций (VehicleTracker)

```python
def _group_stable_detections(detections: List[Tuple[float, Detection]]):
    """
    Алгоритм:
    1. Сортировать детекции по времени
    2. Для каждой детекции i:
       - Если уже использована, пропустить
       - Создать новую группу [i]
       - Найти все детекции j где IoU(i, j) >= 0.7
       - Добавить в группу
       - Пометить как использованные
    3. Для каждой группы:
       - Проверить временной диапазон >= stability_seconds
       - Если нет - отбросить
       - Усреднить все bbox в группе
       - Вычислить stability_score
       - Создать StableVehicle
    4. Вернуть список StableVehicle
    """
```

### Алгоритм IoU (Intersection over Union)

```python
def calculate_iou(bbox1, bbox2):
    """
    x1_1, y1_1, x2_1, y2_1 = bbox1
    x1_2, y1_2, x2_2, y2_2 = bbox2
    
    # Пересечение
    x1_i = max(x1_1, x1_2)
    y1_i = max(y1_1, y1_2)
    x2_i = min(x2_1, x2_2)
    y2_i = min(y2_1, y2_2)
    
    if x2_i < x1_i or y2_i < y1_i:
        return 0.0
    
    intersection = (x2_i - x1_i) * (y2_i - y1_i)
    area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
    area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
    union = area1 + area2 - intersection
    
    return intersection / union
    """
```

### Алгоритм стандартизации размера

**ВАЖНО**: Размер места зависит от размера найденной машины!

Камеры смотрят под разными углами и с разных высот, поэтому одна и та же машина имеет разный размер в пикселях. Вместо единого стандартного размера используется ПРОЦЕНТНЫЙ ЗАПАС от размера найденной машины.

```python
def standardize_bbox(original_bbox, margin_percent_w=120, margin_percent_h=120):
    """
    Применяет процентный запас к bbox машины.
    
    Args:
        margin_percent_w: 120 = 120% = +20% запас по ширине
        margin_percent_h: 120 = 120% = +20% запас по высоте
    
    x1, y1, x2, y2 = original_bbox
    
    # Размер найденной машины
    detected_width = x2 - x1
    detected_height = y2 - y1
    
    # Применить процентный запас
    margin_factor_w = margin_percent_w / 100.0  # 1.2
    margin_factor_h = margin_percent_h / 100.0  # 1.2
    
    new_width = detected_width * margin_factor_w
    new_height = detected_height * margin_factor_h
    
    # Центр остается тот же
    center_x = (x1 + x2) // 2
    center_y = (y1 + y2) // 2
    
    # Построить rect с запасом вокруг центра
    new_x1 = center_x - new_width // 2
    new_x2 = center_x + new_width // 2
    new_y1 = center_y - new_height // 2
    new_y2 = center_y + new_height // 2
    
    return {
        "x1": new_x1,
        "y1": new_y1,
        "x2": new_x2,
        "y2": new_y2
    }
    """
```

**Примеры:**

```
Машина близко к камере: bbox = (100, 200, 400, 700)
├── Ширина = 300px, Высота = 500px
├── С запасом 120%: Ширина = 360px, Высота = 600px
└── Место будет 360x600 пикселей

Машина далеко от камеры: bbox = (500, 400, 580, 520)  
├── Ширина = 80px, Высота = 120px
├── С запасом 120%: Ширина = 96px, Высота = 144px
└── Место будет 96x144 пикселей

ТА ЖЕ ФИЗИЧЕСКАЯ МАШИНА, но РАЗНЫЙ РАЗМЕР В ПИКСЕЛЯХ!
```

### Алгоритм проверки валидности

```python
def check_validity(bbox, suggested_rect, frame_width=1920, frame_height=1080):
    """
    Критерии исключения:
    
    1. Слишком близко к краю (<10px)
       if x1 < 10 or y1 < 10 or x2 > width-10 or y2 > height-10:
           return False, "Слишком близко к краю"
    
    2. Выходит за границы
       if x1 < 0 or y1 < 0 or x2 > width or y2 > height:
           return False, "Выходит за границы"
    
    3. Слишком маленький
       if (x2-x1) < 50 or (y2-y1) < 50:
           return False, "Слишком маленький"
    
    return True, None
    """
```

---

## 9. State Management (Управление состоянием)

### StateManager

```python
class StateManager:
    """Управляет состоянием парковочных мест."""
    
    store: JSONStore
    lock: threading.Lock
    event_callbacks: List[Callable]
    
    # Методы для Spots
    def update_spot_state(spot_id, state_update)
        """Обновить состояние одного места."""
    
    def update_multiple_spots(updates: Dict[str, Dict])
        """Пакетное обновление мест."""
    
    def get_space_state(space_id) -> Dict
        """Получить состояние зоны."""
    
    def get_spot_details(space_id) -> List[Dict]
        """Получить детали всех мест в зоне."""
    
    # Агрегация
    def _recalculate_space_stats(state_data, space_id)
        """Пересчитать статистику зоны."""
        # total_spots = количество parking spots
        # occupied_spots = количество с occupied=true
        # free_spots = total - occupied
```

### State структура
```json
{
    "spaces": {
        "space_abc123": {
            "total_spots": 25,
            "occupied_spots": 12,
            "free_spots": 13,
            "spots": {
                "spot_xyz789": {
                    "occupied": true,
                    "detected_at": "2025-11-13T18:25:00Z",
                    "occupied_since": "2025-11-13T18:30:00Z",
                    "sequential_number": 5
                }
            }
        }
    }
}
```

---

## 10. Примеры использования

### Пример 1: Создание зоны с множественными камерами

```python
# 1. Создать парковочную зону
space = {
    "id": "space_parking_yard",
    "name": "Двор - Парковка",
    "camera_ids": [],
    "next_spot_number": 1
}
store.save_spaces([space])

# 2. Добавить камеры
camera1 = {
    "id": "cam_entrance",
    "name": "Въезд",
    "rtsp_url": "rtsp://...",
    "assigned_space_ids": ["space_parking_yard"]
}

camera2 = {
    "id": "cam_side",
    "name": "Боковой вид",
    "rtsp_url": "rtsp://...",
    "assigned_space_ids": ["space_parking_yard"]
}

# 3. Связать камеры с зоной
space["camera_ids"] = ["cam_entrance", "cam_side"]
```

### Пример 2: Автоматическая разметка

```python
# 1. Запустить анализ
session_id = auto_markup_service.start_analysis(
    space_id="space_parking_yard",
    mode="average",
    standard_spot_width=200,
    standard_spot_height=300,
    stability_seconds=30
)

# 2. Дождаться завершения
while True:
    progress = auto_markup_service.get_analysis_progress(session_id)
    if progress['status'] == 'completed':
        break
    time.sleep(1)

# 3. Получить предложения
proposals = auto_markup_service.get_proposals(session_id)
# proposals['proposals'] = [
#     {"index": 0, "suggested_label": "1", "is_valid": true, ...},
#     {"index": 1, "suggested_label": "2", "is_valid": true, ...},
#     {"index": 2, "suggested_label": "3", "is_valid": false, ...},  # исключено
# ]

# 4. Применить одобренные (0 и 1)
result = auto_markup_service.apply_proposals(
    session_id=session_id,
    approved_indices=[0, 1],
    label_prefix="A",
    auto_number=True
)
# result = {"created_spots": 2, "spot_ids": ["spot_...", "spot_..."]}

# Созданы места:
# - Spot A1 (spot_number=1)
# - Spot A2 (spot_number=2)
# Space.next_spot_number стал = 3
```

### Пример 3: Добавление альтернативного ракурса

```python
# Есть место созданное с cam_1
spot = {
    "id": "spot_A1",
    "camera_id": "cam_entrance",
    "rect": {"x1": 100, "y1": 200, "x2": 300, "y2": 500},
    "alternative_views": []
}

# Обнаружили это же место на cam_2 с другими координатами
# (вручную или через другую сессию auto-markup)

spot["alternative_views"].append({
    "camera_id": "cam_side",
    "rect": {"x1": 450, "y1": 180, "x2": 650, "y2": 480}
})

# Теперь система будет проверять занятость на ОБОИХ ракурсах
```

### Пример 4: Детекция с множественными ракурсами

```python
# В detection loop
for spot in spots:
    space = get_space(spot["space_id"])
    
    # Проверить на основной камере
    if spot["camera_id"] in space["camera_ids"]:
        frame = video_manager.get_frame(spot["camera_id"])
        occupied = detector.detect_in_roi(frame, spot["rect"])
    
    # Проверить альтернативные ракурсы
    for alt_view in spot.get("alternative_views", []):
        if alt_view["camera_id"] in space["camera_ids"]:
            frame = video_manager.get_frame(alt_view["camera_id"])
            occupied_alt = detector.detect_in_roi(frame, alt_view["rect"])
            occupied = occupied or occupied_alt  # Занято если хоть на одном ракурсе
```

---

## 11. Диаграмма классов (UML-подобная)

```
┌─────────────────────────────┐
│       JSONStore             │
│  ─────────────────────────  │
│  + get_cameras()            │
│  + get_spaces()             │
│  + get_spots()              │
│  + get_config()             │
│  + update_config()          │
└─────────────────────────────┘
         △
         │ uses
         │
┌─────────────────────────────┐      ┌─────────────────────────────┐
│   VideoProcessorManager     │      │        Detector             │
│  ─────────────────────────  │      │  ─────────────────────────  │
│  + add_camera()             │      │  + detect(frame)            │
│  + get_frame(camera_id)     │      │  + detect_in_roi()          │
│  + is_camera_alive()        │      │  + get_detections_in_rois() │
└─────────────────────────────┘      └─────────────────────────────┘
         △                                      △
         │                                      │
         │ uses                                 │ uses
         │                                      │
┌─────────────────────────────────────────────────────────────────┐
│                   AutoMarkupService                              │
│  ──────────────────────────────────────────────────────────────  │
│  - tracker: VehicleTracker                                       │
│  - sessions: Dict[str, AutoMarkupSession]                        │
│                                                                   │
│  + start_analysis(space_id, mode, ...)  → session_id            │
│  + get_analysis_progress(session_id)    → Dict                   │
│  + get_proposals(session_id)            → List[SpotProposal]     │
│  + apply_proposals(session_id, indices) → Dict                   │
└─────────────────────────────────────────────────────────────────┘
         │
         │ contains
         │
         ▼
┌─────────────────────────────┐      ┌─────────────────────────────┐
│     VehicleTracker          │      │   AutoMarkupSession         │
│  ─────────────────────────  │      │  ─────────────────────────  │
│  + add_frame_detections()   │      │  - proposals: []            │
│  + get_stable_vehicles()    │      │  - status: str              │
│  - _group_detections()      │      │  - progress: int            │
│  - _calculate_iou()         │      │  - preview_frame: ndarray   │
└─────────────────────────────┘      └─────────────────────────────┘
```

---

## 12. Важные константы и настройки

### Детекция
```python
VEHICLE_CLASSES = ['car', 'truck', 'bus', 'motorcycle']
DEFAULT_CONFIDENCE_THRESHOLD = 0.5
IoU_THRESHOLD_FOR_GROUPING = 0.7
IoU_THRESHOLD_FOR_OVERLAP = 0.3
```

### Стабильность
```python
DEFAULT_STABILITY_SECONDS = 30      # Минимальное время стабильности
STABILITY_PRESENCE_THRESHOLD = 0.8  # Должна быть на 80% кадров
```

### Размеры по умолчанию
```python
DEFAULT_SPOT_WIDTH = 200            # пикселей
DEFAULT_SPOT_HEIGHT = 300           # пикселей
EDGE_MARGIN = 10                    # отступ от края кадра
MIN_SPOT_SIZE = 50                  # минимальный размер
```

### Режимы анализа
```python
MODE_SINGLE = {
    'frames': 1,
    'interval': 0,
    'duration': 1  # секунда
}

MODE_AVERAGE = {
    'frames': 30,
    'interval': 1,  # секунда
    'duration': 30  # секунд
}

MODE_DURATION = {
    'frames': 'variable',
    'interval': 5,  # секунд
    'duration': 'user_defined'  # 60-600 секунд
}
```

---

## 13. Обработка ошибок

### Типичные ошибки и их обработка

```python
# 1. Камера недоступна
if not video_manager.is_camera_alive(camera_id):
    raise RuntimeError("Camera not available")

# 2. Нет детекций
if len(detections) == 0:
    return []  # Вернуть пустой список предложений

# 3. Все предложения невалидны
valid_proposals = [p for p in proposals if p.is_valid]
if len(valid_proposals) == 0:
    # Уведомить пользователя

# 4. Timeout блокировки файла
try:
    store.update_state(...)
except TimeoutError:
    # Повторить или вернуть ошибку

# 5. Сессия не найдена
session = sessions.get(session_id)
if not session:
    return 404
```

---

## 14. Производительность и оптимизация

### Оптимизации детекции
```python
# Детектировать один раз, проверить все ROI
detections = detector.detect(frame)  # 1 проход YOLO

for roi in all_rois:
    has_vehicle = any(
        detector._bbox_intersects_roi(d.bbox, roi) 
        for d in detections
    )
```

### Кэширование кадров
```python
# VideoProcessor хранит latest_frame в памяти
# Множественные запросы используют один кадр
frame = video_manager.get_frame(camera_id)  # Быстро, из RAM
```

### Асинхронный анализ
```python
# Анализ запускается в отдельном потоке
threading.Thread(target=_run_analysis, daemon=True).start()

# Frontend опрашивает прогресс через AJAX
setInterval(() => checkProgress(), 1000)
```

---

## Резюме

Эта документация описывает полную архитектуру системы с акцентом на:

1. **Камеры** - захват RTSP потоков
2. **Детекция** - YOLO распознавание транспорта
3. **Зоны** - логическая группировка мест
4. **Места** - конкретные парковочные позиции
5. **Автоматическая разметка** - AI-помощь в настройке
6. **Множественные ракурсы** - поддержка нескольких камер на одно место
7. **Сквозная нумерация** - единая система нумерации для зоны

Система спроектирована для масштабирования: от маленькой парковки (1 камера, 10 мест) до большой (10+ камер, 100+ мест).

