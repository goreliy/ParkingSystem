# План реализации системы мониторинга парковки

## Обзор

Система мониторинга парковочного пространства на базе Flask с использованием YOLOv8/v12 для детекции транспортных средств, JSON-хранилищем данных, веб-интерфейсом реального времени и интеграцией с Telegram-ботом для удалённого управления и стриминга.

## Архитектура системы

### Основные компоненты

1. **Backend (Flask)** - веб-сервер и REST API
2. **Video Processing** - захват RTSP-потоков и буферизация кадров
3. **YOLO Detector** - распознавание транспортных средств
4. **Occupancy Tracker** - логика определения занятости с таймерами
5. **State Manager** - управление состоянием парковочных мест
6. **JSON Storage** - атомарное хранение данных с блокировками
7. **Telegram Bot** - удалённое управление и мониторинг
8. **Stream Manager** - RTMP-стриминг через FFmpeg в Telegram

### Структура проекта

```
parking-monitor/
├── backend/
│   ├── api/                    # REST API endpoints
│   │   ├── cameras.py         # CRUD для камер
│   │   ├── spaces.py          # CRUD для парковочных пространств
│   │   ├── spots.py           # CRUD для парковочных мест
│   │   ├── config.py          # Управление конфигурацией
│   │   └── stream.py          # Снапшоты, SSE, управление стримом
│   ├── bot/                   # Telegram интеграция
│   │   ├── telebot_runner.py # Telegram бот с командами
│   │   └── stream_manager.py # FFmpeg стриминг менеджер
│   ├── services/              # Бизнес-логика
│   │   ├── video_processor.py # Захват RTSP и буферизация
│   │   ├── detector.py        # YOLO обёртка
│   │   ├── occupancy.py       # Логика занятости
│   │   └── state.py           # Управление состоянием
│   ├── storage/               # Хранилище данных
│   │   └── json_store.py      # JSON с блокировками
│   ├── templates/             # HTML шаблоны
│   │   ├── base.html          # Базовый шаблон
│   │   ├── index.html         # Главная страница
│   │   ├── dashboard.html     # Дашборд мониторинга
│   │   ├── setup.html         # Настройка камер/мест
│   │   └── config.html        # Конфигурация системы
│   └── app.py                 # Точка входа приложения
├── data/                      # JSON файлы данных
│   ├── cameras.json           # Камеры
│   ├── spaces.json            # Парковочные пространства
│   ├── spots.json             # Парковочные места
│   ├── state.json             # Текущее состояние
│   └── config.json            # Конфигурация
├── logs/                      # Логи приложения
│   └── parking.log
├── models/                    # Документация схем
│   └── schemas.md
├── deploy/                    # Конфигурации развёртывания
│   └── systemd/
│       └── parking.service    # Linux systemd unit
├── requirements.txt           # Python зависимости
├── run_windows.ps1            # Скрипт запуска для Windows
├── run_linux.sh               # Скрипт запуска для Linux
├── README.md                  # Документация
└── plan.md                    # Этот файл
```

## Реализованные функции

### 1. Управление камерами

✅ **Добавление камер**
- REST API: `POST /api/cameras`
- Поля: name, rtsp_url
- Автоматический старт video processor

✅ **Просмотр и удаление камер**
- REST API: `GET/DELETE /api/cameras/{id}`
- Статус подключения (alive/dead)

✅ **Автоматическое переподключение**
- При потере соединения автоматический реконнект через 5 секунд
- Буферизация последнего кадра в памяти

### 2. Управление парковочными пространствами

✅ **Создание пространств**
- REST API: `POST /api/spaces`
- Назначение камер к пространствам

✅ **Настройка парковочных мест**
- Типы мест: parking / nopark
- Прямоугольные области (x1,y1;x2,y2)
- Графический интерфейс для разметки
- Клик по изображению для выбора координат

### 3. Детекция транспортных средств

