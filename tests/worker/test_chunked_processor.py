"""Unit tests for chunked_processor.py

Tests for should_use_chunking() branches and GCS failure handling.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, Mock
import pytest

# Ensure backend package import path
ROOT = Path(__file__).resolve().parents[2]
PKG_ROOT = ROOT / "backend"
if str(PKG_ROOT) not in sys.path:
    sys.path.insert(0, str(PKG_ROOT))

from tests.helpers.audio import make_tiny_wav
from worker.tasks.assembly import chunked_processor


class TestShouldUseChunking:
    """Test should_use_chunking() function with various conditions."""
    
    def test_disable_chunking_env_var_true(self, tmp_path, monkeypatch):
        """Test DISABLE_CHUNKING=true disables chunking."""
        monkeypatch.setenv("DISABLE_CHUNKING", "true")
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        
        # Create a long audio file (>10 min)
        audio_path = tmp_path / "long_audio.wav"
        make_tiny_wav(audio_path, ms=11 * 60 * 1000)  # 11 minutes
        
        result = chunked_processor.should_use_chunking(audio_path)
        assert result is False
    
    def test_disable_chunking_env_var_1(self, tmp_path, monkeypatch):
        """Test DISABLE_CHUNKING=1 disables chunking."""
        monkeypatch.setenv("DISABLE_CHUNKING", "1")
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        
        audio_path = tmp_path / "long_audio.wav"
        make_tiny_wav(audio_path, ms=11 * 60 * 1000)
        
        result = chunked_processor.should_use_chunking(audio_path)
        assert result is False
    
    def test_disable_chunking_env_var_yes(self, tmp_path, monkeypatch):
        """Test DISABLE_CHUNKING=yes disables chunking."""
        monkeypatch.setenv("DISABLE_CHUNKING", "yes")
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        
        audio_path = tmp_path / "long_audio.wav"
        make_tiny_wav(audio_path, ms=11 * 60 * 1000)
        
        result = chunked_processor.should_use_chunking(audio_path)
        assert result is False
    
    def test_storage_backend_r2_disables_chunking(self, tmp_path, monkeypatch):
        """Test STORAGE_BACKEND=r2 disables chunking."""
        monkeypatch.delenv("DISABLE_CHUNKING", raising=False)
        monkeypatch.setenv("STORAGE_BACKEND", "r2")
        
        audio_path = tmp_path / "long_audio.wav"
        make_tiny_wav(audio_path, ms=11 * 60 * 1000)
        
        result = chunked_processor.should_use_chunking(audio_path)
        assert result is False
    
    def test_storage_backend_not_gcs_disables_chunking(self, tmp_path, monkeypatch):
        """Test STORAGE_BACKEND != gcs disables chunking."""
        monkeypatch.delenv("DISABLE_CHUNKING", raising=False)
        monkeypatch.setenv("STORAGE_BACKEND", "s3")  # Some other backend
        
        audio_path = tmp_path / "long_audio.wav"
        make_tiny_wav(audio_path, ms=11 * 60 * 1000)
        
        result = chunked_processor.should_use_chunking(audio_path)
        assert result is False
    
    def test_duration_10_min_disables_chunking(self, tmp_path, monkeypatch):
        """Test duration <= 10 min disables chunking."""
        monkeypatch.delenv("DISABLE_CHUNKING", raising=False)
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        
        audio_path = tmp_path / "short_audio.wav"
        make_tiny_wav(audio_path, ms=10 * 60 * 1000)  # Exactly 10 minutes
        
        result = chunked_processor.should_use_chunking(audio_path)
        assert result is False
    
    def test_duration_5_min_disables_chunking(self, tmp_path, monkeypatch):
        """Test duration < 10 min disables chunking."""
        monkeypatch.delenv("DISABLE_CHUNKING", raising=False)
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        
        audio_path = tmp_path / "short_audio.wav"
        make_tiny_wav(audio_path, ms=5 * 60 * 1000)  # 5 minutes
        
        result = chunked_processor.should_use_chunking(audio_path)
        assert result is False
    
    def test_duration_11_min_enables_chunking(self, tmp_path, monkeypatch):
        """Test duration > 10 min enables chunking when GCS is available."""
        monkeypatch.delenv("DISABLE_CHUNKING", raising=False)
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        
        audio_path = tmp_path / "long_audio.wav"
        make_tiny_wav(audio_path, ms=11 * 60 * 1000)  # 11 minutes
        
        result = chunked_processor.should_use_chunking(audio_path)
        assert result is True
    
    def test_duration_30_min_enables_chunking(self, tmp_path, monkeypatch):
        """Test long files (>30 min) enable chunking."""
        monkeypatch.delenv("DISABLE_CHUNKING", raising=False)
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        
        audio_path = tmp_path / "long_audio.wav"
        make_tiny_wav(audio_path, ms=30 * 60 * 1000)  # 30 minutes
        
        result = chunked_processor.should_use_chunking(audio_path)
        assert result is True
    
    def test_file_not_found_returns_false(self, tmp_path, monkeypatch):
        """Test that missing file returns False."""
        monkeypatch.delenv("DISABLE_CHUNKING", raising=False)
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        
        audio_path = tmp_path / "nonexistent.wav"
        
        result = chunked_processor.should_use_chunking(audio_path)
        assert result is False


class TestSplitAudioIntoChunks:
    """Test split_audio_into_chunks() GCS failure handling."""
    
    def test_gcs_client_unavailable_raises_runtime_error(self, tmp_path, monkeypatch):
        """Test that GCS client unavailability raises RuntimeError."""
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        
        audio_path = tmp_path / "long_audio.wav"
        make_tiny_wav(audio_path, ms=11 * 60 * 1000)
        
        from uuid import uuid4
        user_id = uuid4()
        episode_id = uuid4()
        
        # Mock _get_gcs_client to return None (unavailable)
        # Patch at the infrastructure.gcs module level since it's imported inside the function
        with patch('infrastructure.gcs._get_gcs_client') as mock_get_client:
            mock_get_client.return_value = None
            
            with pytest.raises(RuntimeError) as exc_info:
                chunked_processor.split_audio_into_chunks(
                    audio_path=audio_path,
                    user_id=user_id,
                    episode_id=episode_id,
                )
            
            assert "GCS client unavailable" in str(exc_info.value)
            assert "Falling back to direct processing" in str(exc_info.value)
    
    def test_gcs_client_init_exception_raises_runtime_error(self, tmp_path, monkeypatch):
        """Test that GCS client init exception raises RuntimeError."""
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        
        audio_path = tmp_path / "long_audio.wav"
        make_tiny_wav(audio_path, ms=11 * 60 * 1000)
        
        from uuid import uuid4
        user_id = uuid4()
        episode_id = uuid4()
        
        # Mock _get_gcs_client to raise RuntimeError (credentials issue)
        with patch('infrastructure.gcs._get_gcs_client') as mock_get_client:
            mock_get_client.side_effect = RuntimeError("Credentials not found")
            
            with pytest.raises(RuntimeError) as exc_info:
                chunked_processor.split_audio_into_chunks(
                    audio_path=audio_path,
                    user_id=user_id,
                    episode_id=episode_id,
                )
            
            assert "GCS client unavailable" in str(exc_info.value)
            assert "Falling back to direct processing" in str(exc_info.value)
    
    def test_chunk_upload_failure_raises_runtime_error(self, tmp_path, monkeypatch):
        """Test that chunk upload failure raises RuntimeError and aborts chunking."""
        monkeypatch.setenv("STORAGE_BACKEND", "gcs")
        
        audio_path = tmp_path / "long_audio.wav"
        make_tiny_wav(audio_path, ms=11 * 60 * 1000)
        
        from uuid import uuid4
        user_id = uuid4()
        episode_id = uuid4()
        
        # Mock GCS client to be available
        mock_client = MagicMock()
        with patch('infrastructure.gcs._get_gcs_client') as mock_get_client:
            mock_get_client.return_value = mock_client
            
            # Mock upload_bytes to raise exception on first chunk
            with patch('infrastructure.gcs.upload_bytes') as mock_upload:
                mock_upload.side_effect = RuntimeError("Upload failed: network error")
                
                with pytest.raises(RuntimeError) as exc_info:
                    chunked_processor.split_audio_into_chunks(
                        audio_path=audio_path,
                        user_id=user_id,
                        episode_id=episode_id,
                    )
                
                assert "Failed to upload chunk" in str(exc_info.value)
                assert "Aborting chunking and falling back" in str(exc_info.value)
                
                # Verify that no chunks were created with None URIs
                # (The function should raise before creating any chunks)

