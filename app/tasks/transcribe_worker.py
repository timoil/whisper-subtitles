#!/usr/bin/env python3
"""
Standalone transcription worker that can be killed.
Used for proper job cancellation support.

Outputs JSON progress updates to stdout:
  {"status": "loading_model", "progress": 0}
  {"status": "transcribing", "progress": 50}
  {"status": "completed", "progress": 100, "output": "/path/to/file.srt"}
  {"status": "error", "error": "error message"}
"""
import sys
import json
import os
import signal

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings


def format_timestamp(seconds: float) -> str:
    """Format seconds to SRT timestamp format (HH:MM:SS,mmm)."""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


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
        # Fallback to recommended INT8 model if unknown
        hf_model_id = model_mapping["large-v3-int8"]

    
    # Download model to local cache
    local_path = os.path.join(settings.models_dir, hf_model_id.replace("/", "_"))
    
    if not os.path.exists(local_path):
        print(json.dumps({"status": "downloading_model", "progress": 0, "model": hf_model_id}), flush=True)
        snapshot_download(
            repo_id=hf_model_id,
            local_dir=local_path,
            local_dir_use_symlinks=False
        )
    
    return local_path


def generate_srt_from_result(result) -> str:
    """Generate SRT content from OpenVINO GenAI result."""
    srt_lines = []
    segment_idx = 1
    
    # OpenVINO GenAI returns chunks with timestamps
    if hasattr(result, 'chunks') and result.chunks:
        for chunk in result.chunks:
            start_time = chunk.start_ts
            end_time = chunk.end_ts
            text = chunk.text.strip()
            
            if text:
                srt_lines.append(str(segment_idx))
                srt_lines.append(f"{format_timestamp(start_time)} --> {format_timestamp(end_time)}")
                srt_lines.append(text)
                srt_lines.append("")
                segment_idx += 1
    else:
        # Fallback: no timestamps, use full text
        text = str(result).strip() if result else ""
        if text:
            srt_lines.append("1")
            srt_lines.append("00:00:00,000 --> 00:10:00,000")
            srt_lines.append(text)
            srt_lines.append("")
    
    return "\n".join(srt_lines)


def main():
    if len(sys.argv) < 4:
        print(json.dumps({"status": "error", "error": "Usage: transcribe_worker.py <audio_path> <output_srt> <model_name> [language]"}), flush=True)
        sys.exit(1)
    
    audio_path = sys.argv[1]
    output_srt_path = sys.argv[2]
    model_name = sys.argv[3]
    language = sys.argv[4] if len(sys.argv) > 4 else "auto"
    
    # Handle termination signals gracefully
    def signal_handler(signum, frame):
        print(json.dumps({"status": "cancelled", "progress": 0}), flush=True)
        sys.exit(0)
    
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        import openvino_genai
        import librosa
        
        # Load model
        print(json.dumps({"status": "loading_model", "progress": 0}), flush=True)
        
        model_path = download_whisper_model(model_name)
        
        print(json.dumps({"status": "loading_model", "progress": 5}), flush=True)
        
        # Create pipeline - try GPU first, fallback to CPU
        try:
            pipeline = openvino_genai.WhisperPipeline(model_path, device="GPU")
        except Exception:
            pipeline = openvino_genai.WhisperPipeline(model_path, device="CPU")
        
        print(json.dumps({"status": "loading_audio", "progress": 10}), flush=True)
        
        # Load audio at 16kHz (Whisper requirement)
        audio, sr = librosa.load(audio_path, sr=16000)
        
        # Get audio duration for progress calculation
        duration = len(audio) / sr
        
        # Convert to list for OpenVINO - but do it efficiently
        # OpenVINO GenAI expects raw audio samples
        raw_speech = audio.astype('float32')
        
        # Free librosa's buffer
        del audio
        import gc
        gc.collect()
        
        print(json.dumps({"status": "transcribing", "progress": 15}), flush=True)
        
        # Configure generation
        config = pipeline.get_generation_config()
        config.task = "transcribe"
        config.return_timestamps = True
        
        if language != "auto" and language:
            config.language = f"<|{language}|>"
        
        # Track progress based on processed chunks
        chunks_processed = [0]
        total_chunks = max(1, int(duration / 30) + 1)  # ~30s per chunk
        
        def on_chunk(text: str) -> bool:
            """Called for each processed chunk. Returns False to continue."""
            chunks_processed[0] += 1
            progress = min(95, 15 + int((chunks_processed[0] / total_chunks) * 80))
            print(json.dumps({"status": "transcribing", "progress": progress}), flush=True)
            return False  # Continue processing
        
        # Run transcription with streamer for progress
        result = pipeline.generate(raw_speech, config, streamer=on_chunk)
        
        # Generate SRT
        srt_content = generate_srt_from_result(result)
        
        with open(output_srt_path, 'w', encoding='utf-8') as f:
            f.write(srt_content)
        
        print(json.dumps({"status": "completed", "progress": 100, "output": output_srt_path}), flush=True)
        
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(json.dumps({"status": "error", "error": error_msg, "traceback": traceback.format_exc()}), flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
