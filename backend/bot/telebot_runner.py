"""
Telegram bot implementation with telebot (pyTelegramBotAPI).
"""
import logging
import threading
import time
from typing import Optional
import io
import cv2
import telebot
from telebot import types

logger = logging.getLogger(__name__)


class TelebotRunner:
    """Manages Telegram bot with long polling."""
    
    def __init__(self, store, video_manager, state_manager, stream_manager):
        self.store = store
        self.video_manager = video_manager
        self.state_manager = state_manager
        self.stream_manager = stream_manager
        self.bot: Optional[telebot.TeleBot] = None
        self.polling_thread: Optional[threading.Thread] = None
        self.running = False
        self.current_token = None
    
    def start(self):
        """Start or restart bot with token from config."""
        config = self.store.get_config()
        bot_token = config.get('bot_token', '')
        
        if not bot_token:
            logger.warning("Bot token not configured")
            return False
        
        # Check if token changed
        if bot_token == self.current_token and self.running:
            logger.info("Bot already running with same token")
            return True
        
        # Stop existing bot if running
        if self.running:
            self.stop()
        
        try:
            self.bot = telebot.TeleBot(bot_token, parse_mode='HTML')
            self.current_token = bot_token
            self._register_handlers()
            
            # Start polling in separate thread
            self.running = True
            self.polling_thread = threading.Thread(target=self._polling_loop, daemon=True)
            self.polling_thread.start()
            
            logger.info("Telegram bot started")
            return True
        
        except Exception as e:
            logger.error(f"Failed to start bot: {e}")
            self.bot = None
            self.current_token = None
            return False
    
    def stop(self):
        """Stop bot."""
        if not self.running:
            return
        
        self.running = False
        
        if self.bot:
            try:
                self.bot.stop_polling()
            except:
                pass
            self.bot = None
        
        if self.polling_thread:
            self.polling_thread.join(timeout=5)
        
        self.current_token = None
        logger.info("Telegram bot stopped")
    
    def _polling_loop(self):
        """Main polling loop with auto-reconnect."""
        while self.running:
            try:
                logger.info("Starting bot polling...")
                self.bot.polling(none_stop=True, interval=1, timeout=30)
            except Exception as e:
                if self.running:
                    logger.error(f"Bot polling error: {e}")
                    time.sleep(5)
                else:
                    break
    
    def _register_handlers(self):
        """Register all bot command handlers."""
        
        @self.bot.message_handler(commands=['start'])
        def handle_start(message):
            self._register_chat(message)
            self.bot.reply_to(
                message,
                "🅿️ <b>Бот Мониторинга Парковки</b>\n\n"
                "Используйте /help для просмотра доступных команд."
            )
        
        @self.bot.message_handler(commands=['help'])
        def handle_help(message):
            self._register_chat(message)
            is_admin = self._is_admin(message.chat.id)
            
            help_text = (
                "📋 <b>Доступные команды:</b>\n\n"
                "<b>Общие:</b>\n"
                "/spaces - Список всех парковочных зон\n"
                "/space &lt;id&gt; - Детали зоны\n"
                "/image_camera &lt;id&gt; - Снимок с камеры\n"
                "/image_space &lt;id&gt; - Снимок зоны с разметкой\n"
            )
            
            if is_admin:
                help_text += (
                    "\n<b>Админ команды:</b>\n"
                    "/add_camera &lt;название&gt; &lt;rtsp_url&gt; - Добавить камеру\n"
                    "/list_cameras - Список камер\n"
                    "/add_space &lt;название&gt; - Добавить парковочную зону\n"
                    "/assign_camera &lt;space_id&gt; &lt;camera_id&gt; - Назначить камеру\n"
                    "/add_spot &lt;space_id&gt; &lt;тип&gt; &lt;метка&gt; &lt;x1,y1;x2,y2&gt; - Добавить место\n"
                    "/move_spot &lt;spot_id&gt; &lt;x1,y1;x2,y2&gt; - Переместить место\n"
                    "/delete_spot &lt;spot_id&gt; - Удалить место\n"
                    "/set_occupancy_minutes &lt;N&gt; - Установить порог занятости\n"
                    "/start_stream &lt;camera_id&gt; [target] - Запустить стрим\n"
                    "/stop_stream - Остановить активный стрим\n"
                    "/stream_status - Проверить статус стрима\n"
                )
            
            self.bot.reply_to(message, help_text)
        
        @self.bot.message_handler(commands=['spaces'])
        def handle_spaces(message):
            self._register_chat(message)
            try:
                summary = self.state_manager.get_all_spaces_summary()
                
                if not summary:
                    self.bot.reply_to(message, "Парковочные зоны не настроены.")
                    return
                
                text = "🅿️ <b>Парковочные зоны:</b>\n\n"
                for space in summary:
                    text += (
                        f"<b>{space['name']}</b> (ID: {space['id']})\n"
                        f"  📊 Свободно: {space['free_spots']}/{space['total_spots']}\n"
                        f"  🚗 Занято: {space['occupied_spots']}\n\n"
                    )
                
                self.bot.reply_to(message, text)
            except Exception as e:
                logger.error(f"Error in /spaces: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['space'])
        def handle_space(message):
            self._register_chat(message)
            try:
                args = message.text.split(maxsplit=1)
                if len(args) < 2:
                    self.bot.reply_to(message, "Использование: /space <space_id>")
                    return
                
                space_id = args[1]
                spots = self.state_manager.get_spot_details(space_id)
                space_state = self.state_manager.get_space_state(space_id)
                
                if not space_state:
                    self.bot.reply_to(message, "Зона не найдена.")
                    return
                
                text = f"🅿️ <b>Детали зоны:</b>\n\n"
                text += f"Всего: {space_state['total_spots']}\n"
                text += f"Свободно: {space_state['free_spots']}\n"
                text += f"Занято: {space_state['occupied_spots']}\n\n"
                
                if spots:
                    text += "<b>Места:</b>\n"
                    for spot in spots:
                        if spot['type'] == 'parking':
                            status = "🔴 Занято" if spot['occupied'] else "🟢 Свободно"
                            seq = f" #{spot['sequential_number']}" if spot.get('sequential_number') else ""
                            text += f"{spot['label']}: {status}{seq}\n"
                
                self.bot.reply_to(message, text)
            except Exception as e:
                logger.error(f"Error in /space: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['image_camera'])
        def handle_image_camera(message):
            self._register_chat(message)
            try:
                args = message.text.split(maxsplit=1)
                if len(args) < 2:
                    self.bot.reply_to(message, "Использование: /image_camera <camera_id>")
                    return
                
                camera_id = args[1]
                frame = self.video_manager.get_frame(camera_id)
                
                if frame is None:
                    self.bot.reply_to(message, "Камера недоступна или нет кадра.")
                    return
                
                # Encode as JPEG
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                bio = io.BytesIO(buffer.tobytes())
                
                self.bot.send_photo(message.chat.id, bio)
            except Exception as e:
                logger.error(f"Error in /image_camera: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['image_space'])
        def handle_image_space(message):
            self._register_chat(message)
            try:
                args = message.text.split(maxsplit=1)
                if len(args) < 2:
                    self.bot.reply_to(message, "Использование: /image_space <space_id>")
                    return
                
                space_id = args[1]
                
                # Get annotated image (similar to API endpoint)
                spaces = self.store.get_spaces()
                space = next((s for s in spaces if s['id'] == space_id), None)
                
                if not space or not space.get('camera_ids'):
                    self.bot.reply_to(message, "Зона не найдена или не назначена камера.")
                    return
                
                camera_id = space['camera_ids'][0]
                frame = self.video_manager.get_frame(camera_id)
                
                if frame is None:
                    self.bot.reply_to(message, "Камера недоступна.")
                    return
                
                # Annotate frame
                spots = self.store.get_spots()
                space_spots = [s for s in spots if s['space_id'] == space_id]
                spot_states = self.state_manager.get_spot_details(space_id)
                state_lookup = {s['id']: s for s in spot_states}
                
                for spot in space_spots:
                    rect = spot['rect']
                    x1, y1, x2, y2 = rect['x1'], rect['y1'], rect['x2'], rect['y2']
                    state = state_lookup.get(spot['id'], {})
                    occupied = state.get('occupied', False)
                    
                    if spot['type'] == 'nopark':
                        color = (255, 0, 0)
                    elif occupied:
                        color = (0, 0, 255)
                    else:
                        color = (0, 255, 0)
                    
                    cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                    label = spot['label']
                    if occupied and state.get('sequential_number'):
                        label += f" #{state['sequential_number']}"
                    cv2.putText(frame, label, (x1, y1-5), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
                
                _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                bio = io.BytesIO(buffer.tobytes())
                
                self.bot.send_photo(message.chat.id, bio)
            except Exception as e:
                logger.error(f"Error in /image_space: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        # Admin commands
        @self.bot.message_handler(commands=['add_camera'])
        def handle_add_camera(message):
            if not self._check_admin(message):
                return
            
            try:
                args = message.text.split(maxsplit=2)
                if len(args) < 3:
                    self.bot.reply_to(message, "Использование: /add_camera <название> <rtsp_url>")
                    return
                
                name, rtsp_url = args[1], args[2]
                
                # Use API logic
                import uuid
                camera_id = f"cam_{uuid.uuid4().hex[:8]}"
                cameras = self.store.get_cameras()
                cameras.append({
                    'id': camera_id,
                    'name': name,
                    'rtsp_url': rtsp_url,
                    'assigned_space_ids': []
                })
                self.store.save_cameras(cameras)
                self.video_manager.add_camera(camera_id, rtsp_url)
                
                self.bot.reply_to(message, f"✅ Камера добавлена: {camera_id}")
            except Exception as e:
                logger.error(f"Error in /add_camera: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['list_cameras'])
        def handle_list_cameras(message):
            if not self._check_admin(message):
                return
            
            try:
                cameras = self.store.get_cameras()
                if not cameras:
                    self.bot.reply_to(message, "Камеры не настроены.")
                    return
                
                text = "📹 <b>Камеры:</b>\n\n"
                for cam in cameras:
                    alive = "🟢" if self.video_manager.is_camera_alive(cam['id']) else "🔴"
                    text += f"{alive} <b>{cam['name']}</b> (ID: {cam['id']})\n"
                
                self.bot.reply_to(message, text)
            except Exception as e:
                logger.error(f"Error in /list_cameras: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['add_space'])
        def handle_add_space(message):
            if not self._check_admin(message):
                return
            
            try:
                args = message.text.split(maxsplit=1)
                if len(args) < 2:
                    self.bot.reply_to(message, "Использование: /add_space <название>")
                    return
                
                name = args[1]
                import uuid
                space_id = f"space_{uuid.uuid4().hex[:8]}"
                spaces = self.store.get_spaces()
                spaces.append({
                    'id': space_id,
                    'name': name,
                    'camera_ids': [],
                    'next_spot_number': 1,
                    'spot_numbering_scheme': 'sequential'
                })
                self.store.save_spaces(spaces)
                self.state_manager.initialize_space(space_id)
                
                self.bot.reply_to(message, f"✅ Зона добавлена: {space_id}")
            except Exception as e:
                logger.error(f"Error in /add_space: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['assign_camera'])
        def handle_assign_camera(message):
            if not self._check_admin(message):
                return
            
            try:
                args = message.text.split()
                if len(args) < 3:
                    self.bot.reply_to(message, "Использование: /assign_camera <space_id> <camera_id>")
                    return
                
                space_id, camera_id = args[1], args[2]
                spaces = self.store.get_spaces()
                cameras = self.store.get_cameras()
                
                space = next((s for s in spaces if s['id'] == space_id), None)
                camera = next((c for c in cameras if c['id'] == camera_id), None)
                
                if not space or not camera:
                    self.bot.reply_to(message, "Зона или камера не найдены.")
                    return
                
                if camera_id not in space['camera_ids']:
                    space['camera_ids'].append(camera_id)
                if space_id not in camera['assigned_space_ids']:
                    camera['assigned_space_ids'].append(space_id)
                
                self.store.save_spaces(spaces)
                self.store.save_cameras(cameras)
                
                self.bot.reply_to(message, "✅ Камера назначена зоне")
            except Exception as e:
                logger.error(f"Error in /assign_camera: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['add_spot'])
        def handle_add_spot(message):
            if not self._check_admin(message):
                return
            
            try:
                # Format: /add_spot space_id type label x1,y1;x2,y2
                args = message.text.split(maxsplit=4)
                if len(args) < 5:
                    self.bot.reply_to(message, "Использование: /add_spot <space_id> <тип> <метка> <x1,y1;x2,y2>")
                    return
                
                space_id, spot_type, label, coords = args[1], args[2], args[3], args[4]
                
                # Parse coordinates
                p1, p2 = coords.split(';')
                x1, y1 = map(int, p1.split(','))
                x2, y2 = map(int, p2.split(','))
                
                import uuid
                from datetime import datetime, timezone
                
                # Получить space для camera_id и нумерации
                spaces = self.store.get_spaces()
                space = next((s for s in spaces if s['id'] == space_id), None)
                
                if not space:
                    self.bot.reply_to(message, "Зона не найдена.")
                    return
                
                camera_id = space['camera_ids'][0] if space.get('camera_ids') else None
                spot_number = space.get('next_spot_number', 1)
                
                spot_id = f"spot_{uuid.uuid4().hex[:8]}"
                spots = self.store.get_spots()
                spots.append({
                    'id': spot_id,
                    'space_id': space_id,
                    'camera_id': camera_id,
                    'type': spot_type,
                    'label': label,
                    'spot_number': spot_number,
                    'rect': {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2},
                    'alternative_views': [],
                    'created_by': 'telegram_bot',
                    'created_at': datetime.now(timezone.utc).isoformat()
                })
                self.store.save_spots(spots)
                
                # Обновить счетчик
                space['next_spot_number'] = spot_number + 1
                self.store.save_spaces(spaces)
                
                self.state_manager.initialize_space(space_id)
                
                self.bot.reply_to(message, f"✅ Место добавлено: {spot_id}")
            except Exception as e:
                logger.error(f"Error in /add_spot: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['move_spot'])
        def handle_move_spot(message):
            if not self._check_admin(message):
                return
            
            try:
                args = message.text.split(maxsplit=2)
                if len(args) < 3:
                    self.bot.reply_to(message, "Использование: /move_spot <spot_id> <x1,y1;x2,y2>")
                    return
                
                spot_id, coords = args[1], args[2]
                p1, p2 = coords.split(';')
                x1, y1 = map(int, p1.split(','))
                x2, y2 = map(int, p2.split(','))
                
                spots = self.store.get_spots()
                spot = next((s for s in spots if s['id'] == spot_id), None)
                
                if not spot:
                    self.bot.reply_to(message, "Место не найдено.")
                    return
                
                spot['rect'] = {'x1': x1, 'y1': y1, 'x2': x2, 'y2': y2}
                self.store.save_spots(spots)
                
                self.bot.reply_to(message, "✅ Место перемещено")
            except Exception as e:
                logger.error(f"Error in /move_spot: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['delete_spot'])
        def handle_delete_spot(message):
            if not self._check_admin(message):
                return
            
            try:
                args = message.text.split()
                if len(args) < 2:
                    self.bot.reply_to(message, "Использование: /delete_spot <spot_id>")
                    return
                
                spot_id = args[1]
                spots = self.store.get_spots()
                spot = next((s for s in spots if s['id'] == spot_id), None)
                
                if not spot:
                    self.bot.reply_to(message, "Место не найдено.")
                    return
                
                space_id = spot['space_id']
                spots = [s for s in spots if s['id'] != spot_id]
                self.store.save_spots(spots)
                self.state_manager.initialize_space(space_id)
                
                self.bot.reply_to(message, "✅ Место удалено")
            except Exception as e:
                logger.error(f"Error in /delete_spot: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['set_occupancy_minutes'])
        def handle_set_occupancy(message):
            if not self._check_admin(message):
                return
            
            try:
                args = message.text.split()
                if len(args) < 2:
                    self.bot.reply_to(message, "Использование: /set_occupancy_minutes <N>")
                    return
                
                minutes = int(args[1])
                self.store.update_config({'occupancy_minutes': minutes})
                
                self.bot.reply_to(message, f"✅ Порог занятости установлен на {minutes} минут")
            except Exception as e:
                logger.error(f"Error in /set_occupancy_minutes: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['start_stream'])
        def handle_start_stream(message):
            if not self._check_admin(message):
                return
            
            try:
                args = message.text.split()
                if len(args) < 2:
                    self.bot.reply_to(message, "Использование: /start_stream <camera_id> [target_alias]")
                    return
                
                camera_id = args[1]
                target_alias = args[2] if len(args) > 2 else None
                
                # Get camera
                cameras = self.store.get_cameras()
                camera = next((c for c in cameras if c['id'] == camera_id), None)
                
                if not camera:
                    self.bot.reply_to(message, "Камера не найдена.")
                    return
                
                success, msg = self.stream_manager.start_stream(
                    camera_id, camera['rtsp_url'], target_alias, message.chat.id
                )
                
                self.bot.reply_to(message, f"{'✅' if success else '❌'} {msg}")
            except Exception as e:
                logger.error(f"Error in /start_stream: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['stop_stream'])
        def handle_stop_stream(message):
            if not self._check_admin(message):
                return
            
            try:
                success, msg = self.stream_manager.stop_stream()
                self.bot.reply_to(message, f"{'✅' if success else '❌'} {msg}")
            except Exception as e:
                logger.error(f"Error in /stop_stream: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
        
        @self.bot.message_handler(commands=['stream_status'])
        def handle_stream_status(message):
            if not self._check_admin(message):
                return
            
            try:
                active = self.stream_manager.get_active_stream_info()
                
                if active:
                    import datetime
                    started = datetime.datetime.fromtimestamp(active['started_at'])
                    text = (
                        "🔴 <b>Стрим активен</b>\n\n"
                        f"Камера: {active['camera_id']}\n"
                        f"Цель: {active['target_alias']}\n"
                        f"Запущен: {started.strftime('%Y-%m-%d %H:%M:%S')}\n"
                        f"PID: {active['pid']}"
                    )
                else:
                    text = "⚫ Нет активного стрима"
                
                self.bot.reply_to(message, text)
            except Exception as e:
                logger.error(f"Error in /stream_status: {e}")
                self.bot.reply_to(message, f"Ошибка: {str(e)}")
    
    def _register_chat(self, message):
        """Register a chat if not already registered."""
        chat_id = message.chat.id
        username = message.from_user.username or ''
        first_name = message.from_user.first_name or ''
        
        config = self.store.get_config()
        allowed_chats = config.get('allowed_chats', [])
        
        # Check if already registered
        if any(c['chat_id'] == chat_id for c in allowed_chats):
            return
        
        # Register new chat
        allowed_chats.append({
            'chat_id': chat_id,
            'username': username,
            'first_name': first_name,
            'is_admin': False
        })
        
        self.store.update_config({'allowed_chats': allowed_chats})
        logger.info(f"Registered new chat: {chat_id} (@{username})")
    
    def _is_admin(self, chat_id: int) -> bool:
        """Check if chat has admin privileges."""
        config = self.store.get_config()
        allowed_chats = config.get('allowed_chats', [])
        chat = next((c for c in allowed_chats if c['chat_id'] == chat_id), None)
        return chat and chat.get('is_admin', False)
    
    def _check_admin(self, message) -> bool:
        """Check admin and reply if not authorized."""
        if not self._is_admin(message.chat.id):
            self.bot.reply_to(message, "❌ Требуются права администратора")
            return False
        return True

