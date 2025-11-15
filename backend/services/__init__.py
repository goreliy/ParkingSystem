from .video_processor import VideoProcessor, VideoProcessorManager
from .detector import Detector, Detection
from .auto_markup import AutoMarkupService, VehicleTracker, SpotProposal, StableVehicle

__all__ = [
    'VideoProcessor', 'VideoProcessorManager', 
    'Detector', 'Detection',
    'AutoMarkupService', 'VehicleTracker', 'SpotProposal', 'StableVehicle'
]

