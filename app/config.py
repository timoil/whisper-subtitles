import os
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Security
    secret_key: str = "change-me-in-production"
    algorithm: str = "HS256"
    access_token_expire_hours: int = 24
    
    # Whisper settings
    default_model: str = "large-v3-int8"
    cpu_threads: int = 4
    default_language: str = "auto"
    
    # Paths
    data_dir: str = "/app/data"
    models_dir: str = "/app/models"
    
    # Available models with descriptions (OpenVINO compatible)
    @property
    def available_models(self) -> dict:
        return {
            "tiny": {
                "name": "Tiny",
                "size": "~75 MB",
                "accuracy": 2,
                "speed": "~32x faster than realtime",
                "description": "For quick tests, low accuracy"
            },
            "base": {
                "name": "Base", 
                "size": "~150 MB",
                "accuracy": 3,
                "speed": "~16x faster than realtime",
                "description": "Fast but with errors"
            },
            "small": {
                "name": "Small",
                "size": "~500 MB", 
                "accuracy": 4,
                "speed": "~10x faster than realtime",
                "description": "Good balance of speed and quality"
            },
            "medium": {
                "name": "Medium",
                "size": "~1.5 GB",
                "accuracy": 4,
                "speed": "~5x faster than realtime",
                "description": "Recommended for most tasks"
            },
            "large-v2": {
                "name": "Large V2",
                "size": "~3 GB",
                "accuracy": 5,
                "speed": "~3x faster than realtime",
                "description": "Maximum accuracy, all languages"
            },
            "large-v3-int4": {
                "name": "Large V3 (INT4)",
                "size": "~1 GB",
                "accuracy": 4,
                "speed": "Fastest (N150 Optimized)",
                "description": "Maximum speed for Intel N150"
            },
            "large-v3-int8": {
                "name": "Large V3 (INT8)",
                "size": "~1.5 GB",
                "accuracy": 5,
                "speed": "Fast (N150 Recommended)",
                "description": "Best balance of speed/quality"
            },
            "large-v3-fp16": {
                "name": "Large V3 (FP16)",
                "size": "~3 GB",
                "accuracy": 5,
                "speed": "Slowest (High Precision)",
                "description": "Original precision"
            }
        }
    
    @property
    def uploads_dir(self) -> str:
        return os.path.join(self.data_dir, "uploads")
    
    @property
    def downloads_dir(self) -> str:
        return os.path.join(self.data_dir, "downloads")
    
    @property
    def temp_dir(self) -> str:
        return os.path.join(self.data_dir, "temp")
    
    @property
    def output_dir(self) -> str:
        return os.path.join(self.data_dir, "output")
    
    @property
    def db_path(self) -> str:
        return os.path.join(self.data_dir, "whisper.db")
    
    @property
    def config_path(self) -> str:
        return os.path.join(self.data_dir, "config.json")
    
    class Config:
        env_prefix = ""
        case_sensitive = False

settings = Settings()

# Ensure directories exist
for dir_path in [settings.uploads_dir, settings.downloads_dir, settings.temp_dir, settings.output_dir, settings.models_dir]:
    os.makedirs(dir_path, exist_ok=True)
