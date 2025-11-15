"""
Occupancy detection logic with timers and sequential numbering.
"""
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class OccupancyTracker:
    """Tracks parking spot occupancy with timer-based detection."""
    
    def __init__(self, occupancy_minutes: int = 5):
        self.occupancy_minutes = occupancy_minutes
        self.spot_timers: Dict[str, float] = {}  # spot_id -> first_detection_time
        self.spot_states: Dict[str, bool] = {}  # spot_id -> is_occupied
        self.sequential_numbers: Dict[str, int] = {}  # spot_id -> sequential number
        self.next_sequential = 1
        
    def update_detections(self, detections: Dict[str, bool]) -> Dict[str, Dict]:
        """
        Update spot states based on current detections.
        
        Args:
            detections: Dictionary of {spot_id: vehicle_detected}
        
        Returns:
            Dictionary of changed spots with their new states
        """
        current_time = time.time()
        threshold_seconds = self.occupancy_minutes * 60
        changes = {}
        
        for spot_id, vehicle_detected in detections.items():
            was_occupied = self.spot_states.get(spot_id, False)
            
            if vehicle_detected:
                # Vehicle detected in spot
                if spot_id not in self.spot_timers:
                    # First detection
                    self.spot_timers[spot_id] = current_time
                    logger.debug(f"Spot {spot_id}: vehicle detected, timer started")
                else:
                    # Check if timer threshold exceeded
                    elapsed = current_time - self.spot_timers[spot_id]
                    if elapsed >= threshold_seconds and not was_occupied:
                        # Mark as occupied
                        self.spot_states[spot_id] = True
                        self.sequential_numbers[spot_id] = self.next_sequential
                        self.next_sequential += 1
                        
                        changes[spot_id] = {
                            'occupied': True,
                            'detected_at': datetime.fromtimestamp(
                                self.spot_timers[spot_id], tz=timezone.utc
                            ).isoformat(),
                            'occupied_since': datetime.fromtimestamp(
                                current_time, tz=timezone.utc
                            ).isoformat(),
                            'sequential_number': self.sequential_numbers[spot_id]
                        }
                        logger.info(f"Spot {spot_id}: marked as OCCUPIED (#{self.sequential_numbers[spot_id]})")
            else:
                # No vehicle detected
                if spot_id in self.spot_timers:
                    del self.spot_timers[spot_id]
                
                if was_occupied:
                    # Mark as free
                    self.spot_states[spot_id] = False
                    if spot_id in self.sequential_numbers:
                        del self.sequential_numbers[spot_id]
                    
                    changes[spot_id] = {
                        'occupied': False,
                        'detected_at': None,
                        'occupied_since': None,
                        'sequential_number': None
                    }
                    logger.info(f"Spot {spot_id}: marked as FREE")
        
        return changes
    
    def get_spot_state(self, spot_id: str) -> Dict:
        """Get current state of a spot."""
        is_occupied = self.spot_states.get(spot_id, False)
        return {
            'occupied': is_occupied,
            'sequential_number': self.sequential_numbers.get(spot_id),
            'timer_active': spot_id in self.spot_timers,
            'timer_elapsed': (
                time.time() - self.spot_timers[spot_id]
                if spot_id in self.spot_timers else 0
            )
        }
    
    def get_all_states(self) -> Dict[str, Dict]:
        """Get states of all tracked spots."""
        return {
            spot_id: self.get_spot_state(spot_id)
            for spot_id in self.spot_states.keys()
        }
    
    def reset_spot(self, spot_id: str):
        """Reset a spot's state."""
        if spot_id in self.spot_timers:
            del self.spot_timers[spot_id]
        if spot_id in self.spot_states:
            del self.spot_states[spot_id]
        if spot_id in self.sequential_numbers:
            del self.sequential_numbers[spot_id]
        logger.info(f"Reset spot {spot_id}")
    
    def set_occupancy_threshold(self, minutes: int):
        """Update occupancy threshold."""
        self.occupancy_minutes = minutes
        logger.info(f"Occupancy threshold updated to {minutes} minutes")

