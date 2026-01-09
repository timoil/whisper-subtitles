from pydantic import BaseModel
from typing import Optional, List
from enum import Enum
from datetime import datetime


class JobStatus(str, Enum):
    """Job status enumeration."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    AWAITING_TRACK = "awaiting_track"
    TRANSCRIBING = "transcribing"
    EMBEDDING = "embedding"
    CONVERTING = "converting"  # For streaming version creation
    COMPLETED = "completed"
    FAILED = "failed"


class JobType(str, Enum):
    """Job type enumeration."""
    UPLOAD = "upload"
    URL = "url"
    MAGNET = "magnet"
    TORRENT = "torrent"


class AudioTrack(BaseModel):
    """Audio track information."""
    index: int
    codec: str
    language: Optional[str] = None
    title: Optional[str] = None
    channels: int = 2
    default: bool = False


class JobFile(BaseModel):
    """Individual file within a job (for multi-file torrents)."""
    id: str
    filename: str
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    audio_tracks: List[AudioTrack] = []
    selected_track: Optional[int] = None
    srt_path: Optional[str] = None
    output_path: Optional[str] = None
    streaming_path: Optional[str] = None  # Path to streaming version with burned-in subs
    error: Optional[str] = None


class Job(BaseModel):
    """Main job model."""
    id: str
    type: JobType
    status: JobStatus = JobStatus.PENDING
    progress: float = 0.0
    created_at: datetime
    updated_at: datetime
    
    # Source info
    source: str  # URL, magnet link, or original filename
    
    # Files (for multi-file support)
    files: List[JobFile] = []
    
    # Settings
    embed_subtitles: bool = False
    language: str = "auto"
    model: str = "large-v3-int8"
    
    # Error info
    error: Optional[str] = None
    
    # Group info (for multi-file torrents)
    is_group: bool = False
    group_name: Optional[str] = None
    
    # Torrent file selection (1-based indices)
    selected_indices: Optional[List[int]] = None
    
    # Download progress info
    download_speed: Optional[str] = None  # e.g. "5.2MB/s"
    eta: Optional[str] = None  # e.g. "10m30s"
    is_paused: bool = False  # Pause state for downloads


class LoginRequest(BaseModel):
    """Login request model."""
    username: str
    password: str


class LoginResponse(BaseModel):
    """Login response model."""
    access_token: str
    token_type: str = "bearer"


class PasswordChangeRequest(BaseModel):
    """Password change request model."""
    current_password: str
    new_password: str


class SettingsUpdateRequest(BaseModel):
    """Settings update request model."""
    model: Optional[str] = None
    cpu_threads: Optional[int] = None
    language: Optional[str] = None


class JobCreateRequest(BaseModel):
    """Job creation request model."""
    type: JobType
    source: Optional[str] = None  # URL or magnet link
    embed_subtitles: bool = False
    language: str = "auto"


class TrackSelectionRequest(BaseModel):
    """Track selection request model."""
    track_index: int
    apply_to_all: bool = False  # For multi-file jobs


class TorrentFileInfo(BaseModel):
    """Torrent file information for file selection."""
    index: int
    path: str
    size: int
    size_formatted: str
    selected: bool = True


class FileSelectionRequest(BaseModel):
    """Request to start download with selected files."""
    selected_indices: List[int]  # 1-based indices of files to download

