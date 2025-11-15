"""
Parking space management API endpoints.
"""
from flask import Blueprint, request, jsonify, send_from_directory
import logging
import uuid
import os
import base64
from pathlib import Path
from werkzeug.utils import secure_filename

logger = logging.getLogger(__name__)

spaces_bp = Blueprint('spaces', __name__)


def init_spaces_api(store, state_manager):
    """Initialize spaces API with dependencies."""
    
    @spaces_bp.route('/api/spaces', methods=['GET'])
    def get_spaces():
        """Get all parking spaces."""
        try:
            spaces = store.get_spaces()
            return jsonify({'spaces': spaces}), 200
        except Exception as e:
            logger.error(f"Error getting spaces: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spaces_bp.route('/api/spaces/<space_id>', methods=['GET'])
    def get_space(space_id):
        """Get a specific parking space with state."""
        try:
            spaces = store.get_spaces()
            space = next((s for s in spaces if s['id'] == space_id), None)
            
            if not space:
                return jsonify({'error': 'Space not found'}), 404
            
            # Add state information
            space_state = state_manager.get_space_state(space_id)
            if space_state:
                space['state'] = space_state
            
            return jsonify(space), 200
        except Exception as e:
            logger.error(f"Error getting space: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spaces_bp.route('/api/spaces', methods=['POST'])
    def create_space():
        """Create a new parking space."""
        try:
            data = request.json
            name = data.get('name')
            
            if not name:
                return jsonify({'error': 'name required'}), 400
            
            spaces = store.get_spaces()
            
            # Generate unique ID
            space_id = f"space_{uuid.uuid4().hex[:8]}"
            
            new_space = {
                'id': space_id,
                'name': name,
                'camera_ids': [],
                'next_spot_number': 1,
                'spot_numbering_scheme': 'sequential'
            }
            
            spaces.append(new_space)
            store.save_spaces(spaces)
            
            # Initialize state
            state_manager.initialize_space(space_id)
            
            logger.info(f"Created space: {space_id} ({name})")
            return jsonify(new_space), 201
        
        except Exception as e:
            logger.error(f"Error creating space: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spaces_bp.route('/api/spaces/<space_id>', methods=['PUT'])
    def update_space(space_id):
        """Update a parking space."""
        try:
            data = request.json
            spaces = store.get_spaces()
            
            space = next((s for s in spaces if s['id'] == space_id), None)
            if not space:
                return jsonify({'error': 'Space not found'}), 404
            
            # Update fields
            if 'name' in data:
                space['name'] = data['name']
            
            store.save_spaces(spaces)
            logger.info(f"Updated space: {space_id}")
            
            return jsonify(space), 200
        
        except Exception as e:
            logger.error(f"Error updating space: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spaces_bp.route('/api/spaces/<space_id>', methods=['DELETE'])
    def delete_space(space_id):
        """Delete a parking space."""
        try:
            spaces = store.get_spaces()
            space = next((s for s in spaces if s['id'] == space_id), None)
            
            if not space:
                return jsonify({'error': 'Space not found'}), 404
            
            # Remove from spaces list
            spaces = [s for s in spaces if s['id'] != space_id]
            store.save_spaces(spaces)
            
            # Remove associated spots
            spots = store.get_spots()
            spots = [s for s in spots if s['space_id'] != space_id]
            store.save_spots(spots)
            
            # Remove from state
            state_manager.remove_space(space_id)
            
            # Update cameras
            cameras = store.get_cameras()
            for camera in cameras:
                if space_id in camera.get('assigned_space_ids', []):
                    camera['assigned_space_ids'].remove(space_id)
            store.save_cameras(cameras)
            
            logger.info(f"Deleted space: {space_id}")
            return jsonify({'message': 'Space deleted'}), 200
        
        except Exception as e:
            logger.error(f"Error deleting space: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spaces_bp.route('/api/spaces/<space_id>/assign_camera', methods=['POST'])
    def assign_camera_to_space(space_id):
        """Assign a camera to a parking space."""
        try:
            data = request.json
            camera_id = data.get('camera_id')
            
            if not camera_id:
                return jsonify({'error': 'camera_id required'}), 400
            
            spaces = store.get_spaces()
            cameras = store.get_cameras()
            
            space = next((s for s in spaces if s['id'] == space_id), None)
            camera = next((c for c in cameras if c['id'] == camera_id), None)
            
            if not space:
                return jsonify({'error': 'Space not found'}), 404
            if not camera:
                return jsonify({'error': 'Camera not found'}), 404
            
            # Add camera to space
            if camera_id not in space['camera_ids']:
                space['camera_ids'].append(camera_id)
            
            # Add space to camera
            if space_id not in camera['assigned_space_ids']:
                camera['assigned_space_ids'].append(space_id)
            
            store.save_spaces(spaces)
            store.save_cameras(cameras)
            
            logger.info(f"Assigned camera {camera_id} to space {space_id}")
            return jsonify({'message': 'Camera assigned'}), 200
        
        except Exception as e:
            logger.error(f"Error assigning camera: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spaces_bp.route('/api/spaces/<space_id>/unassign_camera', methods=['POST'])
    def unassign_camera_from_space(space_id):
        """Unassign a camera from a parking space."""
        try:
            data = request.json
            camera_id = data.get('camera_id')
            
            if not camera_id:
                return jsonify({'error': 'camera_id required'}), 400
            
            spaces = store.get_spaces()
            cameras = store.get_cameras()
            
            space = next((s for s in spaces if s['id'] == space_id), None)
            camera = next((c for c in cameras if c['id'] == camera_id), None)
            
            if not space:
                return jsonify({'error': 'Space not found'}), 404
            if not camera:
                return jsonify({'error': 'Camera not found'}), 404
            
            # Remove camera from space
            if camera_id in space['camera_ids']:
                space['camera_ids'].remove(camera_id)
            
            # Remove space from camera
            if space_id in camera['assigned_space_ids']:
                camera['assigned_space_ids'].remove(space_id)
            
            store.save_spaces(spaces)
            store.save_cameras(cameras)
            
            logger.info(f"Unassigned camera {camera_id} from space {space_id}")
            return jsonify({'message': 'Camera unassigned'}), 200
        
        except Exception as e:
            logger.error(f"Error unassigning camera: {e}")
            return jsonify({'error': str(e)}), 500
    
    # Top view plan endpoints
    @spaces_bp.route('/api/spaces/<space_id>/top-view-plan', methods=['GET'])
    def get_top_view_plan(space_id):
        """Get top view plan for a parking space."""
        try:
            spaces = store.get_spaces()
            space = next((s for s in spaces if s['id'] == space_id), None)
            
            if not space:
                return jsonify({'error': 'Space not found'}), 404
            
            plan_data = space.get('top_view_plan', {})
            return jsonify(plan_data), 200
        
        except Exception as e:
            logger.error(f"Error getting top view plan: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spaces_bp.route('/api/spaces/<space_id>/top-view-plan', methods=['POST'])
    def upload_top_view_plan(space_id):
        """Upload top view plan image for a parking space."""
        try:
            spaces = store.get_spaces()
            space = next((s for s in spaces if s['id'] == space_id), None)
            
            if not space:
                return jsonify({'error': 'Space not found'}), 404
            
            # Create directory for space plans
            data_dir = Path(store.data_dir)
            plans_dir = data_dir / 'spaces' / space_id
            plans_dir.mkdir(parents=True, exist_ok=True)
            
            if 'image' in request.files:
                # File upload
                file = request.files['image']
                if file and file.filename:
                    filename = secure_filename(file.filename)
                    # Save as top_view.jpg
                    filepath = plans_dir / 'top_view.jpg'
                    file.save(str(filepath))
                    
                    image_path = f'spaces/{space_id}/top_view.jpg'
                else:
                    return jsonify({'error': 'No file provided'}), 400
            elif 'image_data' in request.json:
                # Base64 data
                image_data = request.json['image_data']
                if image_data.startswith('data:image'):
                    # Remove data URL prefix
                    header, encoded = image_data.split(',', 1)
                    image_bytes = base64.b64decode(encoded)
                    
                    filepath = plans_dir / 'top_view.jpg'
                    with open(filepath, 'wb') as f:
                        f.write(image_bytes)
                    
                    image_path = f'spaces/{space_id}/top_view.jpg'
                else:
                    return jsonify({'error': 'Invalid image data format'}), 400
            else:
                return jsonify({'error': 'No image provided'}), 400
            
            # Initialize or update top_view_plan
            if 'top_view_plan' not in space:
                space['top_view_plan'] = {}
            
            space['top_view_plan']['top_view_image'] = image_path
            if 'top_view_spots' not in space['top_view_plan']:
                space['top_view_plan']['top_view_spots'] = []
            
            store.save_spaces(spaces)
            
            logger.info(f"Uploaded top view plan for space {space_id}")
            return jsonify({
                'message': 'Plan uploaded',
                'image_path': image_path
            }), 200
        
        except Exception as e:
            logger.error(f"Error uploading top view plan: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spaces_bp.route('/api/spaces/<space_id>/top-view-plan/image', methods=['GET'])
    def get_top_view_plan_image(space_id):
        """Get top view plan image file."""
        try:
            spaces = store.get_spaces()
            space = next((s for s in spaces if s['id'] == space_id), None)
            
            if not space:
                return jsonify({'error': 'Space not found'}), 404
            
            plan_data = space.get('top_view_plan', {})
            image_path = plan_data.get('top_view_image')
            
            if not image_path:
                return jsonify({'error': 'No plan image found'}), 404
            
            # Serve file from data directory
            data_dir = Path(store.data_dir)
            file_path = data_dir / image_path
            
            if not file_path.exists():
                return jsonify({'error': 'Image file not found'}), 404
            
            return send_from_directory(
                str(file_path.parent),
                file_path.name,
                mimetype='image/jpeg'
            )
        
        except Exception as e:
            logger.error(f"Error getting top view plan image: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spaces_bp.route('/api/spaces/<space_id>/top-view-plan/spots', methods=['PUT'])
    def update_top_view_plan_spots(space_id):
        """Update spot mappings for top view plan."""
        try:
            data = request.json
            top_view_spots = data.get('top_view_spots', [])
            
            spaces = store.get_spaces()
            space = next((s for s in spaces if s['id'] == space_id), None)
            
            if not space:
                return jsonify({'error': 'Space not found'}), 404
            
            # Initialize top_view_plan if needed
            if 'top_view_plan' not in space:
                space['top_view_plan'] = {}
            
            space['top_view_plan']['top_view_spots'] = top_view_spots
            
            # Update other plan settings if provided
            if 'plan_scale' in data:
                space['top_view_plan']['plan_scale'] = data['plan_scale']
            if 'plan_offset' in data:
                space['top_view_plan']['plan_offset'] = data['plan_offset']
            
            store.save_spaces(spaces)
            
            logger.info(f"Updated top view plan spots for space {space_id}")
            return jsonify({
                'message': 'Plan spots updated',
                'top_view_spots': top_view_spots
            }), 200
        
        except Exception as e:
            logger.error(f"Error updating top view plan spots: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spaces_bp.route('/api/spaces/<space_id>/top-view-plan/spot-mapping', methods=['POST'])
    def create_spot_mapping(space_id):
        """Create or update a single spot mapping on the plan."""
        try:
            data = request.json
            spot_id = data.get('spot_id')
            plan_coords = data.get('plan_coords')
            rotation = data.get('rotation', 0)
            
            if not spot_id or not plan_coords:
                return jsonify({'error': 'spot_id and plan_coords required'}), 400
            
            spaces = store.get_spaces()
            space = next((s for s in spaces if s['id'] == space_id), None)
            
            if not space:
                return jsonify({'error': 'Space not found'}), 404
            
            # Verify spot exists and belongs to this space
            spots = store.get_spots()
            spot = next((s for s in spots if s['id'] == spot_id and s['space_id'] == space_id), None)
            
            if not spot:
                return jsonify({'error': 'Spot not found or does not belong to this space'}), 404
            
            # Initialize top_view_plan if needed
            if 'top_view_plan' not in space:
                space['top_view_plan'] = {
                    'top_view_spots': []
                }
            
            if 'top_view_spots' not in space['top_view_plan']:
                space['top_view_plan']['top_view_spots'] = []
            
            # Find existing mapping or create new
            existing = next(
                (s for s in space['top_view_plan']['top_view_spots'] if s['spot_id'] == spot_id),
                None
            )
            
            if existing:
                existing['plan_coords'] = plan_coords
                existing['rotation'] = rotation
            else:
                space['top_view_plan']['top_view_spots'].append({
                    'spot_id': spot_id,
                    'plan_coords': plan_coords,
                    'rotation': rotation
                })
            
            store.save_spaces(spaces)
            
            logger.info(f"Created/updated spot mapping for {spot_id} in space {space_id}")
            return jsonify({
                'message': 'Spot mapping updated',
                'spot_id': spot_id
            }), 200
        
        except Exception as e:
            logger.error(f"Error creating spot mapping: {e}")
            return jsonify({'error': str(e)}), 500
    
    return spaces_bp

