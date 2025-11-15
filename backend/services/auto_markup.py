"""
Автоматическая разметка парковочных мест с использованием детекции транспорта.
"""
import logging
import time
import threading
import uuid
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class StableVehicle:
    """Представляет стабильно стоящую машину."""
    bbox: Tuple[int, int, int, int]  # усредненный bbox (x1, y1, x2, y2)
    confidence: float  # средняя уверенность
    stability_score: float  # доля кадров где присутствует (0-1)
    detections_count: int  # количество детекций
    first_seen: float  # timestamp первой детекции
    last_seen: float  # timestamp последней детекции


@dataclass
class SpotProposal:
    """Предложение парковочного места."""
    index: int
    camera_id: str
    bbox: Tuple[int, int, int, int]  # оригинальный bbox машины
    suggested_rect: Dict  # стандартизированный rect для spot
    confidence: float
    stability_score: float
    is_valid: bool  # флаг "правильно припаркована"
    exclude_reason: Optional[str]
    suggested_label: str
    
    def to_dict(self):
        return asdict(self)


class VehicleTracker:
    """Отслеживает транспорт на кадрах для определения неподвижных авто."""
    
    def __init__(self, stability_seconds: int = 30):
        self.stability_seconds = stability_seconds
        self.detections_history: Dict[str, List[Tuple[float, List]]] = {}
        self.lock = threading.Lock()
    
    def add_frame_detections(self, camera_id: str, detections: List):
        """Добавить детекции с одного кадра."""
        with self.lock:
            current_time = time.time()
            
            if camera_id not in self.detections_history:
                self.detections_history[camera_id] = []
            
            # Добавить новые детекции
            self.detections_history[camera_id].append((current_time, detections))
            
            # Очистить старые детекции (старше stability_seconds * 2)
            cutoff_time = current_time - (self.stability_seconds * 2)
            self.detections_history[camera_id] = [
                (t, dets) for t, dets in self.detections_history[camera_id]
                if t >= cutoff_time
            ]
    
    def get_stable_vehicles(self, camera_id: str) -> List[StableVehicle]:
        """Получить список стабильно стоящих машин."""
        with self.lock:
            if camera_id not in self.detections_history:
                return []
            
            history = self.detections_history[camera_id]
            
            if len(history) < 2:
                return []
            
            # Собрать все детекции в один список
            all_detections = []
            for timestamp, detections in history:
                for det in detections:
                    all_detections.append((timestamp, det))
            
            if not all_detections:
                return []
            
            # Группировать похожие детекции
            stable_vehicles = self._group_stable_detections(all_detections)
            
            return stable_vehicles
    
    def _group_stable_detections(self, detections: List[Tuple[float, any]]) -> List[StableVehicle]:
        """Группировать детекции в стабильные машины."""
        if not detections:
            return []
        
        # Сортировать по времени
        detections = sorted(detections, key=lambda x: x[0])
        
        groups = []
        used = set()
        
        for i, (time_i, det_i) in enumerate(detections):
            if i in used:
                continue
            
            # Начать новую группу
            group = [(time_i, det_i)]
            used.add(i)
            
            # Найти все похожие детекции
            for j, (time_j, det_j) in enumerate(detections):
                if j in used:
                    continue
                
                # Проверить IoU
                iou = self._calculate_iou(det_i.bbox, det_j.bbox)
                if iou >= 0.7:  # Порог схожести
                    group.append((time_j, det_j))
                    used.add(j)
            
            groups.append(group)
        
        # Конвертировать группы в стабильные машины
        stable_vehicles = []
        current_time = time.time()
        
        for group in groups:
            if len(group) < 2:  # Нужно минимум 2 детекции
                continue
            
            timestamps = [t for t, _ in group]
            dets = [d for _, d in group]
            
            # Проверить временной диапазон
            time_span = max(timestamps) - min(timestamps)
            if time_span < self.stability_seconds:
                continue
            
            # Усреднить bbox
            avg_bbox = self._average_bboxes([d.bbox for d in dets])
            avg_confidence = np.mean([d.confidence for d in dets])
            
            # Вычислить stability_score
            total_duration = current_time - min(timestamps)
            stability_score = min(1.0, time_span / self.stability_seconds)
            
            stable_vehicle = StableVehicle(
                bbox=avg_bbox,
                confidence=float(avg_confidence),
                stability_score=float(stability_score),
                detections_count=len(group),
                first_seen=min(timestamps),
                last_seen=max(timestamps)
            )
            
            stable_vehicles.append(stable_vehicle)
        
        return stable_vehicles
    
    def _calculate_iou(self, bbox1: Tuple, bbox2: Tuple) -> float:
        """Вычислить Intersection over Union между двумя bbox."""
        x1_1, y1_1, x2_1, y2_1 = bbox1
        x1_2, y1_2, x2_2, y2_2 = bbox2
        
        # Пересечение
        x1_inter = max(x1_1, x1_2)
        y1_inter = max(y1_1, y1_2)
        x2_inter = min(x2_1, x2_2)
        y2_inter = min(y2_1, y2_2)
        
        if x2_inter < x1_inter or y2_inter < y1_inter:
            return 0.0
        
        intersection = (x2_inter - x1_inter) * (y2_inter - y1_inter)
        
        # Площади
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        
        union = area1 + area2 - intersection
        
        if union == 0:
            return 0.0
        
        return intersection / union
    
    def _average_bboxes(self, bboxes: List[Tuple]) -> Tuple[int, int, int, int]:
        """Усреднить список bbox."""
        x1_avg = int(np.mean([b[0] for b in bboxes]))
        y1_avg = int(np.mean([b[1] for b in bboxes]))
        x2_avg = int(np.mean([b[2] for b in bboxes]))
        y2_avg = int(np.mean([b[3] for b in bboxes]))
        return (x1_avg, y1_avg, x2_avg, y2_avg)
    
    def clear_camera(self, camera_id: str):
        """Очистить историю для камеры."""
        with self.lock:
            if camera_id in self.detections_history:
                del self.detections_history[camera_id]


