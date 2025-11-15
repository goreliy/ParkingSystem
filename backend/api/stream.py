"""
Stream, snapshot, and SSE API endpoints.
"""
from flask import Blueprint, request, jsonify, Response
import logging
import cv2
import numpy as np
from io import BytesIO
import json
import time
import queue

logger = logging.getLogger(__name__)

stream_bp = Blueprint('stream', __name__)

# Simple metrics tracking
_metrics = {
    'snapshot_requests': 0,
    'snapshot_success': 0,
    'snapshot_errors': 0,
    'camera_unavailable': 0,
    'encoding_errors': 0,
    'total_response_time': 0.0
}


def _create_placeholder_image(text: str = "Изображение недоступно") -> Response:
    """Create a placeholder image with text."""
    try:
        # Create a simple placeholder image
        img = np.zeros((480, 640, 3), dtype=np.uint8)
        img[:] = (50, 50, 50)  # Dark gray background
        
        # Add text
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 1.0
        thickness = 2
        
        # Get text size for centering
        (text_width, text_height), baseline = cv2.getTextSize(text, font, font_scale, thickness)
        x = (640 - text_width) // 2
        y = (480 + text_height) // 2
        
        # Draw text with shadow
        cv2.putText(img, text, (x + 2, y + 2), font, font_scale, (0, 0, 0), thickness + 2)
        cv2.putText(img, text, (x, y), font, font_scale, (200, 200, 200), thickness)
        
        _, buffer = cv2.imencode('.jpg', img, [cv2.IMWRITE_JPEG_QUALITY, 85])
        
        return Response(
            buffer.tobytes(),
            mimetype='image/jpeg',
            headers={'Cache-Control': 'no-cache, no-store, must-revalidate'}
        )
    except Exception as e:
        logger.error(f"Error creating placeholder image: {e}")
        # Return minimal error response
        return Response(
            b'',
            mimetype='image/jpeg',
            status=500
        )


