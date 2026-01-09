import asyncio
import os
from typing import Optional, Callable

from app.config import settings
from app.auth import get_config_data


# Global model cache
_pipeline_cache = {}


def download_whisper_model(model_name: str) -> str:
    """Download OpenVINO Whisper model from HuggingFace and return local path."""
    from huggingface_hub import snapshot_download
    
    # Map short names to HuggingFace model IDs
    model_mapping = {
        "tiny": "OpenVINO/whisper-tiny-fp16-ov",
        "base": "OpenVINO/whisper-base-fp16-ov",
        "small": "OpenVINO/whisper-small-fp16-ov",
        "medium": "OpenVINO/whisper-medium-fp16-ov",
        "large-v2": "OpenVINO/whisper-large-v2-fp16-ov",
        "large-v3-int4": "OpenVINO/whisper-large-v3-int4-ov",
        "large-v3-int8": "OpenVINO/whisper-large-v3-int8-ov",
        "large-v3-fp16": "OpenVINO/whisper-large-v3-fp16-ov",
    }
    
    hf_model_id = model_mapping.get(model_name)
    if not hf_model_id:
        hf_model_id = model_mapping["large-v3-int8"]
    
    # Download model to local cache
    local_path = os.path.join(settings.models_dir, hf_model_id.replace("/", "_"))
    
    if not os.path.exists(local_path):
        print(f"Downloading model {hf_model_id}...")
        snapshot_download(
            repo_id=hf_model_id,
            local_dir=local_path,
            local_dir_use_symlinks=False
        )
        print(f"Model downloaded to {local_path}")
    
    return local_path


def get_whisper_pipeline(model_name: str):
    """Get or create an OpenVINO GenAI Whisper pipeline."""
    import openvino_genai
    
    if model_name not in _pipeline_cache:
        model_path = download_whisper_model(model_name)
        print(f"Loading OpenVINO Whisper pipeline from {model_path}")
        
        # Create pipeline with GPU device
        try:
            pipeline = openvino_genai.WhisperPipeline(model_path, device="GPU")
            print("Pipeline loaded on GPU")
        except Exception as e:
            print(f"GPU loading failed ({e}), falling back to CPU")
            pipeline = openvino_genai.WhisperPipeline(model_path, device="CPU")
            print("Pipeline loaded on CPU")
        
        _pipeline_cache[model_name] = pipeline
    
    return _pipeline_cache[model_name]


