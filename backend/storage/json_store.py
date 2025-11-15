"""
JSON storage module with atomic read/write and file locking.
"""
import json
import os
import logging
from pathlib import Path
from typing import Any, Dict
import portalocker
from datetime import datetime


class JSONStore:
    """Thread-safe JSON file storage with locking."""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        
        # Default schemas
        self.defaults = {
            "config.json": {
                "schema_version": 1,
                "bot_token": "",
                "allowed_chats": [],
                "occupancy_minutes": 5,
                "confidence_threshold": 0.5,
                "update_hz": 1.0,
                "streaming": {
                    "enabled": True,
                    "ffmpeg_path": "ffmpeg",
                    "targets": [],
                    "one_active_stream": True
                }
            },
            "cameras.json": {"cameras": []},
            "spaces.json": {"spaces": []},
            "spots.json": {"spots": []},
            "state.json": {
                "spaces": {},
                "active_stream": None
            },
            "markup_sessions.json": {"sessions": {}}
        }
        
        # Initialize files if they don't exist
        self._init_files()
    
    def _init_files(self):
        """Create default JSON files if they don't exist."""
        for filename, default_data in self.defaults.items():
            filepath = self.data_dir / filename
            if not filepath.exists():
                self._write_atomic(filepath, default_data)
    
    def _write_atomic(self, filepath: Path, data: Dict[str, Any]):
        """Write JSON atomically with exclusive lock."""
        start_time = datetime.now()
        try:
            with portalocker.Lock(str(filepath), 'w', timeout=2) as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > 0.5:
                logger = logging.getLogger(__name__)
                logger.warning(f"Slow write lock acquisition for {filepath}: {elapsed:.3f}s")
        except portalocker.exceptions.LockException as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to acquire write lock for {filepath} after 2s: {e}")
            raise TimeoutError(f"Could not lock file {filepath} for writing")
    
    def _read_locked(self, filepath: Path) -> Dict[str, Any]:
        """Read JSON with shared lock."""
        if not filepath.exists():
            return {}
        
        start_time = datetime.now()
        try:
            with portalocker.Lock(str(filepath), 'r', timeout=2) as f:
                result = json.load(f)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > 0.5:
                logger = logging.getLogger(__name__)
                logger.warning(f"Slow read lock acquisition for {filepath}: {elapsed:.3f}s")
            
            return result
        except portalocker.exceptions.LockException as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to acquire read lock for {filepath} after 2s: {e}")
            raise TimeoutError(f"Could not lock file {filepath} for reading")
    
    def read(self, filename: str) -> Dict[str, Any]:
        """Read JSON file."""
        filepath = self.data_dir / filename
        return self._read_locked(filepath)
    
    def write(self, filename: str, data: Dict[str, Any]):
        """Write JSON file atomically."""
        filepath = self.data_dir / filename
        self._write_atomic(filepath, data)
    
    def update(self, filename: str, updater_func):
        """Update JSON file atomically with a function."""
        filepath = self.data_dir / filename
        
        start_time = datetime.now()
        try:
            with portalocker.Lock(str(filepath), 'r+', timeout=2) as f:
                data = json.load(f)
                updated_data = updater_func(data)
                f.seek(0)
                f.truncate()
                json.dump(updated_data, f, indent=2, ensure_ascii=False)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > 0.5:
                logger = logging.getLogger(__name__)
                logger.warning(f"Slow update lock acquisition for {filepath}: {elapsed:.3f}s")
            
            return updated_data
        except portalocker.exceptions.LockException as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to acquire update lock for {filepath} after 2s: {e}")
            raise TimeoutError(f"Could not lock file {filepath} for updating")
    
    # Convenience methods for specific files
    def get_config(self) -> Dict[str, Any]:
        return self.read("config.json")
    
    def update_config(self, updates: Dict[str, Any]):
        def updater(data):
            data.update(updates)
            return data
        return self.update("config.json", updater)
    
    def get_cameras(self) -> list:
        return self.read("cameras.json").get("cameras", [])
    
    def save_cameras(self, cameras: list):
        self.write("cameras.json", {"cameras": cameras})
    
    def get_spaces(self) -> list:
        return self.read("spaces.json").get("spaces", [])
    
    def save_spaces(self, spaces: list):
        self.write("spaces.json", {"spaces": spaces})
    
    def get_spots(self) -> list:
        return self.read("spots.json").get("spots", [])
    
    def save_spots(self, spots: list):
        self.write("spots.json", {"spots": spots})
    
    def get_state(self) -> Dict[str, Any]:
        return self.read("state.json")
    
    def update_state(self, updater_func):
        return self.update("state.json", updater_func)
    
    def get_markup_sessions(self) -> Dict[str, any]:
        return self.read("markup_sessions.json").get("sessions", {})
    
    def save_markup_sessions(self, sessions: Dict):
        self.write("markup_sessions.json", {"sessions": sessions})

