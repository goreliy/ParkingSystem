"""
Camera management API endpoints.
"""
from flask import Blueprint, request, jsonify
import logging
import uuid

logger = logging.getLogger(__name__)

cameras_bp = Blueprint('cameras', __name__)


def init_cameras_api(store, video_manager):
    """Initialize cameras API with dependencies."""
    
    @cameras_bp.route('/api/cameras', methods=['GET'])
    def get_cameras():
        """Get all cameras."""
        try:
            cameras = store.get_cameras()
            # Инициализация exclusion_zones для старых камер
            for camera in cameras:
                if 'exclusion_zones' not in camera:
                    camera['exclusion_zones'] = []
            return jsonify({'cameras': cameras}), 200
        except Exception as e:
            logger.error(f"Error getting cameras: {e}")
            return jsonify({'error': str(e)}), 500
    
    @cameras_bp.route('/api/cameras/<camera_id>', methods=['GET'])
    def get_camera(camera_id):
        """Get a specific camera."""
        try:
            cameras = store.get_cameras()
            camera = next((c for c in cameras if c['id'] == camera_id), None)
            
            if not camera:
                return jsonify({'error': 'Camera not found'}), 404
            
            # Add live status
            camera['is_alive'] = video_manager.is_camera_alive(camera_id)
            
            # Инициализация exclusion_zones для старых камер
            if 'exclusion_zones' not in camera:
                camera['exclusion_zones'] = []
            
            return jsonify(camera), 200
        except Exception as e:
            logger.error(f"Error getting camera: {e}")
            return jsonify({'error': str(e)}), 500
    
    @cameras_bp.route('/api/cameras', methods=['POST'])
    def create_camera():
        """Create a new camera."""
        try:
            data = request.json
            name = data.get('name')
            rtsp_url = data.get('rtsp_url')
            
            if not name or not rtsp_url:
                return jsonify({'error': 'name and rtsp_url required'}), 400
            
            cameras = store.get_cameras()
            
            # Generate unique ID
            camera_id = f"cam_{uuid.uuid4().hex[:8]}"
            
            new_camera = {
                'id': camera_id,
                'name': name,
                'rtsp_url': rtsp_url,
                'assigned_space_ids': [],
                'exclusion_zones': []  # Зоны, исключённые из парковки
            }
            
            cameras.append(new_camera)
            store.save_cameras(cameras)
            
            # Start video processor
            video_manager.add_camera(camera_id, rtsp_url)
            
            logger.info(f"Created camera: {camera_id} ({name})")
            return jsonify(new_camera), 201
        
        except Exception as e:
            logger.error(f"Error creating camera: {e}")
            return jsonify({'error': str(e)}), 500
    
    @cameras_bp.route('/api/cameras/<camera_id>', methods=['PUT'])
    def update_camera(camera_id):
        """Update a camera."""
        try:
            data = request.json
            cameras = store.get_cameras()
            
            camera = next((c for c in cameras if c['id'] == camera_id), None)
            if not camera:
                return jsonify({'error': 'Camera not found'}), 404
            
            # Update fields
            if 'name' in data:
                camera['name'] = data['name']
            
            if 'rtsp_url' in data and data['rtsp_url'] != camera['rtsp_url']:
                camera['rtsp_url'] = data['rtsp_url']
                # Restart video processor with new URL
                video_manager.remove_camera(camera_id)
                video_manager.add_camera(camera_id, camera['rtsp_url'])
            
            if 'exclusion_zones' in data:
                camera['exclusion_zones'] = data['exclusion_zones']
            
            # Инициализация exclusion_zones для старых камер
            if 'exclusion_zones' not in camera:
                camera['exclusion_zones'] = []
            
            store.save_cameras(cameras)
            logger.info(f"Updated camera: {camera_id}")
            
            return jsonify(camera), 200
        
        except Exception as e:
            logger.error(f"Error updating camera: {e}")
            return jsonify({'error': str(e)}), 500
    
    @cameras_bp.route('/api/cameras/<camera_id>', methods=['DELETE'])
    def delete_camera(camera_id):
        """Delete a camera."""
        try:
            cameras = store.get_cameras()
            camera = next((c for c in cameras if c['id'] == camera_id), None)
            
            if not camera:
                return jsonify({'error': 'Camera not found'}), 404
            
            # Remove from video manager
            video_manager.remove_camera(camera_id)
            
            # Remove from cameras list
            cameras = [c for c in cameras if c['id'] != camera_id]
            store.save_cameras(cameras)
            
            # Remove from spaces
            spaces = store.get_spaces()
            for space in spaces:
                if camera_id in space.get('camera_ids', []):
                    space['camera_ids'].remove(camera_id)
            store.save_spaces(spaces)
            
            logger.info(f"Deleted camera: {camera_id}")
            return jsonify({'message': 'Camera deleted'}), 200
        
        except Exception as e:
            logger.error(f"Error deleting camera: {e}")
            return jsonify({'error': str(e)}), 500
    
    @cameras_bp.route('/api/cameras/<camera_id>/exclusion-zones', methods=['PUT'])
    def update_exclusion_zones(camera_id):
        """Обновить исключённые зоны для камеры."""
        try:
            data = request.json
            exclusion_zones = data.get('exclusion_zones', [])
            
            # Валидация формата
            if not isinstance(exclusion_zones, list):
                return jsonify({'error': 'exclusion_zones must be a list'}), 400
            
            for zone in exclusion_zones:
                if not all(key in zone for key in ['x1', 'y1', 'x2', 'y2']):
                    return jsonify({'error': 'Each zone must have x1, y1, x2, y2'}), 400
            
            cameras = store.get_cameras()
            camera = next((c for c in cameras if c['id'] == camera_id), None)
            
            if not camera:
                return jsonify({'error': 'Camera not found'}), 404
            
            camera['exclusion_zones'] = exclusion_zones
            store.save_cameras(cameras)
            
            logger.info(f"Updated exclusion zones for camera {camera_id}: {len(exclusion_zones)} zones")
            return jsonify(camera), 200
        
        except Exception as e:
            logger.error(f"Error updating exclusion zones: {e}")
            return jsonify({'error': str(e)}), 500
    
    return cameras_bp

