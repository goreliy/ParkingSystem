"""
Менеджер YOLO моделей для детекции транспорта.
"""
import logging
import os
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime
import requests

logger = logging.getLogger(__name__)

# Доступные YOLO модели
AVAILABLE_YOLO_MODELS = {
    # YOLOv8 модели
    'yolov8n.pt': {
        'name': 'YOLOv8 Nano',
        'size': '6 MB',
        'speed': 'Самая быстрая',
        'accuracy': 'Базовая',
        'url': 'https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8n.pt',
        'recommended': False,
        'version': 'v8'
    },
    'yolov8s.pt': {
        'name': 'YOLOv8 Small',
        'size': '22 MB',
        'speed': 'Быстрая',
        'accuracy': 'Хорошая',
        'url': 'https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8s.pt',
        'recommended': False,
        'version': 'v8'
    },
    'yolov8m.pt': {
        'name': 'YOLOv8 Medium',
        'size': '52 MB',
        'speed': 'Средняя',
        'accuracy': 'Отличная',
        'url': 'https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8m.pt',
        'recommended': False,
        'version': 'v8'
    },
    'yolov8l.pt': {
        'name': 'YOLOv8 Large',
        'size': '88 MB',
        'speed': 'Медленная',
        'accuracy': 'Очень хорошая',
        'url': 'https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8l.pt',
        'recommended': False,
        'version': 'v8'
    },
    'yolov8x.pt': {
        'name': 'YOLOv8 XLarge',
        'size': '138 MB',
        'speed': 'Очень медленная',
        'accuracy': 'Максимальная',
        'url': 'https://github.com/ultralytics/assets/releases/download/v8.1.0/yolov8x.pt',
        'recommended': False,
        'version': 'v8'
    },
    
    # YOLOv11 модели (улучшенная архитектура)
    'yolo11n.pt': {
        'name': 'YOLOv11 Nano',
        'size': '5 MB',
        'speed': 'Очень быстрая',
        'accuracy': 'Хорошая',
        'url': 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt',
        'recommended': False,
        'version': 'v11'
    },
    'yolo11s.pt': {
        'name': 'YOLOv11 Small',
        'size': '19 MB',
        'speed': 'Быстрая',
        'accuracy': 'Очень хорошая',
        'url': 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11s.pt',
        'recommended': True,
        'version': 'v11'
    },
    'yolo11m.pt': {
        'name': 'YOLOv11 Medium',
        'size': '40 MB',
        'speed': 'Средняя',
        'accuracy': 'Отличная',
        'url': 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11m.pt',
        'recommended': False,
        'version': 'v11'
    },
    'yolo11l.pt': {
        'name': 'YOLOv11 Large',
        'size': '50 MB',
        'speed': 'Медленная',
        'accuracy': 'Превосходная',
        'url': 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11l.pt',
        'recommended': False,
        'version': 'v11'
    },
    'yolo11x.pt': {
        'name': 'YOLOv11 XLarge',
        'size': '110 MB',
        'speed': 'Очень медленная',
        'accuracy': 'Максимальная',
        'url': 'https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11x.pt',
        'recommended': False,
        'version': 'v11'
    }
}


