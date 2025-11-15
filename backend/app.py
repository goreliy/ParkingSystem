"""
Main Flask application entry point.
"""
# КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ ДЛЯ PyTorch 2.6+ и YOLOv11
# Monkey patch torch.load ДО ВСЕХ импортов ultralytics
import os
os.environ['TORCH_FORCE_WEIGHTS_ONLY_LOAD'] = 'False'

import torch
import pickle
import importlib
_original_torch_load = torch.load

def _patched_torch_load(*args, **kwargs):
    """
    Улучшенный патч для torch.load с поддержкой YOLOv11.
    
    Решает две проблемы:
    1. PyTorch 2.6+ требует weights_only=False для YOLO моделей
    2. YOLOv11 модели могут содержать классы, отсутствующие в старых версиях ultralytics
    """
    # Всегда используем weights_only=False для доверенных YOLO моделей
    kwargs['weights_only'] = False
    
    try:
        return _original_torch_load(*args, **kwargs)
    except AttributeError as e:
        # Если класс отсутствует, пытаемся использовать fallback механизм
        error_msg = str(e)
        if 'C3k2' in error_msg or 'ultralytics.nn.modules.block' in error_msg:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Обнаружена проблема совместимости версий ultralytics при загрузке модели. "
                f"Ошибка: {error_msg}\n"
                f"РЕШЕНИЕ: Обновите ultralytics до версии 8.3.0 или выше:\n"
                f"  pip install --upgrade ultralytics>=8.3.0"
            )
            # Пытаемся динамически добавить отсутствующий класс
            try:
                from ultralytics.nn.modules import block as block_module
                # Если класс C3k2 отсутствует, это означает несовместимость версий
                # В этом случае лучше выбросить понятную ошибку
                raise RuntimeError(
                    f"Модель YOLOv11 требует ultralytics версии 8.3.0 или выше. "
                    f"Текущая версия может быть устаревшей.\n"
                    f"Выполните: pip install --upgrade ultralytics>=8.3.0\n"
                    f"Оригинальная ошибка: {error_msg}"
                ) from e
            except Exception as fallback_error:
                raise RuntimeError(
                    f"Не удалось загрузить модель YOLOv11. "
                    f"Требуется обновление ultralytics: pip install --upgrade ultralytics>=8.3.0\n"
                    f"Оригинальная ошибка: {error_msg}"
                ) from e
        raise

