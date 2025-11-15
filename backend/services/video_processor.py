"""
Video processor for capturing RTSP streams and maintaining frame buffer.
"""
import cv2
import threading
import time
import logging
from typing import Optional, Dict
import numpy as np

logger = logging.getLogger(__name__)


class VideoProcessor:
    """Manages video capture from RTSP streams."""
    
    def __init__(self, camera_id: str, rtsp_url: str):
        self.camera_id = camera_id
        self.rtsp_url = rtsp_url
        self.cap: Optional[cv2.VideoCapture] = None
        self.latest_frame: Optional[np.ndarray] = None
        self.frame_lock = threading.Lock()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_frame_time = 0
        self.fps = 0
        self.reconnect_delay = 5  # seconds
        
    def start(self):
        """Start video capture thread."""
        if self.running:
            logger.warning(f"Video processor for {self.camera_id} already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        logger.info(f"Started video processor for camera {self.camera_id}")
    
    def stop(self):
        """Stop video capture thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=5)
        if self.cap:
            self.cap.release()
        logger.info(f"Stopped video processor for camera {self.camera_id}")
    
    def _capture_loop(self):
        """Main capture loop with auto-reconnect."""
        while self.running:
            try:
                self._connect()
                while self.running and self.cap and self.cap.isOpened():
                    ret, frame = self.cap.read()
                    
                    if not ret:
                        logger.warning(f"Failed to read frame from {self.camera_id}")
                        break
                    
                    with self.frame_lock:
                        self.latest_frame = frame.copy()
                        current_time = time.time()
                        if self.last_frame_time > 0:
                            self.fps = 1.0 / (current_time - self.last_frame_time)
                        self.last_frame_time = current_time
                    
                    # Small delay to prevent CPU overload
                    time.sleep(0.01)
                
            except Exception as e:
                logger.error(f"Error in capture loop for {self.camera_id}: {e}")
            
            finally:
                if self.cap:
                    self.cap.release()
                    self.cap = None
            
            if self.running:
                logger.info(f"Reconnecting to {self.camera_id} in {self.reconnect_delay}s...")
                time.sleep(self.reconnect_delay)
    
    def _connect(self):
        """Connect to RTSP stream."""
        logger.info(f"Connecting to RTSP stream: {self.camera_id}")
        self.cap = cv2.VideoCapture(self.rtsp_url)
        
        # Set buffer size to minimize latency
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        
        if not self.cap.isOpened():
            raise ConnectionError(f"Failed to open RTSP stream for {self.camera_id}")
        
        logger.info(f"Connected to {self.camera_id}")
    
    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Get the latest captured frame (thread-safe)."""
        with self.frame_lock:
            return self.latest_frame.copy() if self.latest_frame is not None else None
    
    def is_alive(self) -> bool:
        """Check if capture is active and receiving frames."""
        with self.frame_lock:
            if self.latest_frame is None:
                return False
            # Consider alive if we got a frame in the last 10 seconds
            return (time.time() - self.last_frame_time) < 10


class VideoProcessorManager:
    """Manages multiple video processors."""
    
    def __init__(self):
        self.processors: Dict[str, VideoProcessor] = {}
        self.lock = threading.Lock()
    
    def add_camera(self, camera_id: str, rtsp_url: str):
        """Add and start a camera processor."""
        with self.lock:
            if camera_id in self.processors:
                logger.warning(f"Camera {camera_id} already exists")
                return
            
            processor = VideoProcessor(camera_id, rtsp_url)
            processor.start()
            self.processors[camera_id] = processor
            logger.info(f"Added camera processor: {camera_id}")
    
    def remove_camera(self, camera_id: str):
        """Stop and remove a camera processor."""
        with self.lock:
            if camera_id not in self.processors:
                logger.warning(f"Camera {camera_id} not found")
                return
            
            processor = self.processors.pop(camera_id)
            processor.stop()
            logger.info(f"Removed camera processor: {camera_id}")
    
    def get_frame(self, camera_id: str) -> Optional[np.ndarray]:
        """Get latest frame from a camera."""
        with self.lock:
            processor = self.processors.get(camera_id)
            if processor:
                return processor.get_latest_frame()
            return None
    
    def get_all_camera_ids(self) -> list:
        """Get list of all active camera IDs."""
        with self.lock:
            return list(self.processors.keys())
    
    def is_camera_alive(self, camera_id: str) -> bool:
        """Check if camera is actively receiving frames."""
        with self.lock:
            processor = self.processors.get(camera_id)
            return processor.is_alive() if processor else False
    
    def stop_all(self):
        """Stop all camera processors."""
        with self.lock:
            for processor in self.processors.values():
                processor.stop()
            self.processors.clear()
            logger.info("Stopped all camera processors")