class ModelManager:
    """Менеджер для управления YOLO моделями."""
    
    def __init__(self, models_dir: str = "models"):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(exist_ok=True)
        
        # Также проверяем корневую директорию
        self.root_dir = Path(".")
    
    def list_available_models(self) -> List[Dict]:
        """Получить список доступных для загрузки моделей."""
        models = []
        
        for filename, info in AVAILABLE_YOLO_MODELS.items():
            is_downloaded = self._is_model_downloaded(filename)
            
            model_info = {
                'filename': filename,
                'name': info['name'],
                'size': info['size'],
                'speed': info['speed'],
                'accuracy': info['accuracy'],
                'recommended': info['recommended'],
                'is_downloaded': is_downloaded,
                'download_url': info['url']
            }
            
            if is_downloaded:
                model_path = self._get_model_path(filename)
                model_info['path'] = str(model_path)
                model_info['size_bytes'] = model_path.stat().st_size if model_path.exists() else 0
            
            models.append(model_info)
        
        return models
    
    def list_downloaded_models(self) -> List[Dict]:
        """Получить список загруженных моделей."""
        models = []
        
        # Проверить models/ директорию
        for model_file in self.models_dir.glob("*.pt"):
            models.append(self._get_model_info(model_file))
        
        # Проверить корневую директорию
        for model_file in self.root_dir.glob("*.pt"):
            if model_file.name not in [m['filename'] for m in models]:
                models.append(self._get_model_info(model_file))
        
        return models
    
    def _get_model_info(self, model_path: Path) -> Dict:
        """Получить информацию о модели."""
        filename = model_path.name
        size_bytes = model_path.stat().st_size
        size_mb = size_bytes / (1024 * 1024)
        
        # Дополнительная информация из AVAILABLE_YOLO_MODELS
        extra_info = AVAILABLE_YOLO_MODELS.get(filename, {})
        
        return {
            'filename': filename,
            'path': str(model_path),
            'size_mb': f"{size_mb:.1f} MB",
            'size_bytes': size_bytes,
            'name': extra_info.get('name', filename),
            'speed': extra_info.get('speed', 'Неизвестно'),
            'accuracy': extra_info.get('accuracy', 'Неизвестно'),
            'is_downloaded': True
        }
    
    def _is_model_downloaded(self, filename: str) -> bool:
        """Проверить загружена ли модель."""
        # Проверить в models/
        if (self.models_dir / filename).exists():
            return True
        
        # Проверить в корне
        if (self.root_dir / filename).exists():
            return True
        
        return False
    
    def _get_model_path(self, filename: str) -> Optional[Path]:
        """Получить путь к модели."""
        # Сначала проверить models/
        models_path = self.models_dir / filename
        if models_path.exists():
            return models_path
        
        # Затем корень
        root_path = self.root_dir / filename
        if root_path.exists():
            return root_path
        
        return None
    
    def download_model(self, filename: str, progress_callback=None) -> Dict:
        """
        Загрузить YOLO модель.
        
        Args:
            filename: Имя файла модели
            progress_callback: Callback для отслеживания прогресса
        
        Returns:
            Информация о загруженной модели
        """
        if filename not in AVAILABLE_YOLO_MODELS:
            raise ValueError(f"Unknown model: {filename}")
        
        if self._is_model_downloaded(filename):
            logger.info(f"Model {filename} already downloaded")
            return self._get_model_info(self._get_model_path(filename))
        
        model_info = AVAILABLE_YOLO_MODELS[filename]
        url = model_info['url']
        
        # Сохранить в models/
        output_path = self.models_dir / filename
        
        try:
            logger.info(f"Downloading {filename} from {url}")
            
            response = requests.get(url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            
            with open(output_path, 'wb') as f:
                if total_size == 0:
                    f.write(response.content)
                else:
                    downloaded = 0
                    chunk_size = 8192
                    
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            if progress_callback:
                                progress = int((downloaded / total_size) * 100)
                                progress_callback(progress, downloaded, total_size)
            
            logger.info(f"Successfully downloaded {filename}")
            return self._get_model_info(output_path)
        
        except Exception as e:
            logger.error(f"Error downloading model {filename}: {e}")
            # Удалить частично загруженный файл
            if output_path.exists():
                output_path.unlink()
            raise
    
    def delete_model(self, filename: str) -> bool:
        """Удалить модель."""
        model_path = self._get_model_path(filename)
        
        if not model_path:
            return False
        
        try:
            model_path.unlink()
            logger.info(f"Deleted model {filename}")
            return True
        except Exception as e:
            logger.error(f"Error deleting model {filename}: {e}")
            return False
    
    def get_model_path_for_detector(self, filename: str) -> str:
        """Получить путь к модели для использования в Detector."""
        model_path = self._get_model_path(filename)
        
        if not model_path:
            # Если модель не найдена, вернуть имя файла
            # Ultralytics автоматически загрузит модель при первом использовании
            logger.warning(f"Model {filename} not found locally, will be auto-downloaded by ultralytics")
            return filename
        
        return str(model_path)

