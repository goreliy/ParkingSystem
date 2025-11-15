"""
Менеджер для автоматической загрузки и управления FFmpeg.
"""
import logging
import os
import platform
import shutil
import subprocess
import zipfile
import tarfile
from pathlib import Path
from typing import Optional
import requests
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# URLs для скачивания FFmpeg
FFMPEG_URLS = {
    'Windows': {
        'x86_64': 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip',
        'x86': 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip'
    },
    'Linux': {
        'x86_64': None,  # Используем системный пакетный менеджер
        'aarch64': None
    }
}


class FFmpegManager:
    """Менеджер для автоматической загрузки и управления FFmpeg."""
    
    def __init__(self, root_dir: Path = None):
        """
        Инициализация менеджера FFmpeg.
        
        Args:
            root_dir: Корневая директория проекта
        """
        if root_dir is None:
            root_dir = Path(__file__).parent.parent.parent
        self.root_dir = Path(root_dir)
        self.ffmpeg_dir = self.root_dir / 'tools' / 'ffmpeg'
        self.ffmpeg_dir.mkdir(parents=True, exist_ok=True)
        
        self.system = platform.system()
        self.machine = platform.machine()
        
    def find_ffmpeg(self) -> Optional[str]:
        """
        Найти FFmpeg в системе или в загруженных файлах.
        
        Returns:
            Путь к FFmpeg или None
        """
        # Сначала проверить системный PATH
        ffmpeg_path = shutil.which('ffmpeg')
        if ffmpeg_path:
            logger.info(f"FFmpeg found in PATH: {ffmpeg_path}")
            return ffmpeg_path
        
        # Проверить в локальной директории
        if self.system == 'Windows':
            local_ffmpeg = self.ffmpeg_dir / 'ffmpeg.exe'
        else:
            local_ffmpeg = self.ffmpeg_dir / 'ffmpeg'
        
        if local_ffmpeg.exists() and os.access(local_ffmpeg, os.X_OK):
            logger.info(f"FFmpeg found locally: {local_ffmpeg}")
            return str(local_ffmpeg)
        
        return None
    
    def is_ffmpeg_available(self) -> bool:
        """Проверить, доступен ли FFmpeg."""
        ffmpeg_path = self.find_ffmpeg()
        if not ffmpeg_path:
            return False
        
        try:
            result = subprocess.run(
                [ffmpeg_path, '-version'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            logger.error(f"Error checking FFmpeg: {e}")
            return False
    
    def download_ffmpeg_windows(self, progress_callback=None) -> Optional[str]:
        """
        Загрузить FFmpeg для Windows.
        
        Args:
            progress_callback: Callback для отслеживания прогресса
            
        Returns:
            Путь к FFmpeg или None
        """
        if self.system != 'Windows':
            return None
        
        url = FFMPEG_URLS['Windows'].get(self.machine) or FFMPEG_URLS['Windows']['x86_64']
        if not url:
            logger.error("No FFmpeg URL for this Windows architecture")
            return None
        
        logger.info(f"Downloading FFmpeg from {url}")
        
        try:
            # Скачать архив
            zip_path = self.ffmpeg_dir / 'ffmpeg.zip'
            response = requests.get(url, stream=True, timeout=30)
            total_size = int(response.headers.get('content-length', 0))
            
            with open(zip_path, 'wb') as f:
                downloaded = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if progress_callback and total_size > 0:
                            progress = (downloaded / total_size) * 100
                            progress_callback(progress)
            
            logger.info("Extracting FFmpeg...")
            # Распаковать
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall(self.ffmpeg_dir)
            
            # Найти ffmpeg.exe в распакованных файлах
            for root, dirs, files in os.walk(self.ffmpeg_dir):
                if 'ffmpeg.exe' in files:
                    ffmpeg_path = Path(root) / 'ffmpeg.exe'
                    # Переместить в корень ffmpeg_dir
                    target_path = self.ffmpeg_dir / 'ffmpeg.exe'
                    if ffmpeg_path != target_path:
                        shutil.move(str(ffmpeg_path), str(target_path))
                    # Удалить архив и лишние файлы
                    zip_path.unlink()
                    # Очистить распакованные директории (оставить только exe)
                    for item in self.ffmpeg_dir.iterdir():
                        if item.is_dir():
                            shutil.rmtree(item)
                        elif item.name != 'ffmpeg.exe':
                            item.unlink()
                    
                    logger.info(f"FFmpeg downloaded to {target_path}")
                    return str(target_path)
            
            logger.error("FFmpeg.exe not found in downloaded archive")
            return None
            
        except Exception as e:
            logger.error(f"Error downloading FFmpeg: {e}")
            return None
    
    def install_ffmpeg_linux(self) -> bool:
        """
        Попытаться установить FFmpeg через системный пакетный менеджер.
        
        Returns:
            True если установка успешна
        """
        if self.system != 'Linux':
            return False
        
        logger.info("Attempting to install FFmpeg via package manager...")
        
        # Определить пакетный менеджер
        if shutil.which('apt-get'):
            cmd = ['sudo', 'apt-get', 'update', '&&', 'sudo', 'apt-get', 'install', '-y', 'ffmpeg']
        elif shutil.which('yum'):
            cmd = ['sudo', 'yum', 'install', '-y', 'ffmpeg']
        elif shutil.which('dnf'):
            cmd = ['sudo', 'dnf', 'install', '-y', 'ffmpeg']
        elif shutil.which('pacman'):
            cmd = ['sudo', 'pacman', '-S', '--noconfirm', 'ffmpeg']
        else:
            logger.error("No supported package manager found")
            return False
        
        try:
            # Запустить установку
            logger.warning("FFmpeg installation requires sudo. Please run manually:")
            logger.warning(f"  {' '.join(cmd)}")
            return False
        except Exception as e:
            logger.error(f"Error installing FFmpeg: {e}")
            return False
    
    def ensure_ffmpeg(self, auto_download: bool = True) -> Optional[str]:
        """
        Убедиться, что FFmpeg доступен, при необходимости загрузить.
        
        Args:
            auto_download: Автоматически загружать если не найден
            
        Returns:
            Путь к FFmpeg или None
        """
        # Проверить наличие
        ffmpeg_path = self.find_ffmpeg()
        if ffmpeg_path and self.is_ffmpeg_available():
            return ffmpeg_path
        
        if not auto_download:
            return None
        
        logger.info("FFmpeg not found, attempting to download...")
        
        if self.system == 'Windows':
            return self.download_ffmpeg_windows()
        elif self.system == 'Linux':
            # Для Linux лучше использовать системный пакетный менеджер
            logger.warning("For Linux, please install FFmpeg manually:")
            logger.warning("  sudo apt-get install ffmpeg  # Ubuntu/Debian")
            logger.warning("  sudo yum install ffmpeg      # CentOS/RHEL")
            return None
        else:
            logger.error(f"Unsupported system: {self.system}")
            return None
    
    def get_ffmpeg_path(self) -> str:
        """
        Получить путь к FFmpeg (для использования в конфигурации).
        
        Returns:
            Путь к FFmpeg или 'ffmpeg' (для поиска в PATH)
        """
        ffmpeg_path = self.find_ffmpeg()
        if ffmpeg_path:
            return ffmpeg_path
        return 'ffmpeg'