✅ **YOLO интеграция**
- Поддержка YOLOv8 (n/s/m/l/x)
- Фильтрация по классам: car, truck, bus, motorcycle
- Настраиваемый порог уверенности (confidence threshold)

✅ **ROI detection**
- Проверка пересечения bbox с областями мест
- Пороговое значение площади пересечения (30%)

### 4. Логика занятости

✅ **Таймер-based детекция**
- Настраиваемый порог (по умолчанию 5 минут)
- Автоматическая фиксация статуса после превышения порога

✅ **Сквозная нумерация**
- Автоматическое присвоение порядковых номеров занятым местам
- Сброс номера при освобождении

✅ **Агрегированная статистика**
- Подсчёт total/occupied/free мест по пространствам
- Обновление в реальном времени

### 5. Web интерфейс

✅ **Dashboard**
- Обзор всех парковочных пространств
- Детальный просмотр по выбранному пространству
- Таблица мест со статусами
- Аннотированные изображения с разметкой

✅ **Setup**
- Управление камерами (добавление/удаление)
- Управление пространствами
- Графический редактор парковочных мест
- Назначение камер к пространствам

✅ **Configuration**
- Настройка Telegram бота (токен, чаты)
- Настройка стриминга (targets, FFmpeg)
- Параметры детекции (occupancy_minutes, confidence, update_hz)
- Статус активного стрима

✅ **Real-time updates**
- Server-Sent Events (SSE) для live-обновлений
- Автоматическое обновление снапшотов каждые 5 секунд

### 6. REST API

✅ **Cameras API**
- `GET /api/cameras` - список камер
- `POST /api/cameras` - создание
- `PUT /api/cameras/{id}` - обновление
- `DELETE /api/cameras/{id}` - удаление

✅ **Spaces API**
- `GET /api/spaces` - список пространств
- `POST /api/spaces` - создание
- `POST /api/spaces/{id}/assign_camera` - назначение камеры

✅ **Spots API**
- `GET /api/spots?space_id=` - список мест
- `POST /api/spots` - создание места
- `PUT /api/spots/{id}` - обновление
- `DELETE /api/spots/{id}` - удаление

✅ **State API**
- `GET /api/state` - сводка по всем пространствам
- `GET /api/state/spaces/{id}` - детали пространства
- `GET /api/events` - SSE stream

✅ **Snapshots API**
- `GET /api/snapshot/camera/{id}` - кадр с камеры
- `GET /api/snapshot/space/{id}?annotated=1` - аннотированный кадр

✅ **Config API**
- `GET/PUT /api/config/bot` - конфигурация бота
- `GET/PUT /api/config/streaming` - конфигурация стриминга
- `PUT /api/config/occupancy` - параметры детекции

### 7. Telegram Bot

✅ **Базовые команды (пользователи)**
- `/start` - регистрация чата
- `/help` - список команд
- `/spaces` - список пространств со статистикой
- `/space <id>` - детали пространства
- `/image_camera <id>` - снимок с камеры
- `/image_space <id>` - аннотированный снимок пространства

✅ **Админ-команды**
- `/add_camera <name> <rtsp_url>` - добавить камеру
- `/list_cameras` - список камер
- `/add_space <name>` - создать пространство
- `/assign_camera <space_id> <camera_id>` - назначить камеру
- `/add_spot <space_id> <type> <label> <x1,y1;x2,y2>` - добавить место
- `/move_spot <spot_id> <x1,y1;x2,y2>` - переместить место
- `/delete_spot <spot_id>` - удалить место
- `/set_occupancy_minutes <N>` - изменить порог занятости

✅ **Стриминг-команды (админы)**
- `/start_stream <camera_id> [target]` - запустить стрим в Telegram
- `/stop_stream` - остановить активный стрим
- `/stream_status` - статус стрима

✅ **Управление доступом**
- Автоматическая регистрация чатов при `/start`
- Установка прав admin через Web UI
- Разграничение команд по правам