# Теперь можно импортировать остальное
import logging
import sys
import time
import threading
from pathlib import Path
from flask import Flask, render_template

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.storage import JSONStore
from backend.services import VideoProcessorManager, Detector
from backend.services.occupancy import OccupancyTracker
from backend.services.state import StateManager
from backend.services.auto_markup import AutoMarkupService
from backend.services.model_manager import ModelManager
from backend.bot.stream_manager import StreamManager
from backend.bot.telebot_runner import TelebotRunner
from backend.api.cameras import init_cameras_api
from backend.api.spaces import init_spaces_api
from backend.api.spots import init_spots_api
from backend.api.config import init_config_api
from backend.api.stream import init_stream_api
from backend.api.auto_markup import init_auto_markup_api
from backend.api.models import init_models_api

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/parking.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class ParkingMonitorApp:
    """Main application class that coordinates all components."""
    
    def __init__(self):
        self.store = JSONStore()
        self.video_manager = VideoProcessorManager()
        self.model_manager = ModelManager()
        
        # Получить активную модель из конфига или использовать дефолтную
        config = self.store.get_config()
        active_model = config.get('active_model', 'yolov8n.pt')
        model_path = self.model_manager.get_model_path_for_detector(active_model)
        
        self.detector = Detector(model_path=model_path, 
                                confidence_threshold=config.get('confidence_threshold', 0.5))
        self.state_manager = StateManager(self.store)
        self.stream_manager = StreamManager(self.store, self.state_manager)
        self.auto_markup_service = AutoMarkupService(
            self.store, self.video_manager, self.detector
        )
        self.bot_runner = TelebotRunner(
            self.store, self.video_manager, 
            self.state_manager, self.stream_manager
        )
        
        self.occupancy_tracker = OccupancyTracker(
            occupancy_minutes=config.get('occupancy_minutes', 5)
        )
        
        self.detection_thread = None
        self.detection_running = False
        
        self.flask_app = self._create_flask_app()
    
    def _create_flask_app(self):
        """Create and configure Flask application."""
        app = Flask(
            __name__,
            template_folder=str(Path(__file__).parent / 'templates'),
            static_folder=str(Path(__file__).parent / 'static')
        )
        
        # Register API blueprints
        app.register_blueprint(init_cameras_api(self.store, self.video_manager))
        app.register_blueprint(init_spaces_api(self.store, self.state_manager))
        app.register_blueprint(init_spots_api(self.store, self.state_manager))
        app.register_blueprint(init_config_api(self.store))
        app.register_blueprint(init_stream_api(
            self.store, self.video_manager, 
            self.state_manager, self.detector
        ))
        app.register_blueprint(init_auto_markup_api(
            self.store, self.video_manager, 
            self.detector, self.auto_markup_service
        ))
        app.register_blueprint(init_models_api(
            self.store, self.detector, 
            self.model_manager, self.video_manager
        ))
        
        # Web UI routes
        @app.route('/')
        def index():
            return render_template('index.html')
        
        @app.route('/setup')
        def setup():
            return render_template('setup.html')
        
        @app.route('/dashboard')
        def dashboard():
            return render_template('dashboard.html')
        
        @app.route('/config')
        def config_page():
            return render_template('config.html')
        
        @app.route('/auto-markup')
        def auto_markup_page():
            return render_template('auto_markup.html')
        
        return app
    
    def start(self):
        """Start all application components."""
        logger.info("=" * 60)
        logger.info("Starting Parking Monitor System")
        logger.info("=" * 60)
        
        # Initialize cameras from config
        self._initialize_cameras()
        
        # Start detection loop
        self._start_detection_loop()
        
        # Start Telegram bot
        logger.info("Starting Telegram bot...")
        self.bot_runner.start()
        
        logger.info("All components started successfully")
    
    def stop(self):
        """Stop all application components."""
        logger.info("Shutting down Parking Monitor System...")
        
        # Stop detection loop
        self.detection_running = False
        if self.detection_thread:
            self.detection_thread.join(timeout=10)
        
        # Stop video processors
        self.video_manager.stop_all()
        
        # Stop stream manager
        self.stream_manager.cleanup()
        
        # Stop bot
        self.bot_runner.stop()
        
        logger.info("Shutdown complete")
    
    def _initialize_cameras(self):
        """Initialize video processors for configured cameras."""
        cameras = self.store.get_cameras()
        logger.info(f"Initializing {len(cameras)} cameras...")
        
        for camera in cameras:
            self.video_manager.add_camera(camera['id'], camera['rtsp_url'])
            logger.info(f"  - {camera['name']} ({camera['id']})")
    
    def _start_detection_loop(self):
        """Start background detection loop."""
        self.detection_running = True
        self.detection_thread = threading.Thread(target=self._detection_loop, daemon=True)
        self.detection_thread.start()
        logger.info("Detection loop started")
    
    def _detection_loop(self):
        """Main detection loop that processes frames and updates occupancy."""
        config = self.store.get_config()
        update_interval = 1.0 / config.get('update_hz', 1.0)
        
        logger.info(f"Detection loop running (update interval: {update_interval}s)")
        
        while self.detection_running:
            try:
                start_time = time.time()
                
                # Get all spots
                spots = self.store.get_spots()
                
                # Group spots by space and camera
                space_camera_spots = {}
                spaces = self.store.get_spaces()
                
                for spot in spots:
                    if spot['type'] != 'parking':
                        continue
                    
                    space_id = spot['space_id']
                    space = next((s for s in spaces if s['id'] == space_id), None)
                    
                    if not space or not space.get('camera_ids'):
                        continue
                    
                    camera_id = space['camera_ids'][0]  # Use first camera
                    
                    key = (space_id, camera_id)
                    if key not in space_camera_spots:
                        space_camera_spots[key] = []
                    space_camera_spots[key].append(spot)
                
                # Process each camera/space combination
                detections = {}
                for (space_id, camera_id), space_spots in space_camera_spots.items():
                    frame = self.video_manager.get_frame(camera_id)
                    
                    if frame is None:
                        continue
                    
                    # Prepare ROIs for batch detection
                    rois = [
                        {'id': spot['id'], **spot['rect']}
                        for spot in space_spots
                    ]
                    
                    # Detect vehicles in ROIs
                    spot_detections = self.detector.get_detections_in_rois(frame, rois)
                    detections.update(spot_detections)
                
                # Update occupancy tracker
                if detections:
                    changes = self.occupancy_tracker.update_detections(detections)
                    
                    # Update state for changed spots
                    if changes:
                        self.state_manager.update_multiple_spots(changes)
                
                # Sleep for remaining time
                elapsed = time.time() - start_time
                sleep_time = max(0, update_interval - elapsed)
                time.sleep(sleep_time)
            
            except Exception as e:
                logger.error(f"Error in detection loop: {e}", exc_info=True)
                time.sleep(1)
    
    def run(self, host='0.0.0.0', port=5000):
        """Run the Flask application."""
        self.start()
        
        try:
            logger.info(f"Starting web server on {host}:{port}")
            logger.info(f"Dashboard: http://{host}:{port}/dashboard")
            logger.info(f"Setup: http://{host}:{port}/setup")
            logger.info(f"Config: http://{host}:{port}/config")
            
            # Use Flask development server with threading enabled
            self.flask_app.run(host=host, port=port, threaded=True, debug=False)
        
        except KeyboardInterrupt:
            logger.info("Received shutdown signal")
        
        finally:
            self.stop()


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Parking Monitor System')
    parser.add_argument('--host', default='0.0.0.0', help='Host to bind to')
    parser.add_argument('--port', type=int, default=5000, help='Port to bind to')
    
    args = parser.parse_args()
    
    app = ParkingMonitorApp()
    app.run(host=args.host, port=args.port)


if __name__ == '__main__':
    main()

