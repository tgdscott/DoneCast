"""
Test recovery of raw file transcripts from GCS after deployment.

This test simulates the scenario where:
1. Raw files have been uploaded and transcribed
2. MediaTranscript records exist in the database
3. Local transcript files are missing (simulating deployment)
4. Recovery function should download from GCS and restore locally
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime
from uuid import uuid4

from api.startup_tasks import _recover_raw_file_transcripts
from api.models.transcription import MediaTranscript


@pytest.fixture
def mock_transcript_records():
    """Create mock MediaTranscript records with GCS metadata."""
    return [
        MediaTranscript(
            id=uuid4(),
            filename="test-audio-1.mp3",
            transcript_meta_json='{"gcs_json": "gs://test-bucket/transcripts/test-audio-1.json", "bucket_stem": "test-audio-1"}',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ),
        MediaTranscript(
            id=uuid4(),
            filename="test-audio-2.mp3",
            transcript_meta_json='{"gcs_uri": "transcripts/test-audio-2.json", "safe_stem": "test-audio-2"}',
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ),
        MediaTranscript(
            id=uuid4(),
            filename="local-only.mp3",
            transcript_meta_json='{}',  # No GCS metadata (local dev file)
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        ),
    ]


def test_recover_raw_file_transcripts_basic(mock_transcript_records, tmp_path):
    """Test basic transcript recovery from GCS."""
    
    # Mock the session and query results
    with patch('api.startup_tasks.session_scope') as mock_session_scope, \
         patch('api.startup_tasks.TRANSCRIPTS_DIR', tmp_path), \
         patch('infrastructure.gcs.download_bytes') as mock_download:
        
        # Setup session mock
        mock_session = MagicMock()
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        # Mock query execution to return our test records
        mock_exec = MagicMock()
        mock_exec.all.return_value = mock_transcript_records[:2]  # Only GCS-backed records
        mock_session.exec.return_value = mock_exec
        
        # Mock GCS download to return fake transcript data
        mock_download.return_value = b'{"words": [{"text": "test", "start": 0.0, "end": 1.0}]}'
        
        # Run the recovery function
        _recover_raw_file_transcripts(limit=10)
        
        # Verify download was called for each record with GCS metadata
        assert mock_download.call_count == 2
        
        # Verify files were written to local storage
        assert (tmp_path / "test-audio-1.json").exists()
        assert (tmp_path / "test-audio-2.json").exists()


def test_recover_raw_file_transcripts_skip_existing(mock_transcript_records, tmp_path):
    """Test that recovery skips files that already exist locally."""
    
    # Pre-create one local transcript file
    (tmp_path / "test-audio-1.json").write_text('{"existing": true}')
    
    with patch('api.startup_tasks.session_scope') as mock_session_scope, \
         patch('api.startup_tasks.TRANSCRIPTS_DIR', tmp_path), \
         patch('infrastructure.gcs.download_bytes') as mock_download:
        
        mock_session = MagicMock()
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        mock_exec = MagicMock()
        mock_exec.all.return_value = mock_transcript_records[:2]
        mock_session.exec.return_value = mock_exec
        
        mock_download.return_value = b'{"words": []}'
        
        # Run recovery
        _recover_raw_file_transcripts(limit=10)
        
        # Should only download for test-audio-2 (test-audio-1 already exists)
        assert mock_download.call_count == 1
        
        # Verify existing file wasn't overwritten
        content = (tmp_path / "test-audio-1.json").read_text()
        assert '"existing": true' in content


def test_recover_raw_file_transcripts_gcs_failure(mock_transcript_records, tmp_path):
    """Test graceful handling of GCS download failures."""
    
    with patch('api.startup_tasks.session_scope') as mock_session_scope, \
         patch('api.startup_tasks.TRANSCRIPTS_DIR', tmp_path), \
         patch('infrastructure.gcs.download_bytes') as mock_download:
        
        mock_session = MagicMock()
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        mock_exec = MagicMock()
        mock_exec.all.return_value = [mock_transcript_records[0]]
        mock_session.exec.return_value = mock_exec
        
        # Simulate GCS download failure
        mock_download.side_effect = Exception("Network timeout")
        
        # Should not crash
        _recover_raw_file_transcripts(limit=10)
        
        # File should not exist (download failed)
        assert not (tmp_path / "test-audio-1.json").exists()


def test_recover_raw_file_transcripts_empty_database(tmp_path):
    """Test behavior when no MediaTranscript records exist."""
    
    with patch('api.startup_tasks.session_scope') as mock_session_scope, \
         patch('api.startup_tasks.TRANSCRIPTS_DIR', tmp_path), \
         patch('infrastructure.gcs.download_bytes') as mock_download:
        
        mock_session = MagicMock()
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        mock_exec = MagicMock()
        mock_exec.all.return_value = []  # No records
        mock_session.exec.return_value = mock_exec
        
        # Should complete without errors
        _recover_raw_file_transcripts(limit=10)
        
        # No downloads should occur
        mock_download.assert_not_called()


def test_recover_raw_file_transcripts_respects_limit():
    """Test that recovery respects the row limit parameter."""
    
    with patch('api.startup_tasks.session_scope') as mock_session_scope:
        mock_session = MagicMock()
        mock_session_scope.return_value.__enter__.return_value = mock_session
        
        mock_select = MagicMock()
        
        with patch('api.startup_tasks.select', return_value=mock_select):
            # Run with custom limit
            _recover_raw_file_transcripts(limit=50)
            
            # Verify limit was applied to query
            mock_select.limit.assert_called_once_with(50)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