### 8. RTMP Streaming

✅ **FFmpeg интеграция**
- Запуск FFmpeg процессов для стриминга
- Предпочтение копированию без перекодирования (`-c:v copy`)
- Фолбэк на перекодирование при необходимости

✅ **Управление стримами**
- Глобальная блокировка "только один активный стрим"
- Watchdog для мониторинга процесса FFmpeg
- Автоочистка состояния при падении процесса

✅ **Кросс-платформенность**
- Windows: `CREATE_NEW_PROCESS_GROUP`
- Linux: `setsid` для групп процессов
- Корректное завершение через `terminate`/`SIGTERM`

✅ **Конфигурация targets**
- Алиасы для целей стриминга
- RTMP URL и stream key
- Chat ID для группы/канала
- Управление через Web UI

### 9. JSON Storage

✅ **Атомарное хранение**
- Блокировки через `portalocker`
- Транзакционные обновления с функциями-updater
- Автоматическое создание файлов с дефолтными значениями

✅ **Схемы данных**
- `config.json` - конфигурация системы
- `cameras.json` - камеры
- `spaces.json` - пространства
- `spots.json` - парковочные места
- `state.json` - текущее состояние и активный стрим

### 10. Логирование

✅ **Структурированные логи**
- Файл: `logs/parking.log`
- Console output
- Уровни: INFO, WARNING, ERROR
- Timestamps и имена модулей

✅ **Логирование событий**
- Подключение/отключение камер
- Изменения статусов мест
- Старт/стоп стримов
- Ошибки детекции и обработки

### 11. Кросс-платформенность

✅ **Windows**
- PowerShell скрипт `run_windows.ps1`
- Автоматическое создание venv
- Проверка Python и FFmpeg
- Установка зависимостей

✅ **Linux**
- Bash скрипт `run_linux.sh`
- Поддержка systemd service
- `/deploy/systemd/parking.service`
- Логирование в syslog

✅ **Универсальный код**
- `pathlib` для путей
- `portalocker` для блокировок
- `os.name` для platform-specific logic

## Технологический стек

### Backend
- **Flask** - веб-фреймворк
- **gevent** - WSGI сервер и SSE
- **OpenCV** - захват и обработка видео
- **Ultralytics (YOLO)** - детекция объектов
- **portalocker** - файловые блокировки
- **pyTelegramBotAPI** - Telegram интеграция

### Frontend
- **Vanilla JavaScript** - без фреймворков
- **SSE** - real-time обновления
- **Fetch API** - REST клиент
- **CSS Grid/Flexbox** - responsive layout

### External Tools
- **FFmpeg** - видео кодирование и стриминг
- **RTSP** - протокол захвата видео
- **RTMP** - протокол стриминга в Telegram

## Workflow системы

### 1. Инициализация
1. Загрузка конфигурации из JSON
2. Инициализация JSON Store
3. Создание Video Processor Manager
4. Загрузка YOLO модели
5. Инициализация State Manager
6. Старт камер из конфигурации
7. Запуск detection loop
8. Старт Telegram бота
9. Запуск Flask сервера

### 2. Detection Loop
1. Получение списка мест (spots)
2. Группировка по пространствам и камерам
3. Захват кадров с камер
4. Детекция YOLO по ROI
5. Обновление OccupancyTracker
6. Применение изменений через StateManager
7. Broadcast событий через SSE
8. Пауза согласно `update_hz`

### 3. Real-time Updates
1. Клиент подключается к `/api/events` (SSE)
2. State Manager регистрирует callback
3. При изменении состояния вызывается callback
4. Событие помещается в очереди всех клиентов
5. SSE доставляет событие клиенту
6. JavaScript обновляет UI