def init_stream_api(store, video_manager, state_manager, detector):
    """Initialize stream API with dependencies."""
    
    # SSE event queue
    event_subscribers = []
    
    def broadcast_event(event_type: str, data: dict):
        """Broadcast event to all SSE subscribers."""
        event_data = {
            'type': event_type,
            'data': data,
            'timestamp': time.time()
        }
        
        # Remove closed connections
        active_subscribers = []
        for q in event_subscribers:
            try:
                q.put_nowait(event_data)
                active_subscribers.append(q)
            except:
                pass
        event_subscribers.clear()
        event_subscribers.extend(active_subscribers)
    
    # Register state change callback
    state_manager.register_event_callback(
        lambda event_type, data: broadcast_event(event_type, data)
    )
    
    @stream_bp.route('/api/snapshot/camera/<camera_id>', methods=['GET'])
    def get_camera_snapshot(camera_id):
        """Get snapshot from a camera."""
        start_time = time.time()
        _metrics['snapshot_requests'] += 1
        
        try:
            # Check if camera is alive
            if not video_manager.is_camera_alive(camera_id):
                logger.warning(f"Camera {camera_id} is not alive")
                _metrics['camera_unavailable'] += 1
                return _create_placeholder_image("Камера недоступна"), 503
            
            frame = video_manager.get_frame(camera_id)
            
            if frame is None:
                logger.warning(f"No frame available for camera {camera_id}")
                _metrics['camera_unavailable'] += 1
                return _create_placeholder_image("Нет кадра"), 503
            
            # Encode as JPEG with error handling
            try:
                success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not success:
                    raise ValueError("Failed to encode frame")
            except Exception as encode_error:
                logger.error(f"Error encoding frame from {camera_id}: {encode_error}")
                _metrics['encoding_errors'] += 1
                return _create_placeholder_image("Ошибка кодирования"), 500
            
            elapsed = time.time() - start_time
            _metrics['total_response_time'] += elapsed
            _metrics['snapshot_success'] += 1
            
            if elapsed > 1.0:
                logger.warning(f"Slow snapshot request for camera {camera_id}: {elapsed:.3f}s")
            else:
                logger.debug(f"Camera snapshot {camera_id} took {elapsed:.3f}s")
            
            return Response(
                buffer.tobytes(),
                mimetype='image/jpeg',
                headers={'Cache-Control': 'no-cache, no-store, must-revalidate'}
            )
        except Exception as e:
            logger.error(f"Error getting camera snapshot {camera_id}: {e}", exc_info=True)
            _metrics['snapshot_errors'] += 1
            return _create_placeholder_image("Ошибка сервера"), 500
    
    @stream_bp.route('/api/snapshot/space/<space_id>', methods=['GET'])
    def get_space_snapshot(space_id):
        """Get annotated snapshot of a parking space."""
        start_time = time.time()
        _metrics['snapshot_requests'] += 1
        
        try:
            annotated = request.args.get('annotated', 'true').lower() == 'true'
            
            # Get space and its cameras
            spaces = store.get_spaces()
            space = next((s for s in spaces if s['id'] == space_id), None)
            
            if not space:
                logger.warning(f"Space {space_id} not found")
                _metrics['snapshot_errors'] += 1
                return _create_placeholder_image("Зона не найдена"), 404
            
            if not space.get('camera_ids'):
                logger.warning(f"Space {space_id} has no cameras assigned")
                _metrics['snapshot_errors'] += 1
                return _create_placeholder_image("Нет камеры"), 400
            
            # Get frame from first camera
            camera_id = space['camera_ids'][0]
            
            # Check if camera is alive
            if not video_manager.is_camera_alive(camera_id):
                logger.warning(f"Camera {camera_id} for space {space_id} is not alive")
                _metrics['camera_unavailable'] += 1
                return _create_placeholder_image("Камера недоступна"), 503
            
            frame = video_manager.get_frame(camera_id)
            
            if frame is None:
                logger.warning(f"No frame available for camera {camera_id} (space {space_id})")
                _metrics['camera_unavailable'] += 1
                return _create_placeholder_image("Нет кадра"), 503
            
            if annotated:
                try:
                    # Draw parking spots on frame with enhanced visualization
                    spots = store.get_spots()
                    space_spots = [s for s in spots if s['space_id'] == space_id]
                    spot_states = state_manager.get_spot_details(space_id)
                    
                    # Create state lookup
                    state_lookup = {s['id']: s for s in spot_states}
                    
                    # Create overlay for semi-transparent fill
                    overlay = frame.copy()
                    
                    for spot in space_spots:
                        rect = spot['rect']
                        x1, y1 = rect['x1'], rect['y1']
                        x2, y2 = rect['x2'], rect['y2']
                        
                        state = state_lookup.get(spot['id'], {})
                        occupied = state.get('occupied', False)
                        
                        # Color: red if occupied, green if free, blue if nopark
                        if spot['type'] == 'nopark':
                            color = (255, 0, 0)  # Blue in BGR
                        elif occupied:
                            color = (0, 0, 255)  # Red in BGR
                        else:
                            color = (0, 255, 0)  # Green in BGR
                        
                        # Draw semi-transparent filled rectangle
                        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
                        
                        # Draw rectangle border with thickness 3
                        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 3)
                        
                        # Prepare label
                        label = spot['label']
                        if occupied and state.get('sequential_number'):
                            label += f" #{state['sequential_number']}"
                        
                        # Calculate text position
                        font = cv2.FONT_HERSHEY_SIMPLEX
                        font_scale = 0.8
                        (text_width, text_height), baseline = cv2.getTextSize(label, font, font_scale, 2)
                        text_x = x1
                        text_y = y1 - 10 if y1 > 30 else y1 + text_height + 10
                        
                        # Draw text with black outline for better readability
                        cv2.putText(frame, label, (text_x, text_y), font, font_scale, (0, 0, 0), 4)
                        cv2.putText(frame, label, (text_x, text_y), font, font_scale, color, 2)
                    
                    # Blend overlay with original frame (30% transparency)
                    cv2.addWeighted(overlay, 0.3, frame, 0.7, 0, frame)
                    
                    # Add legend in top-right corner
                    legend_x = frame.shape[1] - 200
                    legend_y = 30
                    legend_spacing = 30
                    
                    # Legend background
                    cv2.rectangle(frame, (legend_x - 10, legend_y - 25), 
                                 (frame.shape[1] - 10, legend_y + legend_spacing * 3 + 5), 
                                 (0, 0, 0), -1)
                    cv2.rectangle(frame, (legend_x - 10, legend_y - 25), 
                                 (frame.shape[1] - 10, legend_y + legend_spacing * 3 + 5), 
                                 (255, 255, 255), 2)
                    
                    # Legend items
                    font_scale_legend = 0.6
                    cv2.putText(frame, "Svobodno", (legend_x + 30, legend_y), 
                               cv2.FONT_HERSHEY_SIMPLEX, font_scale_legend, (255, 255, 255), 2)
                    cv2.rectangle(frame, (legend_x, legend_y - 15), (legend_x + 20, legend_y - 5), (0, 255, 0), -1)
                    
                    cv2.putText(frame, "Zanyato", (legend_x + 30, legend_y + legend_spacing), 
                               cv2.FONT_HERSHEY_SIMPLEX, font_scale_legend, (255, 255, 255), 2)
                    cv2.rectangle(frame, (legend_x, legend_y + legend_spacing - 15), 
                                 (legend_x + 20, legend_y + legend_spacing - 5), (0, 0, 255), -1)
                    
                    cv2.putText(frame, "Zapret", (legend_x + 30, legend_y + legend_spacing * 2), 
                               cv2.FONT_HERSHEY_SIMPLEX, font_scale_legend, (255, 255, 255), 2)
                    cv2.rectangle(frame, (legend_x, legend_y + legend_spacing * 2 - 15), 
                                 (legend_x + 20, legend_y + legend_spacing * 2 - 5), (255, 0, 0), -1)
                    
                except Exception as annotation_error:
                    logger.error(f"Error annotating frame for space {space_id}: {annotation_error}")
                    # Continue with unannotated frame
            
            # Encode as JPEG with error handling
            try:
                success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
                if not success:
                    raise ValueError("Failed to encode frame")
            except Exception as encode_error:
                logger.error(f"Error encoding space snapshot {space_id}: {encode_error}")
                _metrics['encoding_errors'] += 1
                return _create_placeholder_image("Ошибка кодирования"), 500
            
            elapsed = time.time() - start_time
            _metrics['total_response_time'] += elapsed
            _metrics['snapshot_success'] += 1
            
            if elapsed > 1.0:
                logger.warning(f"Slow snapshot request for space {space_id}: {elapsed:.3f}s")
            else:
                logger.debug(f"Space snapshot {space_id} took {elapsed:.3f}s")
            
            return Response(
                buffer.tobytes(),
                mimetype='image/jpeg',
                headers={'Cache-Control': 'no-cache, no-store, must-revalidate'}
            )
        except Exception as e:
            logger.error(f"Error getting space snapshot {space_id}: {e}", exc_info=True)
            _metrics['snapshot_errors'] += 1
            return _create_placeholder_image("Ошибка сервера"), 500
    
    @stream_bp.route('/api/state', methods=['GET'])
    def get_state():
        """Get current parking state."""
        try:
            summary = state_manager.get_all_spaces_summary()
            return jsonify({
                'spaces': summary,
                'timestamp': time.time()
            }), 200
        except Exception as e:
            logger.error(f"Error getting state: {e}")
            return jsonify({'error': str(e)}), 500
    
    @stream_bp.route('/api/state/spaces/<space_id>', methods=['GET'])
    def get_space_state(space_id):
        """Get detailed state of a parking space."""
        try:
            spots = state_manager.get_spot_details(space_id)
            space_state = state_manager.get_space_state(space_id)
            
            if space_state is None:
                return jsonify({'error': 'Space not found'}), 404
            
            return jsonify({
                'space_id': space_id,
                'summary': {
                    'total_spots': space_state.get('total_spots', 0),
                    'occupied_spots': space_state.get('occupied_spots', 0),
                    'free_spots': space_state.get('free_spots', 0)
                },
                'spots': spots,
                'timestamp': time.time()
            }), 200
        except Exception as e:
            logger.error(f"Error getting space state: {e}")
            return jsonify({'error': str(e)}), 500
    
    @stream_bp.route('/api/events', methods=['GET'])
    def sse_events():
        """Server-Sent Events stream for real-time updates."""
        def event_stream():
            # Create queue for this client
            q = queue.Queue(maxsize=50)
            event_subscribers.append(q)
            
            try:
                # Send initial connection message
                yield f"data: {json.dumps({'type': 'connected', 'timestamp': time.time()})}\n\n"
                
                while True:
                    # Wait for event with timeout
                    try:
                        event = q.get(timeout=30)
                        yield f"data: {json.dumps(event)}\n\n"
                    except queue.Empty:
                        # Send keepalive
                        yield f": keepalive\n\n"
            
            except GeneratorExit:
                # Client disconnected
                if q in event_subscribers:
                    event_subscribers.remove(q)
        
        return Response(
            event_stream(),
            mimetype='text/event-stream',
            headers={
                'Cache-Control': 'no-cache',
                'X-Accel-Buffering': 'no'
            }
        )
    
    @stream_bp.route('/api/stream/status', methods=['GET'])
    def get_stream_status():
        """Get active stream status."""
        try:
            active_stream = state_manager.get_active_stream()
            
            if active_stream:
                return jsonify({
                    'active': True,
                    'stream': active_stream
                }), 200
            else:
                return jsonify({
                    'active': False,
                    'stream': None
                }), 200
        except Exception as e:
            logger.error(f"Error getting stream status: {e}")
            return jsonify({'error': str(e)}), 500
    
    @stream_bp.route('/api/stream/start', methods=['POST'])
    def start_stream():
        """Start RTMP stream (placeholder - will be implemented with stream manager)."""
        try:
            data = request.json
            camera_id = data.get('camera_id')
            target_alias = data.get('target_alias')
            
            if not camera_id:
                return jsonify({'error': 'camera_id required'}), 400
            
            # Check if stream already active
            active = state_manager.get_active_stream()
            if active:
                return jsonify({'error': 'Stream already active'}), 409
            
            # TODO: Implement stream manager integration
            return jsonify({'message': 'Stream start not yet implemented'}), 501
        
        except Exception as e:
            logger.error(f"Error starting stream: {e}")
            return jsonify({'error': str(e)}), 500
    
    @stream_bp.route('/api/stream/stop', methods=['POST'])
    def stop_stream():
        """Stop RTMP stream (placeholder)."""
        try:
            active = state_manager.get_active_stream()
            if not active:
                return jsonify({'error': 'No active stream'}), 400
            
            # TODO: Implement stream manager integration
            return jsonify({'message': 'Stream stop not yet implemented'}), 501
        
        except Exception as e:
            logger.error(f"Error stopping stream: {e}")
            return jsonify({'error': str(e)}), 500
    
    @stream_bp.route('/api/metrics', methods=['GET'])
    def get_metrics():
        """Get snapshot API metrics."""
        try:
            avg_response_time = (_metrics['total_response_time'] / _metrics['snapshot_success'] 
                                if _metrics['snapshot_success'] > 0 else 0)
            
            success_rate = ((_metrics['snapshot_success'] / _metrics['snapshot_requests'] * 100) 
                           if _metrics['snapshot_requests'] > 0 else 0)
            
            return jsonify({
                'total_requests': _metrics['snapshot_requests'],
                'successful': _metrics['snapshot_success'],
                'errors': _metrics['snapshot_errors'],
                'camera_unavailable': _metrics['camera_unavailable'],
                'encoding_errors': _metrics['encoding_errors'],
                'success_rate': f"{success_rate:.1f}%",
                'avg_response_time': f"{avg_response_time:.3f}s"
            }), 200
        except Exception as e:
            logger.error(f"Error getting metrics: {e}")
            return jsonify({'error': str(e)}), 500
    
    @stream_bp.route('/api/video/camera/<camera_id>', methods=['GET'])
    def video_stream_camera(camera_id):
        """MJPEG видеопоток с камеры."""
        def generate_frames():
            """Генератор кадров для MJPEG потока."""
            try:
                while True:
                    # Проверить доступность камеры
                    if not video_manager.is_camera_alive(camera_id):
                        # Отправить placeholder
                        placeholder = _create_placeholder_image("Камера недоступна")
                        if hasattr(placeholder, 'get_data'):
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + 
                                   placeholder.get_data() + b'\r\n')
                        time.sleep(1)
                        continue
                    
                    frame = video_manager.get_frame(camera_id)
                    
                    if frame is None:
                        time.sleep(0.1)
                        continue
                    
                    # Кодировать кадр
                    try:
                        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        if success:
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + 
                                   buffer.tobytes() + b'\r\n')
                    except Exception as e:
                        logger.error(f"Error encoding frame for stream: {e}")
                    
                    # Задержка для контроля FPS (~10 FPS)
                    time.sleep(0.1)
            
            except GeneratorExit:
                logger.debug(f"Video stream closed for camera {camera_id}")
        
        return Response(
            generate_frames(),
            mimetype='multipart/x-mixed-replace; boundary=frame',
            headers={'Cache-Control': 'no-cache, no-store, must-revalidate'}
        )
    
    @stream_bp.route('/api/video/space/<space_id>', methods=['GET'])
    def video_stream_space(space_id):
        """MJPEG видеопоток парковочной зоны с аннотациями."""
        def generate_frames():
            """Генератор кадров с разметкой парковочных мест."""
            try:
                # Получить зону
                spaces = store.get_spaces()
                space = next((s for s in spaces if s['id'] == space_id), None)
                
                if not space or not space.get('camera_ids'):
                    placeholder = _create_placeholder_image("Зона не найдена")
                    if hasattr(placeholder, 'get_data'):
                        yield (b'--frame\r\n'
                               b'Content-Type: image/jpeg\r\n\r\n' + 
                               placeholder.get_data() + b'\r\n')
                    return
                
                camera_id = space['camera_ids'][0]
                
                while True:
                    if not video_manager.is_camera_alive(camera_id):
                        time.sleep(1)
                        continue
                    
                    frame = video_manager.get_frame(camera_id)
                    
                    if frame is None:
                        time.sleep(0.1)
                        continue
                    
                    # Нарисовать разметку (аннотацию)
                    try:
                        annotated_frame = frame.copy()
                        spots = store.get_spots()
                        space_spots = [s for s in spots if s['space_id'] == space_id]
                        spot_states = state_manager.get_spot_details(space_id)
                        state_lookup = {s['id']: s for s in spot_states}
                        
                        # Создать overlay для полупрозрачности
                        overlay = annotated_frame.copy()
                        
                        for spot in space_spots:
                            rect = spot['rect']
                            x1, y1 = rect['x1'], rect['y1']
                            x2, y2 = rect['x2'], rect['y2']
                            
                            state = state_lookup.get(spot['id'], {})
                            occupied = state.get('occupied', False)
                            
                            # Цвет
                            if spot['type'] == 'nopark':
                                color = (255, 0, 0)
                            elif occupied:
                                color = (0, 0, 255)
                            else:
                                color = (0, 255, 0)
                            
                            # Заливка
                            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
                            
                            # Рамка
                            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 3)
                            
                            # Метка
                            label = spot['label']
                            if occupied and state.get('sequential_number'):
                                label += f" #{state['sequential_number']}"
                            
                            font = cv2.FONT_HERSHEY_SIMPLEX
                            cv2.putText(annotated_frame, label, (x1, y1 - 10), 
                                       font, 0.8, (0, 0, 0), 4)
                            cv2.putText(annotated_frame, label, (x1, y1 - 10), 
                                       font, 0.8, color, 2)
                        
                        # Смешать overlay
                        cv2.addWeighted(overlay, 0.3, annotated_frame, 0.7, 0, annotated_frame)
                        
                        frame = annotated_frame
                    except Exception as e:
                        logger.error(f"Error annotating stream frame: {e}")
                    
                    # Кодировать
                    try:
                        success, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 75])
                        if success:
                            yield (b'--frame\r\n'
                                   b'Content-Type: image/jpeg\r\n\r\n' + 
                                   buffer.tobytes() + b'\r\n')
                    except Exception as e:
                        logger.error(f"Error encoding stream frame: {e}")
                    
                    time.sleep(0.1)  # ~10 FPS
            
            except GeneratorExit:
                logger.debug(f"Video stream closed for space {space_id}")
        
        return Response(
            generate_frames(),
            mimetype='multipart/x-mixed-replace; boundary=frame',
            headers={'Cache-Control': 'no-cache, no-store, must-revalidate'}
        )
    
    return stream_bp

