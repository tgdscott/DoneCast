"""Test script for Auphonic API integration.

Usage:
    python test_auphonic.py <path_to_audio_file>

Example:
    python test_auphonic.py /path/to/test_episode.mp3
"""

import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

log = logging.getLogger(__name__)


def test_auphonic_api(audio_path: Path):
    """Test Auphonic API with a sample audio file."""
    
    log.info("=" * 80)
    log.info("AUPHONIC API TEST")
    log.info("=" * 80)
    
    # Check if file exists
    if not audio_path.exists():
        log.error("❌ Audio file not found: %s", audio_path)
        return False
    
    log.info("✅ Audio file found: %s (%.2f MB)", audio_path, audio_path.stat().st_size / 1024 / 1024)
    
    # Import Auphonic client
    try:
        from api.services.auphonic_client import AuphonicClient, process_episode_with_auphonic
        log.info("✅ Auphonic client imported successfully")
    except ImportError as e:
        log.error("❌ Failed to import Auphonic client: %s", e)
        return False
    
    # Test account info
    try:
        log.info("\n--- Testing Account Info ---")
        client = AuphonicClient()
        account_info = client.get_info()
        
        log.info("✅ Connected to Auphonic API")
        log.info("Account info:")
        log.info("  - User ID: %s", account_info.get("data", {}).get("user", {}).get("username"))
        log.info("  - Credits: %s", account_info.get("data", {}).get("credits"))
        log.info("  - Credits Used: %s", account_info.get("data", {}).get("credits_used"))
        
    except Exception as e:
        log.error("❌ Failed to get account info: %s", e)
        return False
    
    # Test audio processing
    try:
        log.info("\n--- Testing Audio Processing ---")
        log.info("This will:")
        log.info("  1. Upload audio to Auphonic")
        log.info("  2. Create production with professional processing")
        log.info("  3. Wait for processing to complete")
        log.info("  4. Download processed audio")
        log.info("")
        
        import tempfile
        output_dir = Path(tempfile.gettempdir()) / "auphonic_test_output"
        output_dir.mkdir(parents=True, exist_ok=True)
        
        log.info("Output directory: %s", output_dir)
        log.info("Starting processing... (this may take 1-5 minutes)")
        
        result = process_episode_with_auphonic(
            audio_path=audio_path,
            episode_title="Test Episode - Auphonic Integration",
            output_dir=output_dir,
            enable_denoise=True,
            enable_leveler=True,
            enable_autoeq=True,
            enable_normloudness=True,
            loudness_target=-16.0,
            enable_crossgate=True,  # Filler word removal
            enable_speech_recognition=True,  # Transcription
            webhook_url=None,  # Synchronous
        )
        
        log.info("\n✅ Processing complete!")
        log.info("Results:")
        log.info("  - Production UUID: %s", result.get("production_uuid"))
        log.info("  - Status: %s", result.get("status"))
        log.info("  - Output audio: %s", result.get("output_audio_path"))
        log.info("  - Transcript: %s", result.get("transcript_path") or "None")
        log.info("  - Duration: %s ms", result.get("duration_ms"))
        
        output_audio = Path(result.get("output_audio_path", ""))
        if output_audio.exists():
            log.info("  - Output size: %.2f MB", output_audio.stat().st_size / 1024 / 1024)
            log.info("\n🎉 Test successful! Processed audio saved to:")
            log.info("    %s", output_audio)
            
            # Compare file sizes
            input_size = audio_path.stat().st_size
            output_size = output_audio.stat().st_size
            size_diff_pct = ((output_size - input_size) / input_size) * 100
            log.info("\nFile size comparison:")
            log.info("  - Input:  %.2f MB", input_size / 1024 / 1024)
            log.info("  - Output: %.2f MB (%+.1f%%)", output_size / 1024 / 1024, size_diff_pct)
        else:
            log.error("❌ Output audio file not found!")
            return False
        
        return True
        
    except Exception as e:
        log.error("❌ Audio processing failed: %s", e, exc_info=True)
        return False


def main():
    """Main test runner."""
    
    if len(sys.argv) < 2:
        log.error("Usage: python test_auphonic.py <path_to_audio_file>")
        log.error("Example: python test_auphonic.py /tmp/test_episode.mp3")
        sys.exit(1)
    
    audio_path = Path(sys.argv[1])
    
    success = test_auphonic_api(audio_path)
    
    log.info("\n" + "=" * 80)
    if success:
        log.info("✅ ALL TESTS PASSED")
        log.info("=" * 80)
        sys.exit(0)
    else:
        log.error("❌ TESTS FAILED")
        log.error("=" * 80)
        sys.exit(1)


if __name__ == "__main__":
    main()