### 4. Streaming Workflow
1. Админ отправляет `/start_stream` в Telegram
2. Bot проверяет права и активные стримы
3. Stream Manager проверяет блокировку
4. Получение RTSP URL камеры и RTMP target
5. Запуск FFmpeg процесса
6. Сохранение info в `state.json`
7. Watchdog мониторит процесс
8. При `/stop_stream` или падении - очистка

### 5. Telegram Bot Workflow
1. Пользователь отправляет `/start`
2. Бот регистрирует chat_id в `config.json`
3. Оператор выставляет `is_admin` в Web UI
4. Админ получает доступ к расширенным командам
5. Команды вызывают методы Store/Manager
6. Результат возвращается в чат

## Особенности реализации

### 1. Thread Safety
- Все обновления JSON через блокировки
- Video processors в отдельных потоках
- Detection loop в отдельном потоке
- Telegram bot polling в отдельном потоке
- Lock'и в VideoProcessorManager и StateManager

### 2. Error Handling
- Try-catch во всех API endpoints
- Автореконнект для RTSP
- Watchdog для FFmpeg процессов
- Graceful shutdown всех компонентов

### 3. Performance
- Буферизация только последнего кадра (не все)
- Batch detection по ROI
- Настраиваемая частота обновления
- Lazy loading YOLO модели

### 4. Scalability
- Неограниченное количество камер (в пределах ресурсов)
- Неограниченное количество пространств
- Неограниченное количество мест
- JSON-файлы масштабируются до ~1000 записей

## Ограничения и будущие улучшения

### Текущие ограничения
- JSON storage (не подходит для >1000 камер)
- Один стрим одновременно
- Нет истории событий (только текущее состояние)
- Нет аутентификации в Web UI
- CPU-only YOLO (без GPU по умолчанию)

### Возможные улучшения
- [ ] База данных (PostgreSQL/MongoDB) вместо JSON
- [ ] Множественные стримы
- [ ] История событий и аналитика
- [ ] Аутентификация в Web UI (JWT/OAuth)
- [ ] GPU acceleration для YOLO
- [ ] Кластеризация для масштабирования
- [ ] WebRTC вместо RTMP
- [ ] Mobile приложение
- [ ] Push-уведомления через Telegram
- [ ] Экспорт отчётов (PDF/Excel)

## Тестирование

### Ручное тестирование
1. Создать камеру с тестовым RTSP URL
2. Создать пространство
3. Назначить камеру пространству
4. Разметить парковочные места
5. Проверить детекцию транспорта
6. Проверить таймер занятости
7. Протестировать Telegram команды
8. Протестировать стриминг

### Проверка компонентов
- Video capture: VLC с тем же RTSP URL
- YOLO detection: проверка логов
- SSE: DevTools → Network → EventStream
- FFmpeg: `ps aux | grep ffmpeg` (Linux)

## Развёртывание

### Development
```bash
# Windows
.\run_windows.ps1

# Linux
./run_linux.sh
```

### Production (Linux)
```bash
# Установка
sudo cp deploy/systemd/parking.service /etc/systemd/system/
sudo systemctl enable parking
sudo systemctl start parking

# Мониторинг
sudo systemctl status parking
sudo journalctl -u parking -f
```

### Docker (будущее)
```dockerfile
FROM python:3.10-slim
# ... установка зависимостей
EXPOSE 5000
CMD ["python", "backend/app.py"]
```

## Заключение

Система полностью реализована согласно ТЗ со всеми основными функциями:

✅ Управление камерами и RTSP  
✅ Распознавание транспортных средств (YOLO)  
✅ Логика занятости с таймерами  
✅ Веб-интерфейс реального времени  
✅ REST API  
✅ Telegram бот с админ-командами  
✅ RTMP стриминг в Telegram  
✅ JSON хранилище  
✅ Кросс-платформенность (Windows + Linux)  
✅ Документация и скрипты запуска  

Система готова к использованию и тестированию.

---

**Дата создания:** 2025-11-12  
**Версия:** 1.0.0  
**Статус:** ✅ Completed

