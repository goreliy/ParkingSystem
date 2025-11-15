"""
Parking spots management API endpoints.
"""
from flask import Blueprint, request, jsonify
import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

spots_bp = Blueprint('spots', __name__)


def init_spots_api(store, state_manager):
    """Initialize spots API with dependencies."""
    
    @spots_bp.route('/api/spots', methods=['GET'])
    def get_spots():
        """Get all parking spots."""
        try:
            space_id = request.args.get('space_id')
            spots = store.get_spots()
            
            if space_id:
                spots = [s for s in spots if s['space_id'] == space_id]
            
            return jsonify({'spots': spots}), 200
        except Exception as e:
            logger.error(f"Error getting spots: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spots_bp.route('/api/spots/<spot_id>', methods=['GET'])
    def get_spot(spot_id):
        """Get a specific spot."""
        try:
            spots = store.get_spots()
            spot = next((s for s in spots if s['id'] == spot_id), None)
            
            if not spot:
                return jsonify({'error': 'Spot not found'}), 404
            
            return jsonify(spot), 200
        except Exception as e:
            logger.error(f"Error getting spot: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spots_bp.route('/api/spots', methods=['POST'])
    def create_spot():
        """Create a new parking spot."""
        try:
            data = request.json
            space_id = data.get('space_id')
            spot_type = data.get('type', 'parking')
            label = data.get('label', '')
            rect = data.get('rect')
            
            if not space_id or not rect:
                return jsonify({'error': 'space_id and rect required'}), 400
            
            if spot_type not in ['parking', 'nopark']:
                return jsonify({'error': 'type must be parking or nopark'}), 400
            
            # Validate rect
            if not all(k in rect for k in ['x1', 'y1', 'x2', 'y2']):
                return jsonify({'error': 'rect must have x1, y1, x2, y2'}), 400
            
            spots = store.get_spots()
            
            # Получить зону для сквозной нумерации
            spaces = store.get_spaces()
            space = next((s for s in spaces if s['id'] == space_id), None)
            
            if not space:
                return jsonify({'error': 'Space not found'}), 404
            
            # Generate unique ID
            spot_id = f"spot_{uuid.uuid4().hex[:8]}"
            
            # Получить camera_id из данных или использовать первую камеру зоны
            camera_id = data.get('camera_id')
            if not camera_id and space.get('camera_ids'):
                camera_id = space['camera_ids'][0]
            
            # Получить или сгенерировать spot_number
            spot_number = data.get('spot_number')
            if spot_number is None:
                spot_number = space.get('next_spot_number', 1)
                # Обновить счетчик
                space['next_spot_number'] = spot_number + 1
                store.save_spaces(spaces)
            
            new_spot = {
                'id': spot_id,
                'space_id': space_id,
                'camera_id': camera_id,
                'type': spot_type,
                'label': label,
                'spot_number': spot_number,
                'rect': rect,
                'alternative_views': data.get('alternative_views', []),
                'created_by': data.get('created_by', 'manual'),
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
            spots.append(new_spot)
            store.save_spots(spots)
            
            # Update space stats
            state_manager.initialize_space(space_id)
            
            logger.info(f"Created spot: {spot_id} in space {space_id}")
            return jsonify(new_spot), 201
        
        except Exception as e:
            logger.error(f"Error creating spot: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spots_bp.route('/api/spots/<spot_id>', methods=['PUT'])
    def update_spot(spot_id):
        """Update a parking spot."""
        try:
            data = request.json
            spots = store.get_spots()
            
            spot = next((s for s in spots if s['id'] == spot_id), None)
            if not spot:
                return jsonify({'error': 'Spot not found'}), 404
            
            # Update fields
            if 'label' in data:
                spot['label'] = data['label']
            
            if 'type' in data:
                if data['type'] not in ['parking', 'nopark']:
                    return jsonify({'error': 'type must be parking or nopark'}), 400
                old_type = spot.get('type')
                spot['type'] = data['type']
                
                # Add excluded_at timestamp when excluding a spot
                if old_type == 'parking' and data['type'] == 'nopark':
                    spot['excluded_at'] = datetime.now(timezone.utc).isoformat()
                # Remove excluded_at when restoring
                elif old_type == 'nopark' and data['type'] == 'parking':
                    spot.pop('excluded_at', None)
            
            if 'rect' in data:
                rect = data['rect']
                if not all(k in rect for k in ['x1', 'y1', 'x2', 'y2']):
                    return jsonify({'error': 'rect must have x1, y1, x2, y2'}), 400
                spot['rect'] = rect
            
            store.save_spots(spots)
            
            # Update space stats
            state_manager.initialize_space(spot['space_id'])
            
            logger.info(f"Updated spot: {spot_id}")
            return jsonify(spot), 200
        
        except Exception as e:
            logger.error(f"Error updating spot: {e}")
            return jsonify({'error': str(e)}), 500
    
    @spots_bp.route('/api/spots/<spot_id>', methods=['DELETE'])
    def delete_spot(spot_id):
        """Delete a parking spot."""
        try:
            spots = store.get_spots()
            spot = next((s for s in spots if s['id'] == spot_id), None)
            
            if not spot:
                return jsonify({'error': 'Spot not found'}), 404
            
            space_id = spot['space_id']
            
            # Remove from spots list
            spots = [s for s in spots if s['id'] != spot_id]
            store.save_spots(spots)
            
            # Update space stats
            state_manager.initialize_space(space_id)
            
            logger.info(f"Deleted spot: {spot_id}")
            return jsonify({'message': 'Spot deleted'}), 200
        
        except Exception as e:
            logger.error(f"Error deleting spot: {e}")
            return jsonify({'error': str(e)}), 500
    
    return spots_bp

