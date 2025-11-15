"""
State management and aggregation for parking spaces.
"""
import logging
import threading
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StateManager:
    """Manages parking state and provides aggregated views."""
    
    def __init__(self, json_store):
        self.store = json_store
        self.lock = threading.Lock()
        self.event_callbacks = []
        
    def update_spot_state(self, spot_id: str, state_update: Dict):
        """
        Update a single spot's state.
        
        Args:
            spot_id: Spot identifier
            state_update: New state data
        """
        def updater(data):
            # Find the space for this spot
            spots = self.store.get_spots()
            spot = next((s for s in spots if s['id'] == spot_id), None)
            
            if not spot:
                logger.warning(f"Spot {spot_id} not found")
                return data
            
            space_id = spot['space_id']
            
            # Ensure space exists in state
            if space_id not in data['spaces']:
                data['spaces'][space_id] = {
                    'total_spots': 0,
                    'occupied_spots': 0,
                    'free_spots': 0,
                    'spots': {}
                }
            
            # Update spot state
            data['spaces'][space_id]['spots'][spot_id] = state_update
            
            # Recalculate aggregates for this space
            self._recalculate_space_stats(data, space_id)
            
            return data
        
        with self.lock:
            self.store.update_state(updater)
            self._notify_state_change('spot_update', {
                'spot_id': spot_id,
                'state': state_update
            })
    
    def update_multiple_spots(self, updates: Dict[str, Dict]):
        """Update multiple spots at once."""
        def updater(data):
            spots = self.store.get_spots()
            affected_spaces = set()
            
            for spot_id, state_update in updates.items():
                spot = next((s for s in spots if s['id'] == spot_id), None)
                if not spot:
                    continue
                
                space_id = spot['space_id']
                affected_spaces.add(space_id)
                
                if space_id not in data['spaces']:
                    data['spaces'][space_id] = {
                        'total_spots': 0,
                        'occupied_spots': 0,
                        'free_spots': 0,
                        'spots': {}
                    }
                
                data['spaces'][space_id]['spots'][spot_id] = state_update
            
            # Recalculate stats for affected spaces
            for space_id in affected_spaces:
                self._recalculate_space_stats(data, space_id)
            
            return data
        
        with self.lock:
            self.store.update_state(updater)
            self._notify_state_change('bulk_update', {'count': len(updates)})
    
    def _recalculate_space_stats(self, state_data: Dict, space_id: str):
        """Recalculate aggregate statistics for a space."""
        spots = self.store.get_spots()
        space_spots = [s for s in spots if s['space_id'] == space_id and s['type'] == 'parking']
        
        total = len(space_spots)
        occupied = sum(
            1 for spot in space_spots
            if state_data['spaces'][space_id]['spots'].get(spot['id'], {}).get('occupied', False)
        )
        free = total - occupied
        
        state_data['spaces'][space_id]['total_spots'] = total
        state_data['spaces'][space_id]['occupied_spots'] = occupied
        state_data['spaces'][space_id]['free_spots'] = free
    
    def get_space_state(self, space_id: str) -> Optional[Dict]:
        """Get current state of a parking space."""
        state = self.store.get_state()
        return state['spaces'].get(space_id)
    
    def get_all_spaces_summary(self) -> List[Dict]:
        """Get summary of all parking spaces."""
        state = self.store.get_state()
        spaces = self.store.get_spaces()
        
        summary = []
        for space in spaces:
            space_state = state['spaces'].get(space['id'], {
                'total_spots': 0,
                'occupied_spots': 0,
                'free_spots': 0
            })
            
            summary.append({
                'id': space['id'],
                'name': space['name'],
                'total_spots': space_state.get('total_spots', 0),
                'occupied_spots': space_state.get('occupied_spots', 0),
                'free_spots': space_state.get('free_spots', 0),
                'camera_ids': space.get('camera_ids', [])
            })
        
        return summary
    
    def get_spot_details(self, space_id: str) -> List[Dict]:
        """Get detailed information about spots in a space."""
        state = self.store.get_state()
        spots = self.store.get_spots()
        
        space_spots = [s for s in spots if s['space_id'] == space_id]
        space_state = state['spaces'].get(space_id, {})
        
        details = []
        for spot in space_spots:
            spot_state = space_state.get('spots', {}).get(spot['id'], {})
            details.append({
                'id': spot['id'],
                'label': spot['label'],
                'type': spot['type'],
                'rect': spot['rect'],
                'occupied': spot_state.get('occupied', False),
                'sequential_number': spot_state.get('sequential_number'),
                'detected_at': spot_state.get('detected_at'),
                'occupied_since': spot_state.get('occupied_since')
            })
        
        return details
    
    def initialize_space(self, space_id: str):
        """Initialize state for a new space."""
        def updater(data):
            if space_id not in data['spaces']:
                data['spaces'][space_id] = {
                    'total_spots': 0,
                    'occupied_spots': 0,
                    'free_spots': 0,
                    'spots': {}
                }
                self._recalculate_space_stats(data, space_id)
            return data
        
        with self.lock:
            self.store.update_state(updater)
    
    def remove_space(self, space_id: str):
        """Remove space from state."""
        def updater(data):
            if space_id in data['spaces']:
                del data['spaces'][space_id]
            return data
        
        with self.lock:
            self.store.update_state(updater)
    
    def register_event_callback(self, callback):
        """Register a callback for state change events."""
        self.event_callbacks.append(callback)
    
    def _notify_state_change(self, event_type: str, data: Dict):
        """Notify all registered callbacks of state change."""
        for callback in self.event_callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                logger.error(f"Error in event callback: {e}")
    
    def get_active_stream(self) -> Optional[Dict]:
        """Get information about active stream."""
        state = self.store.get_state()
        return state.get('active_stream')
    
    def set_active_stream(self, stream_info: Optional[Dict]):
        """Set active stream information."""
        def updater(data):
            data['active_stream'] = stream_info
            return data
        
        with self.lock:
            self.store.update_state(updater)

