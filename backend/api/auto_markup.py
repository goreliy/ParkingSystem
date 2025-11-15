"""
API endpoints для автоматической разметки парковочных мест.
"""
from flask import Blueprint, request, jsonify, Response
import logging
import cv2

logger = logging.getLogger(__name__)

auto_markup_bp = Blueprint('auto_markup', __name__)


def init_auto_markup_api(store, video_manager, detector, auto_markup_service):
    """Инициализировать API автоматической разметки."""
    
    @auto_markup_bp.route('/api/auto-markup/start', methods=['POST'])
    def start_analysis():
        """Запустить анализ для автоматической разметки."""
        try:
            data = request.json
            
            space_id = data.get('space_id')
            if not space_id:
                return jsonify({'error': 'space_id required'}), 400
            
            mode = data.get('mode', 'average')
            if mode not in ['single', 'average', 'duration']:
                return jsonify({'error': 'Invalid mode'}), 400
            
            duration_seconds = int(data.get('duration_seconds', 60))
            # standard_spot_width/height теперь в процентах (100-200)
            standard_spot_width = int(data.get('standard_spot_width', 120))
            standard_spot_height = int(data.get('standard_spot_height', 120))
            stability_seconds = int(data.get('stability_seconds', 30))
            
            # Запустить анализ
            session_id = auto_markup_service.start_analysis(
                space_id=space_id,
                mode=mode,
                duration_seconds=duration_seconds,
                standard_spot_width=standard_spot_width,
                standard_spot_height=standard_spot_height,
                stability_seconds=stability_seconds
            )
            
            logger.info(f"Started auto-markup analysis: {session_id}")
            
            return jsonify({
                'session_id': session_id,
                'status': 'analyzing',
                'mode': mode
            }), 201
        
        except Exception as e:
            logger.error(f"Error starting auto-markup: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @auto_markup_bp.route('/api/auto-markup/progress/<session_id>', methods=['GET'])
    def get_progress(session_id):
        """Получить прогресс анализа."""
        try:
            progress = auto_markup_service.get_analysis_progress(session_id)
            
            if not progress:
                return jsonify({'error': 'Session not found'}), 404
            
            return jsonify(progress), 200
        
        except Exception as e:
            logger.error(f"Error getting progress: {e}")
            return jsonify({'error': str(e)}), 500
    
    @auto_markup_bp.route('/api/auto-markup/proposals/<session_id>', methods=['GET'])
    def get_proposals(session_id):
        """Получить предложения парковочных мест."""
        try:
            proposals_data = auto_markup_service.get_proposals(session_id)
            
            if not proposals_data:
                return jsonify({'error': 'Session not found'}), 404
            
            return jsonify(proposals_data), 200
        
        except Exception as e:
            logger.error(f"Error getting proposals: {e}")
            return jsonify({'error': str(e)}), 500
    
    @auto_markup_bp.route('/api/auto-markup/preview/<session_id>', methods=['GET'])
    def get_preview_image(session_id):
        """Получить превью изображение с предложениями."""
        try:
            frame = auto_markup_service.get_preview_image(session_id)
            
            if frame is None:
                return jsonify({'error': 'Preview not available'}), 404
            
            # Encode as JPEG
            success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
            if not success:
                return jsonify({'error': 'Failed to encode image'}), 500
            
            return Response(
                buffer.tobytes(),
                mimetype='image/jpeg',
                headers={'Cache-Control': 'no-cache, no-store, must-revalidate'}
            )
        
        except Exception as e:
            logger.error(f"Error getting preview image: {e}")
            return jsonify({'error': str(e)}), 500
    
    @auto_markup_bp.route('/api/auto-markup/apply', methods=['POST'])
    def apply_proposals():
        """Применить одобренные предложения."""
        try:
            data = request.json
            
            session_id = data.get('session_id')
            if not session_id:
                return jsonify({'error': 'session_id required'}), 400
            
            approved_indices = data.get('approved_indices', [])
            label_prefix = data.get('label_prefix', 'A')
            auto_number = data.get('auto_number', True)
            
            result = auto_markup_service.apply_proposals(
                session_id=session_id,
                approved_indices=approved_indices,
                label_prefix=label_prefix,
                auto_number=auto_number
            )
            
            logger.info(f"Applied {result['created_spots']} proposals from session {session_id}")
            
            return jsonify(result), 200
        
        except Exception as e:
            logger.error(f"Error applying proposals: {e}", exc_info=True)
            return jsonify({'error': str(e)}), 500
    
    @auto_markup_bp.route('/api/auto-markup/cancel/<session_id>', methods=['DELETE'])
    def cancel_analysis(session_id):
        """Отменить анализ."""
        try:
            success = auto_markup_service.cancel_analysis(session_id)
            
            if not success:
                return jsonify({'error': 'Session not found'}), 404
            
            return jsonify({'message': 'Analysis cancelled'}), 200
        
        except Exception as e:
            logger.error(f"Error cancelling analysis: {e}")
            return jsonify({'error': str(e)}), 500
    
    @auto_markup_bp.route('/api/auto-markup/sessions', methods=['GET'])
    def list_sessions():
        """Получить список всех сессий."""
        try:
            sessions = []
            for session_id, session in auto_markup_service.sessions.items():
                sessions.append({
                    'session_id': session_id,
                    'space_id': session.space_id,
                    'camera_id': session.camera_id,
                    'mode': session.mode,
                    'status': session.status,
                    'progress': session.progress,
                    'proposals_count': len(session.proposals),
                    'started_at': session.started_at.isoformat()
                })
            
            return jsonify({'sessions': sessions}), 200
        
        except Exception as e:
            logger.error(f"Error listing sessions: {e}")
            return jsonify({'error': str(e)}), 500
    
    @auto_markup_bp.route('/api/auto-markup/toggle-proposal/<session_id>/<int:proposal_index>', methods=['PUT'])
    def toggle_proposal_validity(session_id, proposal_index):
        """Переключить валидность предложения (исключить/включить)."""
        try:
            data = request.json
            is_valid = data.get('is_valid', True)
            exclude_reason = data.get('exclude_reason')
            
            session = auto_markup_service.sessions.get(session_id)
            if not session:
                return jsonify({'error': 'Session not found'}), 404
            
            if proposal_index >= len(session.proposals):
                return jsonify({'error': 'Invalid proposal index'}), 400
            
            proposal = session.proposals[proposal_index]
            proposal.is_valid = is_valid
            
            if not is_valid and exclude_reason:
                proposal.exclude_reason = exclude_reason
            elif is_valid:
                proposal.exclude_reason = None
            
            logger.info(f"Toggled proposal {proposal_index} in session {session_id}: valid={is_valid}")
            
            return jsonify({
                'message': 'Proposal updated',
                'proposal': proposal.to_dict()
            }), 200
        
        except Exception as e:
            logger.error(f"Error toggling proposal: {e}")
            return jsonify({'error': str(e)}), 500
    
    return auto_markup_bp

