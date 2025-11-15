"""
Configuration management API endpoints.
"""
from flask import Blueprint, request, jsonify
import logging

logger = logging.getLogger(__name__)

config_bp = Blueprint('config', __name__)


def init_config_api(store):
    """Initialize config API with dependencies."""
    
    @config_bp.route('/api/config', methods=['GET'])
    def get_config():
        """Get full configuration."""
        try:
            config = store.get_config()
            # Hide sensitive data in response
            safe_config = config.copy()
            if 'bot_token' in safe_config and safe_config['bot_token']:
                safe_config['bot_token'] = '***' + safe_config['bot_token'][-4:]
            
            return jsonify(safe_config), 200
        except Exception as e:
            logger.error(f"Error getting config: {e}")
            return jsonify({'error': str(e)}), 500
    
    @config_bp.route('/api/config/bot', methods=['GET'])
    def get_bot_config():
        """Get bot configuration."""
        try:
            config = store.get_config()
            bot_config = {
                'bot_token_set': bool(config.get('bot_token')),
                'allowed_chats': config.get('allowed_chats', [])
            }
            return jsonify(bot_config), 200
        except Exception as e:
            logger.error(f"Error getting bot config: {e}")
            return jsonify({'error': str(e)}), 500
    
    @config_bp.route('/api/config/bot', methods=['PUT'])
    def update_bot_config():
        """Update bot configuration."""
        try:
            data = request.json
            updates = {}
            
            if 'bot_token' in data:
                updates['bot_token'] = data['bot_token']
            
            if 'allowed_chats' in data:
                updates['allowed_chats'] = data['allowed_chats']
            
            store.update_config(updates)
            logger.info("Updated bot configuration")
            
            return jsonify({'message': 'Bot config updated'}), 200
        except Exception as e:
            logger.error(f"Error updating bot config: {e}")
            return jsonify({'error': str(e)}), 500
    
    @config_bp.route('/api/config/bot/chats/<int:chat_id>', methods=['PUT'])
    def update_chat_permissions(chat_id):
        """Update chat permissions."""
        try:
            data = request.json
            config = store.get_config()
            allowed_chats = config.get('allowed_chats', [])
            
            # Find the chat
            chat = next((c for c in allowed_chats if c['chat_id'] == chat_id), None)
            
            if not chat:
                return jsonify({'error': 'Chat not found'}), 404
            
            # Update is_admin flag
            if 'is_admin' in data:
                new_admin_status = bool(data['is_admin'])
                
                # If setting to admin, ensure only one admin exists
                if new_admin_status:
                    # Unset all other admins
                    for c in allowed_chats:
                        if c['chat_id'] != chat_id:
                            c['is_admin'] = False
                
                chat['is_admin'] = new_admin_status
            
            store.update_config({'allowed_chats': allowed_chats})
            logger.info(f"Updated chat {chat_id} permissions (is_admin={chat.get('is_admin', False)})")
            
            return jsonify(chat), 200
        except Exception as e:
            logger.error(f"Error updating chat permissions: {e}")
            return jsonify({'error': str(e)}), 500
    
    @config_bp.route('/api/config/bot/chats/<int:chat_id>', methods=['DELETE'])
    def remove_chat(chat_id):
        """Remove a chat from allowed list."""
        try:
            config = store.get_config()
            allowed_chats = config.get('allowed_chats', [])
            
            # Find the chat to check if it's admin
            chat = next((c for c in allowed_chats if c['chat_id'] == chat_id), None)
            
            if not chat:
                return jsonify({'error': 'Chat not found'}), 404
            
            # Prevent removing admin
            if chat.get('is_admin', False):
                return jsonify({'error': 'Cannot remove admin chat. Set another admin first.'}), 400
            
            # Remove the chat
            allowed_chats = [c for c in allowed_chats if c['chat_id'] != chat_id]
            
            store.update_config({'allowed_chats': allowed_chats})
            logger.info(f"Removed chat {chat_id}")
            
            return jsonify({'message': 'Chat removed'}), 200
        except Exception as e:
            logger.error(f"Error removing chat: {e}")
            return jsonify({'error': str(e)}), 500
    
    @config_bp.route('/api/config/streaming', methods=['GET'])
    def get_streaming_config():
        """Get streaming configuration."""
        try:
            config = store.get_config()
            streaming = config.get('streaming', {})
            
            # Hide stream keys
            safe_streaming = streaming.copy()
            if 'targets' in safe_streaming:
                safe_streaming['targets'] = [
                    {**t, 'stream_key': '***' if t.get('stream_key') else ''}
                    for t in safe_streaming['targets']
                ]
            
            return jsonify(safe_streaming), 200
        except Exception as e:
            logger.error(f"Error getting streaming config: {e}")
            return jsonify({'error': str(e)}), 500
    
    @config_bp.route('/api/config/streaming', methods=['PUT'])
    def update_streaming_config():
        """Update streaming configuration."""
        try:
            data = request.json
            config = store.get_config()
            
            if 'streaming' not in config:
                config['streaming'] = {}
            
            streaming = config['streaming']
            
            if 'enabled' in data:
                streaming['enabled'] = bool(data['enabled'])
            
            if 'ffmpeg_path' in data:
                streaming['ffmpeg_path'] = data['ffmpeg_path']
            
            if 'targets' in data:
                streaming['targets'] = data['targets']
            
            if 'one_active_stream' in data:
                streaming['one_active_stream'] = bool(data['one_active_stream'])
            
            store.update_config({'streaming': streaming})
            logger.info("Updated streaming configuration")
            
            return jsonify({'message': 'Streaming config updated'}), 200
        except Exception as e:
            logger.error(f"Error updating streaming config: {e}")
            return jsonify({'error': str(e)}), 500
    
    @config_bp.route('/api/config/occupancy', methods=['PUT'])
    def update_occupancy_config():
        """Update occupancy detection settings."""
        try:
            data = request.json
            updates = {}
            
            if 'occupancy_minutes' in data:
                updates['occupancy_minutes'] = int(data['occupancy_minutes'])
            
            if 'confidence_threshold' in data:
                updates['confidence_threshold'] = float(data['confidence_threshold'])
            
            if 'update_hz' in data:
                updates['update_hz'] = float(data['update_hz'])
            
            store.update_config(updates)
            logger.info("Updated occupancy configuration")
            
            return jsonify({'message': 'Occupancy config updated'}), 200
        except Exception as e:
            logger.error(f"Error updating occupancy config: {e}")
            return jsonify({'error': str(e)}), 500
    
    return config_bp

