"""
API endpoints для управления YOLO моделями.
"""
from flask import Blueprint, request, jsonify
import logging

logger = logging.getLogger(__name__)

models_bp = Blueprint('models', __name__)


def init_models_api(store, detector, model_manager, video_manager):
    """Инициализировать API моделей."""
    
    @models_bp.route('/api/models/available', methods=['GET'])
    def get_available_models():
        """Получить список всех доступных моделей."""
        try:
            models = model_manager.list_available_models()
            return jsonify({'models': models}), 200
        except Exception as e:
            logger.error(f"Error listing available models: {e}")
            return jsonify({'error': str(e)}), 500
    
    @models_bp.route('/api/models/downloaded', methods=['GET'])
    def get_downloaded_models():
        """Получить список загруженных моделей."""
        try:
            models = model_manager.list_downloaded_models()
            return jsonify({'models': models}), 200
        except Exception as e:
            logger.error(f"Error listing downloaded models: {e}")
            return jsonify({'error': str(e)}), 500
    
    @models_bp.route('/api/models/current', methods=['GET'])
    def get_current_model():
        """Получить информацию о текущей используемой модели."""
        try:
            model_info = detector.get_model_info()
            return jsonify(model_info), 200
        except Exception as e:
            logger.error(f"Error getting current model info: {e}")
            return jsonify({'error': str(e)}), 500
    
    @models_bp.route('/api/models/download', methods=['POST'])
    def download_model():
        """Загрузить YOLO модель."""
        try:
            data = request.json
            filename = data.get('filename')
            
            if not filename:
                return jsonify({'error': 'filename required'}), 400
            
            # Проверить доступность модели
            from backend.services.model_manager import AVAILABLE_YOLO_MODELS
            if filename not in AVAILABLE_YOLO_MODELS:
                return jsonify({'error': f'Unknown model: {filename}'}), 400
            
            # Проверить уже загружена ли
            if model_manager._is_model_downloaded(filename):
                return jsonify({'message': 'Model already downloaded', 'filename': filename}), 200
            
            # Загрузить модель
            logger.info(f"Starting download of {filename}")
            model_info = model_manager.download_model(filename)
            
            logger.info(f"Successfully downloaded {filename}")
            return jsonify({
                'message': 'Model downloaded successfully',
                'model': model_info
            }), 200
        
        except Exception as e:
            logger.error(f"Error downloading model: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @models_bp.route('/api/models/delete/<filename>', methods=['DELETE'])
    def delete_model(filename):
        """Удалить модель."""
        try:
            # Проверить что это не текущая модель
            current_model = detector.model_path
            if filename in current_model:
                return jsonify({'error': 'Cannot delete currently active model'}), 400
            
            success = model_manager.delete_model(filename)
            
            if not success:
                return jsonify({'error': 'Model not found or could not be deleted'}), 404
            
            return jsonify({'message': 'Model deleted successfully'}), 200
        
        except Exception as e:
            logger.error(f"Error deleting model: {e}")
            return jsonify({'error': str(e)}), 500
    
    @models_bp.route('/api/models/activate', methods=['POST'])
    def activate_model():
        """Активировать (сменить) модель."""
        try:
            data = request.json
            filename = data.get('filename')
            
            if not filename:
                return jsonify({'error': 'filename required'}), 400
            
            # Получить путь к модели
            model_path = model_manager.get_model_path_for_detector(filename)
            
            # Сменить модель в детекторе (может выбросить RuntimeError)
            try:
                success = detector.change_model(model_path)
                if not success:
                    return jsonify({
                        'error': 'Не удалось загрузить модель',
                        'requires_upgrade': 'yolo11' in filename.lower()
                    }), 500
            except RuntimeError as runtime_error:
                # Ошибка совместимости версий уже обработана в detector.change_model
                error_msg = str(runtime_error)
                logger.error(f"Version compatibility error: {error_msg}")
                return jsonify({
                    'error': error_msg,
                    'requires_upgrade': True,
                    'solution': 'pip install --upgrade ultralytics>=8.3.0'
                }), 500
            
            # Сохранить в конфиг
            store.update_config({'active_model': filename})
            
            logger.info(f"Activated model: {filename}")
            return jsonify({
                'message': 'Model activated successfully',
                'model_info': detector.get_model_info()
            }), 200
        
        except RuntimeError as e:
            # Обработка ошибок совместимости версий
            error_msg = str(e)
            logger.error(f"Error activating model (version compatibility): {e}", exc_info=True)
            return jsonify({
                'error': error_msg,
                'requires_upgrade': 'yolo11' in filename.lower() if 'filename' in locals() else False,
                'solution': 'pip install --upgrade ultralytics>=8.3.0'
            }), 500
        except Exception as e:
            logger.error(f"Error activating model: {e}", exc_info=True)
            error_msg = str(e)
            # Проверяем на признаки проблемы совместимости
            if 'C3k2' in error_msg or 'ultralytics.nn.modules.block' in error_msg:
                return jsonify({
                    'error': (
                        f"Проблема совместимости версий ultralytics. "
                        f"Обновите: pip install --upgrade ultralytics>=8.3.0"
                    ),
                    'original_error': error_msg,
                    'requires_upgrade': True,
                    'solution': 'pip install --upgrade ultralytics>=8.3.0'
                }), 500
            return jsonify({'error': error_msg}), 500
    
    @models_bp.route('/api/models/test', methods=['POST'])
    def test_detection():
        """Тестировать детекцию на кадре с камеры."""
        try:
            data = request.json
            camera_id = data.get('camera_id')
            
            if not camera_id:
                return jsonify({'error': 'camera_id required'}), 400
            
            # Проверить камеру
            if not video_manager.is_camera_alive(camera_id):
                return jsonify({'error': 'Camera not available'}), 503
            
            # Получить кадр
            frame = video_manager.get_frame(camera_id)
            
            if frame is None:
                return jsonify({'error': 'No frame available'}), 503
            
            # Запустить детекцию
            detections = detector.detect(frame)
            
            # Конвертировать в JSON
            detections_json = [
                {
                    'bbox': list(det.bbox),
                    'confidence': det.confidence,
                    'class_name': det.class_name
                }
                for det in detections
            ]
            
            logger.info(f"Test detection on {camera_id}: found {len(detections)} vehicles")
            
            return jsonify({
                'camera_id': camera_id,
                'detections_count': len(detections),
                'detections': detections_json,
                'model_used': detector.model_path,
                'confidence_threshold': detector.confidence_threshold
            }), 200
        
        except Exception as e:
            logger.error(f"Error testing detection: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @models_bp.route('/api/models/set-confidence', methods=['PUT'])
    def set_confidence():
        """Установить порог уверенности."""
        try:
            data = request.json
            threshold = float(data.get('threshold', 0.5))
            
            detector.set_confidence_threshold(threshold)
            
            # Сохранить в конфиг
            store.update_config({'confidence_threshold': threshold})
            
            return jsonify({
                'message': 'Confidence threshold updated',
                'threshold': threshold
            }), 200
        
        except Exception as e:
            logger.error(f"Error setting confidence: {e}")
            return jsonify({'error': str(e)}), 500
    
    return models_bp

