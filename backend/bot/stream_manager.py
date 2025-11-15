"""
FFmpeg stream manager for RTMP streaming to Telegram.
"""
import subprocess
import logging
import shutil
import os
import signal
import time
import threading
from typing import Optional, Dict
from pathlib import Path

logger = logging.getLogger(__name__)


class StreamManager:
    """Manages FFmpeg RTMP streaming with single-stream lock."""
    
    def __init__(self, store, state_manager):
        self.store = store
        self.state_manager = state_manager
        self.process: Optional[subprocess.Popen] = None
        self.lock = threading.Lock()
        self.watchdog_thread: Optional[threading.Thread] = None
        self.watchdog_running = False
    
    def is_stream_active(self) -> bool:
        """Check if a stream is currently active."""
        active_stream = self.state_manager.get_active_stream()
        return active_stream is not None
    
    def get_active_stream_info(self) -> Optional[Dict]:
        """Get information about active stream."""
        return self.state_manager.get_active_stream()
    
    def start_stream(self, camera_id: str, rtsp_url: str, target_alias: str, chat_id: int) -> tuple:
        """
        Start RTMP stream from camera to Telegram.
        
        Returns:
            (success: bool, message: str)
        """
        with self.lock:
            # Check if stream already active
            if self.is_stream_active():
                return False, "A stream is already active. Stop it first."
            
            # Get streaming config
            config = self.store.get_config()
            streaming_config = config.get('streaming', {})
            
            if not streaming_config.get('enabled', True):
                return False, "Streaming is disabled in configuration"
            
            # Find target
            targets = streaming_config.get('targets', [])
            target = next((t for t in targets if t['alias'] == target_alias), None)
            
            if not target:
                # If no alias provided or not found, use first target matching chat_id
                target = next((t for t in targets if t.get('chat_id') == chat_id), None)
                if not target and targets:
                    target = targets[0]
            
            if not target:
                return False, "No streaming target configured"
            
            # Get FFmpeg path
            ffmpeg_path = streaming_config.get('ffmpeg_path', 'ffmpeg')
            
            # Check if ffmpeg exists
            if not shutil.which(ffmpeg_path):
                return False, f"FFmpeg not found at: {ffmpeg_path}"
            
            # Build RTMP URL
            rtmp_url = target['rtmp_url']
            stream_key = target.get('stream_key', '')
            full_url = f"{rtmp_url}/{stream_key}" if stream_key else rtmp_url
            
            # Build FFmpeg command
            # Try copy first (no transcoding)
            cmd = [
                ffmpeg_path,
                '-rtsp_transport', 'tcp',
                '-i', rtsp_url,
                '-c:v', 'copy',
                '-an',  # No audio
                '-f', 'flv',
                '-flvflags', 'no_duration_filesize',
                full_url
            ]
            
            try:
                # Start FFmpeg process
                logger.info(f"Starting stream: {camera_id} -> {target_alias}")
                
                # Platform-specific process creation
                if os.name == 'nt':
                    # Windows: CREATE_NEW_PROCESS_GROUP
                    self.process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                    )
                else:
                    # Linux: use setsid for process group
                    self.process = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        preexec_fn=os.setsid
                    )
                
                # Give it a moment to start
                time.sleep(2)
                
                # Check if process started successfully
                if self.process.poll() is not None:
                    # Process already exited
                    stderr = self.process.stderr.read().decode('utf-8', errors='ignore')
                    logger.error(f"FFmpeg failed to start: {stderr}")
                    self.process = None
                    return False, f"FFmpeg failed to start. Check logs for details."
                
                # Save stream info to state
                stream_info = {
                    'camera_id': camera_id,
                    'target_alias': target_alias,
                    'chat_id': chat_id,
                    'started_at': time.time(),
                    'pid': self.process.pid
                }
                self.state_manager.set_active_stream(stream_info)
                
                # Start watchdog
                self._start_watchdog()
                
                logger.info(f"Stream started successfully: PID {self.process.pid}")
                return True, f"Stream started to {target['title']}"
            
            except Exception as e:
                logger.error(f"Error starting stream: {e}")
                if self.process:
                    self._kill_process(self.process)
                    self.process = None
                return False, f"Error starting stream: {str(e)}"
    
    def stop_stream(self) -> tuple:
        """
        Stop active stream.
        
        Returns:
            (success: bool, message: str)
        """
        with self.lock:
            if not self.is_stream_active():
                return False, "No active stream"
            
            # Stop watchdog
            self._stop_watchdog()
            
            # Kill FFmpeg process
            if self.process:
                logger.info(f"Stopping stream: PID {self.process.pid}")
                self._kill_process(self.process)
                self.process = None
            
            # Clear state
            self.state_manager.set_active_stream(None)
            
            logger.info("Stream stopped")
            return True, "Stream stopped"
    
    def _kill_process(self, process: subprocess.Popen):
        """Kill process (cross-platform)."""
        try:
            if os.name == 'nt':
                # Windows
                process.terminate()
                process.wait(timeout=5)
            else:
                # Linux: kill process group
                os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Force kill if graceful termination failed
            if os.name == 'nt':
                process.kill()
            else:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except Exception as e:
            logger.error(f"Error killing process: {e}")
    
    def _start_watchdog(self):
        """Start watchdog thread to monitor stream."""
        self.watchdog_running = True
        self.watchdog_thread = threading.Thread(target=self._watchdog_loop, daemon=True)
        self.watchdog_thread.start()
    
    def _stop_watchdog(self):
        """Stop watchdog thread."""
        self.watchdog_running = False
        if self.watchdog_thread:
            self.watchdog_thread.join(timeout=5)
    
    def _watchdog_loop(self):
        """Monitor FFmpeg process and clean up if it dies."""
        while self.watchdog_running:
            time.sleep(5)
            
            with self.lock:
                if self.process and self.process.poll() is not None:
                    # Process died
                    logger.warning(f"FFmpeg process died unexpectedly: PID {self.process.pid}")
                    
                    # Read error output
                    if self.process.stderr:
                        stderr = self.process.stderr.read().decode('utf-8', errors='ignore')
                        logger.error(f"FFmpeg stderr: {stderr}")
                    
                    # Clean up
                    self.process = None
                    self.state_manager.set_active_stream(None)
                    self.watchdog_running = False
                    break
    
    def cleanup(self):
        """Clean up resources."""
        if self.is_stream_active():
            self.stop_stream()