class AutoMarkupSession:
    """Сессия автоматической разметки."""
    
    def __init__(self, session_id: str, space_id: str, camera_id: str, 
                 mode: str, settings: Dict):
        self.session_id = session_id
        self.space_id = space_id
        self.camera_id = camera_id
        self.mode = mode
        self.settings = settings
        self.status = 'analyzing'  # analyzing, completed, error, cancelled
        self.started_at = datetime.now(timezone.utc)
        self.completed_at: Optional[datetime] = None
        self.progress = 0
        self.frames_analyzed = 0
        self.vehicles_found = 0
        self.proposals: List[SpotProposal] = []
        self.error_message: Optional[str] = None
        self.preview_frame: Optional[np.ndarray] = None


class AutoMarkupService:
    """Сервис автоматической разметки парковочных мест."""
    
    def __init__(self, store, video_manager, detector):
        self.store = store
        self.video_manager = video_manager
        self.detector = detector
        self.sessions: Dict[str, AutoMarkupSession] = {}
        self.lock = threading.Lock()
    
    def start_analysis(self, space_id: str, mode: str, 
                      duration_seconds: int = 60,
                      standard_spot_width: int = 120,
                      standard_spot_height: int = 120,
                      stability_seconds: int = 30) -> str:
        """
        Запустить анализ для автоматической разметки.
        
        Args:
            space_id: ID парковочной зоны
            mode: 'single', 'average', или 'duration'
            duration_seconds: длительность для режима 'duration'
            standard_spot_width: процент от ширины машины (100 = точно по машине, 120 = +20% запас)
            standard_spot_height: процент от высоты машины (100 = точно по машине, 120 = +20% запас)
            stability_seconds: минимальное время стабильности
        
        Returns:
            session_id
        """
        # Получить зону и камеру
        spaces = self.store.get_spaces()
        space = next((s for s in spaces if s['id'] == space_id), None)
        
        if not space:
            raise ValueError(f"Space {space_id} not found")
        
        if not space.get('camera_ids'):
            raise ValueError(f"Space {space_id} has no cameras assigned")
        
        camera_id = space['camera_ids'][0]  # Используем первую камеру
        
        # Создать сессию
        session_id = f"markup_{uuid.uuid4().hex[:12]}"
        
        settings = {
            'standard_width': standard_spot_width,
            'standard_height': standard_spot_height,
            'stability_seconds': stability_seconds,
            'duration_seconds': duration_seconds
        }
        
        session = AutoMarkupSession(
            session_id=session_id,
            space_id=space_id,
            camera_id=camera_id,
            mode=mode,
            settings=settings
        )
        
        with self.lock:
            self.sessions[session_id] = session
        
        # Запустить анализ в отдельном потоке
        thread = threading.Thread(
            target=self._run_analysis,
            args=(session_id,),
            daemon=True
        )
        thread.start()
        
        logger.info(f"Started auto-markup session {session_id} for space {space_id} in mode {mode}")
        
        return session_id
    
    def _run_analysis(self, session_id: str):
        """Запустить анализ в фоновом потоке."""
        session = self.sessions.get(session_id)
        if not session:
            return
        
        try:
            if session.mode == 'single':
                self._analyze_single_frame(session)
            elif session.mode == 'average':
                self._analyze_average(session)
            elif session.mode == 'duration':
                self._analyze_duration(session)
            else:
                raise ValueError(f"Unknown mode: {session.mode}")
            
            session.status = 'completed'
            session.completed_at = datetime.now(timezone.utc)
            logger.info(f"Analysis completed for session {session_id}: {len(session.proposals)} proposals")
        
        except Exception as e:
            logger.error(f"Error in analysis for session {session_id}: {e}", exc_info=True)
            session.status = 'error'
            session.error_message = str(e)
    
    def _get_exclusion_zones(self, camera_id: str) -> List[Dict[str, int]]:
        """Получить exclusion zones для камеры."""
        cameras = self.store.get_cameras()
        camera = next((c for c in cameras if c['id'] == camera_id), None)
        if camera:
            return camera.get('exclusion_zones', [])
        return []
    
    def _analyze_single_frame(self, session: AutoMarkupSession):
        """Быстрый анализ - один кадр."""
        frame = self.video_manager.get_frame(session.camera_id)
        
        if frame is None:
            raise RuntimeError("Camera not available")
        
        session.preview_frame = frame.copy()
        
        # Получить exclusion zones для камеры
        exclusion_zones = self._get_exclusion_zones(session.camera_id)
        
        # Детектировать машины (с учётом exclusion zones)
        detections = self.detector.detect(frame, exclusion_zones=exclusion_zones)
        session.frames_analyzed = 1
        session.vehicles_found = len(detections)
        session.progress = 100
        
        # Создать предложения
        session.proposals = self._create_proposals_from_detections(
            detections, session.camera_id, session.settings
        )
    
    def _analyze_average(self, session: AutoMarkupSession):
        """Усредненный анализ - 30 секунд."""
        tracker = VehicleTracker(stability_seconds=session.settings['stability_seconds'])
        
        # Получить exclusion zones для камеры
        exclusion_zones = self._get_exclusion_zones(session.camera_id)
        
        duration = 30  # секунд
        interval = 1  # секунда между кадрами
        total_frames = duration // interval
        
        for i in range(total_frames):
            if session.status == 'cancelled':
                return
            
            frame = self.video_manager.get_frame(session.camera_id)
            
            if frame is not None:
                # Сохранить последний кадр для превью
                session.preview_frame = frame.copy()
                
                # Детектировать и добавить в трекер (с учётом exclusion zones)
                detections = self.detector.detect(frame, exclusion_zones=exclusion_zones)
                tracker.add_frame_detections(session.camera_id, detections)
                
                session.frames_analyzed = i + 1
                session.progress = int((i + 1) / total_frames * 100)
            
            time.sleep(interval)
        
        # Получить стабильные машины
        stable_vehicles = tracker.get_stable_vehicles(session.camera_id)
        session.vehicles_found = len(stable_vehicles)
        
        # Создать предложения
        session.proposals = self._create_proposals_from_stable_vehicles(
            stable_vehicles, session.camera_id, session.settings
        )
    
    def _analyze_duration(self, session: AutoMarkupSession):
        """Глубокий анализ - настраиваемая длительность."""
        tracker = VehicleTracker(stability_seconds=session.settings['stability_seconds'])
        
        # Получить exclusion zones для камеры
        exclusion_zones = self._get_exclusion_zones(session.camera_id)
        
        duration = session.settings['duration_seconds']
        interval = 5  # секунд между кадрами
        total_frames = duration // interval
        
        for i in range(total_frames):
            if session.status == 'cancelled':
                return
            
            frame = self.video_manager.get_frame(session.camera_id)
            
            if frame is not None:
                session.preview_frame = frame.copy()
                
                # Детектировать и добавить в трекер (с учётом exclusion zones)
                detections = self.detector.detect(frame, exclusion_zones=exclusion_zones)
                tracker.add_frame_detections(session.camera_id, detections)
                
                session.frames_analyzed = i + 1
                session.progress = int((i + 1) / total_frames * 100)
            
            time.sleep(interval)
        
        stable_vehicles = tracker.get_stable_vehicles(session.camera_id)
        session.vehicles_found = len(stable_vehicles)
        
        session.proposals = self._create_proposals_from_stable_vehicles(
            stable_vehicles, session.camera_id, session.settings
        )
    
    def _create_proposals_from_detections(self, detections: List, 
                                          camera_id: str, 
                                          settings: Dict) -> List[SpotProposal]:
        """Создать предложения из списка детекций (для режима single)."""
        proposals = []
        
        for idx, det in enumerate(detections):
            # Стандартизировать размер
            suggested_rect = self._standardize_bbox(
                det.bbox,
                settings['standard_width'],
                settings['standard_height']
            )
            
            # Проверить валидность
            is_valid, exclude_reason = self._check_validity(det.bbox, suggested_rect)
            
            proposal = SpotProposal(
                index=idx,
                camera_id=camera_id,
                bbox=det.bbox,
                suggested_rect=suggested_rect,
                confidence=det.confidence,
                stability_score=1.0,  # Для single режима считаем 100%
                is_valid=is_valid,
                exclude_reason=exclude_reason,
                suggested_label=f"#{idx+1}"
            )
            
            proposals.append(proposal)
        
        return proposals
    
    def _create_proposals_from_stable_vehicles(self, stable_vehicles: List[StableVehicle],
                                               camera_id: str,
                                               settings: Dict) -> List[SpotProposal]:
        """Создать предложения из стабильных машин."""
        proposals = []
        
        for idx, vehicle in enumerate(stable_vehicles):
            suggested_rect = self._standardize_bbox(
                vehicle.bbox,
                settings['standard_width'],
                settings['standard_height']
            )
            
            is_valid, exclude_reason = self._check_validity(vehicle.bbox, suggested_rect)
            
            proposal = SpotProposal(
                index=idx,
                camera_id=camera_id,
                bbox=vehicle.bbox,
                suggested_rect=suggested_rect,
                confidence=vehicle.confidence,
                stability_score=vehicle.stability_score,
                is_valid=is_valid,
                exclude_reason=exclude_reason,
                suggested_label=f"#{idx+1}"
            )
            
            proposals.append(proposal)
        
        return proposals
    
    def _standardize_bbox(self, bbox: Tuple[int, int, int, int],
                         standard_width: int, 
                         standard_height: int) -> Dict:
        """
        Применить размер на основе найденной машины с процентным запасом.
        
        standard_width и standard_height теперь это процент запаса (не абсолютные пиксели!)
        По умолчанию: standard_width=120 означает 120% от ширины машины (т.е. +20% запас)
        """
        x1, y1, x2, y2 = bbox
        
        # Размер найденной машины
        detected_width = x2 - x1
        detected_height = y2 - y1
        
        # Применить процентный запас (standard_width и height теперь в процентах)
        # Если standard_width = 120, то margin_factor = 1.2 (т.е. +20%)
        margin_factor_w = standard_width / 100.0
        margin_factor_h = standard_height / 100.0
        
        # Новый размер с запасом
        new_width = int(detected_width * margin_factor_w)
        new_height = int(detected_height * margin_factor_h)
        
        # Центр остается тот же
        center_x = (x1 + x2) // 2
        center_y = (y1 + y2) // 2
        
        # Rect с запасом вокруг центра
        new_x1 = center_x - new_width // 2
        new_x2 = center_x + new_width // 2
        new_y1 = center_y - new_height // 2
        new_y2 = center_y + new_height // 2
        
        return {
            'x1': int(new_x1),
            'y1': int(new_y1),
            'x2': int(new_x2),
            'y2': int(new_y2)
        }
    
    def _check_validity(self, original_bbox: Tuple, 
                       suggested_rect: Dict,
                       frame_width: int = 1920,
                       frame_height: int = 1080) -> Tuple[bool, Optional[str]]:
        """
        Проверить валидность предложения.
        
        Returns:
            (is_valid, exclude_reason)
        """
        x1, y1 = suggested_rect['x1'], suggested_rect['y1']
        x2, y2 = suggested_rect['x2'], suggested_rect['y2']
        
        # Проверка 1: Слишком близко к краю
        margin = 10
        if (x1 < margin or y1 < margin or 
            x2 > frame_width - margin or y2 > frame_height - margin):
            return False, "Слишком близко к краю кадра"
        
        # Проверка 2: Выходит за границы кадра
        if x1 < 0 or y1 < 0 or x2 > frame_width or y2 > frame_height:
            return False, "Выходит за границы кадра"
        
        # Проверка 3: Некорректный размер
        width = x2 - x1
        height = y2 - y1
        if width < 50 or height < 50:
            return False, "Слишком маленький размер"
        
        return True, None
    
    def get_analysis_progress(self, session_id: str) -> Optional[Dict]:
        """Получить прогресс анализа."""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        return {
            'session_id': session_id,
            'status': session.status,
            'progress': session.progress,
            'frames_analyzed': session.frames_analyzed,
            'vehicles_found': session.vehicles_found,
            'started_at': session.started_at.isoformat(),
            'completed_at': session.completed_at.isoformat() if session.completed_at else None,
            'error_message': session.error_message
        }
    
    def get_proposals(self, session_id: str) -> Optional[Dict]:
        """Получить предложения парковочных мест."""
        session = self.sessions.get(session_id)
        if not session:
            return None
        
        # Получить следующий номер для зоны
        spaces = self.store.get_spaces()
        space = next((s for s in spaces if s['id'] == session.space_id), None)
        next_spot_number = space.get('next_spot_number', 1) if space else 1
        
        # Обновить suggested_label с правильными номерами
        for idx, proposal in enumerate(session.proposals):
            proposal.suggested_label = f"{next_spot_number + idx}"
        
        return {
            'session_id': session_id,
            'space_id': session.space_id,
            'camera_id': session.camera_id,
            'status': session.status,
            'proposals': [p.to_dict() for p in session.proposals],
            'annotated_image_url': f'/api/auto-markup/preview/{session_id}'
        }
    
    def get_preview_image(self, session_id: str) -> Optional[np.ndarray]:
        """Получить превью изображение с разметкой предложений."""
        session = self.sessions.get(session_id)
        if not session or session.preview_frame is None:
            return None
        
        frame = session.preview_frame.copy()
        
        # Нарисовать все предложения
        for proposal in session.proposals:
            rect = proposal.suggested_rect
            x1, y1 = rect['x1'], rect['y1']
            x2, y2 = rect['x2'], rect['y2']
            
            # Выбрать цвет
            if proposal.is_valid:
                color = (0, 255, 0)  # Зеленый - валидные
                symbol = "✓"
            else:
                color = (0, 0, 255)  # Красный - исключенные
                symbol = "✗"
            
            # Рамка
            import cv2
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
            
            # Метка
            label = f"{proposal.suggested_label} {symbol}"
            cv2.putText(frame, label, (x1, y1 - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 4)
            cv2.putText(frame, label, (x1, y1 - 10), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
            
            # Дополнительная информация
            info = f"Conf: {proposal.confidence:.0%} Stab: {proposal.stability_score:.0%}"
            cv2.putText(frame, info, (x1, y2 + 20), 
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        
        return frame
    
    def apply_proposals(self, session_id: str, approved_indices: List[int],
                       label_prefix: str = "A", auto_number: bool = True) -> Dict:
        """
        Применить одобренные предложения и создать парковочные места.
        
        Args:
            session_id: ID сессии
            approved_indices: индексы одобренных предложений
            label_prefix: префикс для меток
            auto_number: использовать сквозную нумерацию
        
        Returns:
            Информация о созданных местах
        """
        session = self.sessions.get(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
        
        if session.status != 'completed':
            raise ValueError(f"Session {session_id} is not completed")
        
        # Получить зону
        spaces = self.store.get_spaces()
        space = next((s for s in spaces if s['id'] == session.space_id), None)
        
        if not space:
            raise ValueError(f"Space {session.space_id} not found")
        
        # Получить следующий номер
        next_spot_number = space.get('next_spot_number', 1)
        
        # Получить существующие spots
        all_spots = self.store.get_spots()
        
        created_spots = []
        
        for idx in approved_indices:
            if idx >= len(session.proposals):
                continue
            
            proposal = session.proposals[idx]
            
            # Создать новое парковочное место
            spot_id = f"spot_{uuid.uuid4().hex[:8]}"
            
            if auto_number:
                label = f"{label_prefix}{next_spot_number}"
                spot_number = next_spot_number
                next_spot_number += 1
            else:
                label = proposal.suggested_label
                spot_number = None
            
            new_spot = {
                'id': spot_id,
                'space_id': session.space_id,
                'camera_id': session.camera_id,
                'type': 'parking',
                'label': label,
                'spot_number': spot_number,
                'rect': proposal.suggested_rect,
                'alternative_views': [],
                'created_by': 'auto_markup',
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
            all_spots.append(new_spot)
            created_spots.append(spot_id)
        
        # Сохранить spots
        self.store.save_spots(all_spots)
        
        # Обновить next_spot_number в space
        if auto_number:
            space['next_spot_number'] = next_spot_number
            self.store.save_spaces(spaces)
        
        logger.info(f"Created {len(created_spots)} spots from session {session_id}")
        
        return {
            'created_spots': len(created_spots),
            'spot_ids': created_spots,
            'next_spot_number': next_spot_number
        }
    
    def cancel_analysis(self, session_id: str) -> bool:
        """Отменить анализ."""
        session = self.sessions.get(session_id)
        if not session:
            return False
        
        session.status = 'cancelled'
        logger.info(f"Cancelled analysis session {session_id}")
        return True
    
    def delete_session(self, session_id: str) -> bool:
        """Удалить сессию."""
        with self.lock:
            if session_id in self.sessions:
                del self.sessions[session_id]
                logger.info(f"Deleted session {session_id}")
                return True
        return False

