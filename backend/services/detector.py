"""
YOLO detector wrapper for vehicle detection.
"""
import logging
from typing import List, Dict, Tuple, Optional
from datetime import datetime
import numpy as np

logger = logging.getLogger(__name__)

try:
    from ultralytics import YOLO
    YOLO_AVAILABLE = True
    logger.info("Ultralytics YOLO available")
        
except ImportError:
    logger.warning("ultralytics not available, using mock detector")
    YOLO_AVAILABLE = False


class Detection:
    """Represents a single detection."""
    
    def __init__(self, bbox: Tuple[int, int, int, int], confidence: float, class_name: str):
        self.bbox = bbox  # (x1, y1, x2, y2)
        self.confidence = confidence
        self.class_name = class_name
    
    def __repr__(self):
        return f"Detection({self.class_name}, conf={self.confidence:.2f}, bbox={self.bbox})"


class Detector:
    """Vehicle detector using YOLO."""
    
    # Vehicle-related classes in COCO dataset
    VEHICLE_CLASSES = ['car', 'truck', 'bus', 'motorcycle']
    
    def __init__(self, model_path: str = "yolov8n.pt", confidence_threshold: float = 0.5):
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.model = None
        self.model_loaded_at = None
        self._lazy_load()
    
    def _lazy_load(self):
        """Lazy load the YOLO model."""
        if not YOLO_AVAILABLE:
            logger.warning("YOLO not available, detector will return empty results")
            return
        
        try:
            logger.info(f"Loading YOLO model from {self.model_path}")
            self.model = YOLO(self.model_path)
            self.model_loaded_at = datetime.now()
            logger.info(f"YOLO model loaded successfully: {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to load YOLO model {self.model_path}: {e}", exc_info=True)
            self.model = None
            self.model_loaded_at = None
    
    def change_model(self, new_model_path: str) -> bool:
        """
        Сменить модель YOLO.
        
        Args:
            new_model_path: Путь к новой модели
        
        Returns:
            True если успешно загружено
        
        Raises:
            RuntimeError: Если модель не может быть загружена из-за проблем совместимости
        """
        if not YOLO_AVAILABLE:
            logger.error("Cannot change model: ultralytics not available")
            return False
        
        try:
            logger.info(f"Changing YOLO model from {self.model_path} to {new_model_path}")
            
            # Загрузить новую модель (переменная окружения уже установлена)
            new_model = YOLO(new_model_path)
            
            # Если успешно, заменить
            self.model = new_model
            self.model_path = new_model_path
            self.model_loaded_at = datetime.now()
            
            logger.info(f"Successfully changed to model: {new_model_path}")
            return True
        
        except AttributeError as e:
            # Ошибка совместимости версий (например, C3k2 для YOLOv11)
            error_msg = str(e)
            if 'C3k2' in error_msg or 'ultralytics.nn.modules.block' in error_msg:
                logger.error(
                    f"Version compatibility error loading {new_model_path}: {error_msg}\n"
                    f"This usually means ultralytics needs to be upgraded to 8.3.0+"
                )
                # Пробрасываем RuntimeError с понятным сообщением
                raise RuntimeError(
                    f"Модель YOLOv11 требует ultralytics версии 8.3.0 или выше. "
                    f"Текущая версия не поддерживает эту модель.\n"
                    f"Выполните: pip install --upgrade ultralytics>=8.3.0\n"
                    f"Оригинальная ошибка: {error_msg}"
                ) from e
            # Другие AttributeError пробрасываем как есть
            logger.error(f"Failed to change model to {new_model_path}: {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"Failed to change model to {new_model_path}: {e}", exc_info=True)
            # Проверяем на признаки проблемы совместимости в сообщении об ошибке
            error_msg = str(e)
            if 'C3k2' in error_msg or ('ultralytics' in error_msg and 'block' in error_msg):
                raise RuntimeError(
                    f"Проблема совместимости версий ultralytics при загрузке модели.\n"
                    f"Обновите: pip install --upgrade ultralytics>=8.3.0\n"
                    f"Оригинальная ошибка: {error_msg}"
                ) from e
            raise
    
    def get_model_info(self) -> Dict:
        """Получить информацию о текущей модели."""
        return {
            'model_path': self.model_path,
            'is_loaded': self.model is not None,
            'loaded_at': self.model_loaded_at.isoformat() if self.model_loaded_at else None,
            'confidence_threshold': self.confidence_threshold,
            'vehicle_classes': self.VEHICLE_CLASSES
        }
    
    def set_confidence_threshold(self, threshold: float):
        """Установить порог уверенности."""
        if 0.0 <= threshold <= 1.0:
            self.confidence_threshold = threshold
            logger.info(f"Confidence threshold set to {threshold}")
        else:
            raise ValueError("Confidence threshold must be between 0.0 and 1.0")
    
    def detect(self, frame: np.ndarray, exclusion_zones: Optional[List[Dict[str, int]]] = None) -> List[Detection]:
        """
        Detect vehicles in the frame.
        
        Args:
            frame: Input image (BGR format)
            exclusion_zones: Optional list of exclusion zones [{x1, y1, x2, y2}, ...]
        
        Returns:
            List of Detection objects (filtered to exclude zones in exclusion_zones)
        """
        if self.model is None or not YOLO_AVAILABLE:
            return []
        
        try:
            # Run inference
            results = self.model(frame, conf=self.confidence_threshold, verbose=False)
            
            detections = []
            for result in results:
                boxes = result.boxes
                for box in boxes:
                    # Get class name
                    class_id = int(box.cls[0])
                    class_name = self.model.names[class_id]
                    
                    # Filter only vehicles
                    if class_name.lower() not in self.VEHICLE_CLASSES:
                        continue
                    
                    # Get bbox and confidence
                    x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()
                    confidence = float(box.conf[0])
                    
                    detection = Detection(
                        bbox=(int(x1), int(y1), int(x2), int(y2)),
                        confidence=confidence,
                        class_name=class_name
                    )
                    
                    # Фильтровать детекции в exclusion zones
                    if exclusion_zones:
                        if self._is_in_exclusion_zone(detection.bbox, exclusion_zones):
                            continue
                    
                    detections.append(detection)
            
            return detections
        
        except Exception as e:
            logger.error(f"Error during detection: {e}")
            return []
    
    def _is_in_exclusion_zone(self, bbox: Tuple[int, int, int, int], 
                              exclusion_zones: List[Dict[str, int]]) -> bool:
        """
        Проверить, попадает ли детекция в какую-либо exclusion zone.
        
        Args:
            bbox: Detection bounding box (x1, y1, x2, y2)
            exclusion_zones: List of exclusion zones [{x1, y1, x2, y2}, ...]
        
        Returns:
            True если детекция попадает в exclusion zone
        """
        x1_det, y1_det, x2_det, y2_det = bbox
        
        for zone in exclusion_zones:
            x1_zone, y1_zone = zone['x1'], zone['y1']
            x2_zone, y2_zone = zone['x2'], zone['y2']
            
            # Проверяем пересечение (если центр детекции попадает в зону, или значительная часть)
            center_x = (x1_det + x2_det) / 2
            center_y = (y1_det + y2_det) / 2
            
            # Если центр детекции в exclusion zone
            if (x1_zone <= center_x <= x2_zone and y1_zone <= center_y <= y2_zone):
                return True
            
            # Или если значительная часть детекции пересекается с exclusion zone
            x1_inter = max(x1_det, x1_zone)
            y1_inter = max(y1_det, y1_zone)
            x2_inter = min(x2_det, x2_zone)
            y2_inter = min(y2_det, y2_zone)
            
            if x2_inter > x1_inter and y2_inter > y1_inter:
                intersection_area = (x2_inter - x1_inter) * (y2_inter - y1_inter)
                detection_area = (x2_det - x1_det) * (y2_det - y1_det)
                
                if detection_area > 0:
                    overlap_ratio = intersection_area / detection_area
                    # Если более 30% детекции попадает в exclusion zone
                    if overlap_ratio > 0.3:
                        return True
        
        return False
    
    def detect_in_roi(self, frame: np.ndarray, roi: Dict[str, int]) -> bool:
        """
        Check if any vehicle is detected in the specified ROI.
        
        Args:
            frame: Input image
            roi: Dictionary with keys x1, y1, x2, y2
        
        Returns:
            True if vehicle detected in ROI
        """
        detections = self.detect(frame)
        
        for det in detections:
            if self._bbox_intersects_roi(det.bbox, roi):
                return True
        
        return False
    
    def _bbox_intersects_roi(self, bbox: Tuple[int, int, int, int], 
                            roi: Dict[str, int], 
                            threshold: float = 0.3) -> bool:
        """
        Check if detection bbox intersects with ROI.
        
        Args:
            bbox: Detection bounding box (x1, y1, x2, y2)
            roi: ROI dictionary {x1, y1, x2, y2}
            threshold: Minimum intersection ratio to consider as overlap
        
        Returns:
            True if intersection ratio exceeds threshold
        """
        x1_det, y1_det, x2_det, y2_det = bbox
        x1_roi, y1_roi = roi['x1'], roi['y1']
        x2_roi, y2_roi = roi['x2'], roi['y2']
        
        # Calculate intersection
        x1_inter = max(x1_det, x1_roi)
        y1_inter = max(y1_det, y1_roi)
        x2_inter = min(x2_det, x2_roi)
        y2_inter = min(y2_det, y2_roi)
        
        if x2_inter < x1_inter or y2_inter < y1_inter:
            return False
        
        intersection_area = (x2_inter - x1_inter) * (y2_inter - y1_inter)
        roi_area = (x2_roi - x1_roi) * (y2_roi - y1_roi)
        
        if roi_area == 0:
            return False
        
        intersection_ratio = intersection_area / roi_area
        return intersection_ratio >= threshold
    
    def get_detections_in_rois(self, frame: np.ndarray, 
                               rois: List[Dict]) -> Dict[str, bool]:
        """
        Check multiple ROIs at once.
        
        Args:
            frame: Input image
            rois: List of ROI dictionaries with 'id' and coordinates
        
        Returns:
            Dictionary mapping roi_id to detection status
        """
        detections = self.detect(frame)
        results = {}
        
        for roi in rois:
            roi_id = roi['id']
            has_vehicle = False
            
            for det in detections:
                if self._bbox_intersects_roi(det.bbox, roi):
                    has_vehicle = True
                    break
            
            results[roi_id] = has_vehicle
        
        return results