async def transcribe_audio(
    audio_path: str,
    output_srt_path: str,
    model_name: str = "large-v3-int8",
    language: str = "auto",
    cpu_threads: int = 4,
    progress_callback: Optional[Callable] = None
) -> str:
    """
    Transcribe audio file to SRT subtitle format using OpenVINO GenAI.
    Returns path to generated SRT file.
    """
    
    loop = asyncio.get_event_loop()
    
    def do_transcribe():
        import librosa
        
        pipeline = get_whisper_pipeline(model_name)
        
        # Load audio at 16kHz and convert to list (required by openvino_genai)
        audio, sr = librosa.load(audio_path, sr=16000)
        raw_speech = audio.tolist()
        
        # Generate config
        config = pipeline.get_generation_config()
        config.task = "transcribe"
        config.return_timestamps = True
        
        # Set language if specified (use <|xx|> format)
        if language != "auto" and language:
            config.language = f"<|{language}|>"
        
        # Run transcription
        result = pipeline.generate(raw_speech, config)
        
        return result
    
    result = await loop.run_in_executor(None, do_transcribe)
    
    # Parse result and generate SRT
    srt_content = generate_srt_from_result(result)
    
    with open(output_srt_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    
    return output_srt_path


def generate_srt_from_result(result) -> str:
    """Generate SRT content from OpenVINO GenAI result."""
    srt_lines = []
    
    # Check if result has chunks (timestamped segments)
    if hasattr(result, 'chunks') and result.chunks:
        for i, chunk in enumerate(result.chunks, 1):
            start_time = format_timestamp(chunk.start_ts)
            end_time = format_timestamp(chunk.end_ts)
            text = chunk.text.strip()
            
            if text:
                srt_lines.append(f"{i}")
                srt_lines.append(f"{start_time} --> {end_time}")
                srt_lines.append(text)
                srt_lines.append("")
    else:
        # Fallback: single text without timestamps
        text = str(result) if result else ""
        if text.strip():
            srt_lines.append("1")
            srt_lines.append("00:00:00,000 --> 99:59:59,999")
            srt_lines.append(text.strip())
            srt_lines.append("")
    
    return "\n".join(srt_lines)


def generate_srt(segments) -> str:
    """Generate SRT content from segments (compatibility function)."""
    srt_lines = []
    
    for i, segment in enumerate(segments, 1):
        start_time = format_timestamp(segment.start)
        end_time = format_timestamp(segment.end)
        text = segment.text.strip()
        
        srt_lines.append(f"{i}")
        srt_lines.append(f"{start_time} --> {end_time}")
        srt_lines.append(text)
        srt_lines.append("")
    
    return "\n".join(srt_lines)


def format_timestamp(seconds: float) -> str:
    """Format seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    if seconds is None:
        return "00:00:00,000"
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


async def transcribe_with_progress(
    audio_path: str,
    output_srt_path: str,
    model_name: str = "large-v3-int8",
    language: str = "auto",
    cpu_threads: int = 4,
    progress_callback: Optional[Callable] = None,
    job_id: str = None,
    is_cancelled: Optional[Callable] = None
) -> str:
    """
    Transcribe audio with REAL progress tracking using OpenVINO GenAI streamer.
    Progress is based on actual chunks processed (each ~30s of audio).
    """
    from app.tasks.extractor import get_video_duration
    
    # Get audio duration for calculating total chunks
    duration = await get_video_duration(audio_path)
    
    # Whisper processes audio in ~30 second chunks
    CHUNK_DURATION = 30.0
    total_chunks = max(1, int(duration / CHUNK_DURATION) + 1) if duration > 0 else 1
    
    loop = asyncio.get_event_loop()
    chunks_processed = [0]  # Mutable counter for use in callback
    cancelled = [False]  # Track if cancelled
    
    def do_transcribe():
        import librosa
        
        pipeline = get_whisper_pipeline(model_name)
        
        # Load audio at 16kHz and convert to list (required by openvino_genai)
        audio, sr = librosa.load(audio_path, sr=16000)
        raw_speech = audio.tolist()
        
        # Generate config
        config = pipeline.get_generation_config()
        config.task = "transcribe"
        config.return_timestamps = True
        
        # Set language if specified (use <|xx|> format)
        if language != "auto" and language:
            config.language = f"<|{language}|>"
        
        # Streamer callback - called for each chunk of processed text
        def on_chunk(text: str) -> bool:
            """Called for each processed chunk. Returns True to STOP processing."""
            # Check if cancelled
            if is_cancelled and is_cancelled():
                print(f"[TRANSCRIBE] Job cancelled, stopping transcription")
                cancelled[0] = True
                return True  # Stop processing
            
            chunks_processed[0] += 1
            
            # Calculate real progress based on chunks
            progress = min(95, (chunks_processed[0] / total_chunks) * 100)
            
            # Send progress update
            if progress_callback:
                asyncio.run_coroutine_threadsafe(
                    progress_callback(progress),
                    loop
                )
            
            return False  # Continue processing
        
        # Run transcription with streamer for REAL progress
        result = pipeline.generate(raw_speech, config, streamer=on_chunk)
        
        return result, cancelled[0]
    
    result, was_cancelled = await loop.run_in_executor(None, do_transcribe)
    
    # If cancelled, raise exception
    if was_cancelled:
        raise Exception("Transcription cancelled")
    
    # Generate SRT file
    srt_content = generate_srt_from_result(result)
    
    with open(output_srt_path, 'w', encoding='utf-8') as f:
        f.write(srt_content)
    
    if progress_callback:
        await progress_callback(100)
    
    return output_srt_path
