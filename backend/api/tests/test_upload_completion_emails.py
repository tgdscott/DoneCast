"""Unit tests for upload completion email notifications and bug reporting."""

import json
from unittest.mock import Mock, patch, MagicMock
from uuid import uuid4

import pytest

from api.models.podcast import MediaItem, MediaCategory
from api.models.user import User
from api.models.assistant import FeedbackSubmission
from api.services.upload_completion_mailer import (
    send_upload_success_email,
    send_upload_failure_email,
    _format_quality_label,
    _format_processing_type,
    _strip_uuid_from_filename,
    _build_metrics_html,
)
from api.services.bug_reporter import (
    report_upload_failure,
    report_transcription_failure,
    report_assembly_failure,
    report_generic_error,
    _send_admin_bug_notification,
)


class TestUploadCompletionEmails:
    """Test upload completion email sending."""
    
    def test_send_upload_success_email_basic(self):
        """Test sending basic success email without metrics."""
        user = Mock(spec=User)
        user.id = uuid4()
        user.email = "test@example.com"
        
        media_item = Mock(spec=MediaItem)
        media_item.id = uuid4()
        media_item.friendly_name = "My Interview"
        media_item.filename = "gs://bucket/path/to/file.mp3"
        
        with patch("api.services.upload_completion_mailer.mailer") as mock_mailer:
            mock_mailer.send.return_value = True
            
            result = send_upload_success_email(
                user=user,
                media_item=media_item,
                quality_label="good",
                processing_type="standard",
            )
            
            assert result is True
            mock_mailer.send.assert_called_once()
            
            # Verify email contents
            call_args = mock_mailer.send.call_args
            assert call_args[1]["to"] == "test@example.com"
            assert "My Interview" in call_args[1]["subject"] or "My Interview" in call_args[1]["text"]
    
    def test_send_upload_success_email_with_metrics(self):
        """Test sending success email with audio quality metrics."""
        user = Mock(spec=User)
        user.id = uuid4()
        user.email = "test@example.com"
        
        media_item = Mock(spec=MediaItem)
        media_item.id = uuid4()
        media_item.friendly_name = "Podcast Episode"
        media_item.filename = "gs://bucket/episode.mp3"
        
        metrics = {
            "loudness_lufs": -18.5,
            "loudness_max": -3.2,
            "duration_seconds": 3600,
            "sample_rate": 44100,
        }
        
        with patch("api.services.upload_completion_mailer.mailer") as mock_mailer:
            mock_mailer.send.return_value = True
            
            result = send_upload_success_email(
                user=user,
                media_item=media_item,
                quality_label="good",
                processing_type="advanced",
                audio_quality_metrics=metrics,
            )
            
            assert result is True
            mock_mailer.send.assert_called_once()
    
    def test_send_upload_failure_email(self):
        """Test sending upload failure email with bug report confirmation."""
        user = Mock(spec=User)
        user.id = uuid4()
        user.email = "test@example.com"
        
        with patch("api.services.upload_completion_mailer.mailer") as mock_mailer:
            mock_mailer.send.return_value = True
            
            result = send_upload_failure_email(
                user=user,
                filename="test_audio.mp3",
                error_message="File size exceeds limit",
                error_code="SIZE_LIMIT_EXCEEDED",
                request_id="req-12345",
            )
            
            assert result is True
            mock_mailer.send.assert_called_once()
            
            # Verify bug report mention in email
            call_args = mock_mailer.send.call_args
            email_body = call_args[1]["text"]
            assert "automatically reported" in email_body.lower() or "bug report" in email_body.lower()
    
    def test_send_upload_failure_no_email(self):
        """Test failure email when user has no email address."""
        user = Mock(spec=User)
        user.id = uuid4()
        user.email = None
        
        result = send_upload_failure_email(
            user=user,
            filename="test.mp3",
            error_message="Test error",
        )
        
        assert result is False
    
    def test_format_quality_label(self):
        """Test quality label formatting."""
        assert "Good" in _format_quality_label("good")
        assert "🟢" in _format_quality_label("good")
        
        assert "Fair" in _format_quality_label("slightly_bad")
        assert "🟡" in _format_quality_label("slightly_bad")
        
        assert "Poor" in _format_quality_label("incredibly_bad")
        assert "🔴" in _format_quality_label("incredibly_bad")
        
        assert "Unknown" in _format_quality_label(None)
        assert "Unknown" in _format_quality_label("")
    
    def test_format_processing_type(self):
        """Test processing type formatting."""
        assert "Advanced" in _format_processing_type("advanced")
        assert "🎚️" in _format_processing_type("advanced")
        
        assert "Standard" in _format_processing_type("standard")
        assert "📝" in _format_processing_type("standard")
        
        assert "Auphonic" in _format_processing_type("auphonic")
        assert "AssemblyAI" in _format_processing_type("assemblyai")
        
        assert "Standard" in _format_processing_type(None)
    
    def test_strip_uuid_from_filename(self):
        """Test UUID stripping from filenames."""
        # Standard UUID pattern
        uuid_filename = "550e8400-e29b-41d4-a716-446655440000_MyAudio.mp3"
        result = _strip_uuid_from_filename(uuid_filename)
        assert result == "MyAudio.mp3"
        assert "550e8400" not in result
        
        # Hex pattern
        hex_filename = "abc123def456_MyPodcast.mp3"
        result = _strip_uuid_from_filename(hex_filename)
        assert result == "MyPodcast.mp3"
        
        # GCS path
        gcs_filename = "gs://bucket/path/550e8400-e29b-41d4-a716-446655440000_Interview.mp3"
        result = _strip_uuid_from_filename(gcs_filename)
        assert result == "Interview.mp3"
        
        # No UUID
        normal_filename = "SimpleAudio.mp3"
        result = _strip_uuid_from_filename(normal_filename)
        assert result == "SimpleAudio.mp3"
    
    def test_build_metrics_html(self):
        """Test HTML metrics building."""
        metrics = {
            "loudness_lufs": -18.5,
            "loudness_max": -3.2,
            "duration_seconds": 3600,
            "sample_rate": 44100,
        }
        
        html = _build_metrics_html(metrics)
        assert "-18.5" in html
        assert "60:00" in html  # Duration formatted
        assert "44100" in html
        
        # Test with empty metrics
        html_empty = _build_metrics_html(None)
        assert html_empty == ""
        
        # Test with partial metrics
        partial_metrics = {"loudness_lufs": -20}
        html_partial = _build_metrics_html(partial_metrics)
        assert "-20" in html_partial


class TestBugReporting:
    """Test automatic bug report submission."""
    
    def test_report_upload_failure(self):
        """Test reporting upload failure as bug."""
        session = Mock()
        user = Mock(spec=User)
        user.id = uuid4()
        user.email = "user@example.com"
        
        with patch("api.services.bug_reporter.FeedbackSubmission") as MockFeedback:
            mock_feedback = Mock(spec=FeedbackSubmission)
            mock_feedback.id = uuid4()
            MockFeedback.return_value = mock_feedback
            
            with patch("api.services.bug_reporter._send_admin_bug_notification") as mock_send:
                result = report_upload_failure(
                    session=session,
                    user=user,
                    filename="test.mp3",
                    error_message="GCS upload failed",
                    error_code="GCS_ERROR",
                    request_id="req-123",
                )
                
                assert result == mock_feedback.id
                session.add.assert_called()
                session.commit.assert_called()
    
    def test_report_transcription_failure(self):
        """Test reporting transcription failure as bug."""
        session = Mock()
        user = Mock(spec=User)
        user.id = uuid4()
        user.email = "user@example.com"
        
        with patch("api.services.bug_reporter.FeedbackSubmission") as MockFeedback:
            mock_feedback = Mock(spec=FeedbackSubmission)
            mock_feedback.id = uuid4()
            MockFeedback.return_value = mock_feedback
            
            result = report_transcription_failure(
                session=session,
                user=user,
                media_filename="audio.mp3",
                transcription_service="AssemblyAI",
                error_message="API timeout",
                request_id="req-456",
            )
            
            assert result == mock_feedback.id
            session.add.assert_called()
    
    def test_report_assembly_failure(self):
        """Test reporting assembly failure as bug."""
        session = Mock()
        user = Mock(spec=User)
        user.id = uuid4()
        user.email = "user@example.com"
        
        with patch("api.services.bug_reporter.FeedbackSubmission") as MockFeedback:
            mock_feedback = Mock(spec=FeedbackSubmission)
            mock_feedback.id = uuid4()
            MockFeedback.return_value = mock_feedback
            
            result = report_assembly_failure(
                session=session,
                user=user,
                episode_title="Episode 42",
                error_message="Audio mixing failed",
                request_id="req-789",
            )
            
            assert result == mock_feedback.id
    
    def test_report_generic_error(self):
        """Test reporting generic error as bug."""
        session = Mock()
        user = Mock(spec=User)
        user.id = uuid4()
        user.email = "user@example.com"
        
        with patch("api.services.bug_reporter.FeedbackSubmission") as MockFeedback:
            mock_feedback = Mock(spec=FeedbackSubmission)
            mock_feedback.id = uuid4()
            MockFeedback.return_value = mock_feedback
            
            result = report_generic_error(
                session=session,
                user=user,
                error_category="database",
                error_message="Connection pool exhausted",
                error_code="DB_POOL_EXHAUSTED",
            )
            
            assert result == mock_feedback.id
    
    def test_report_error_without_user(self):
        """Test that error reporting fails gracefully without user."""
        session = Mock()
        
        result = report_generic_error(
            session=session,
            user=None,
            error_category="test",
            error_message="Test error",
        )
        
        assert result is None
    
    def test_send_admin_bug_notification(self):
        """Test admin notification email sending."""
        feedback = Mock(spec=FeedbackSubmission)
        feedback.id = uuid4()
        feedback.severity = "critical"
        feedback.type = "bug"
        feedback.title = "Upload failed"
        feedback.description = "Test description"
        feedback.category = "upload"
        feedback.error_logs = '{"error": "test"}'
        feedback.created_at = Mock()
        
        user = Mock(spec=User)
        user.id = uuid4()
        user.email = "user@example.com"
        
        with patch("api.services.bug_reporter.settings") as mock_settings:
            mock_settings.ADMIN_EMAIL = "admin@example.com"
            
            with patch("api.services.bug_reporter.mailer") as mock_mailer:
                mock_mailer.send.return_value = True
                
                result = _send_admin_bug_notification(feedback, user, Mock())
                
                assert result is True
                mock_mailer.send.assert_called_once()
                
                # Verify email contents
                call_args = mock_mailer.send.call_args
                assert call_args[1]["to"] == "admin@example.com"
                assert "CRITICAL" in call_args[1]["subject"]


class TestIntegration:
    """Integration tests for upload → email → bug reporting flow."""
    
    def test_upload_success_flow(self):
        """Test complete success flow: upload → email."""
        user = Mock(spec=User)
        user.id = uuid4()
        user.email = "user@example.com"
        
        media_item = Mock(spec=MediaItem)
        media_item.id = uuid4()
        media_item.friendly_name = "Test Audio"
        media_item.filename = "gs://bucket/audio.mp3"
        media_item.audio_quality_label = "good"
        media_item.use_auphonic = False
        media_item.audio_quality_metrics_json = json.dumps({
            "loudness_lufs": -18,
            "duration_seconds": 1800,
        })
        
        with patch("api.services.upload_completion_mailer.mailer") as mock_mailer:
            mock_mailer.send.return_value = True
            
            result = send_upload_success_email(
                user=user,
                media_item=media_item,
                quality_label="good",
                processing_type="standard",
                audio_quality_metrics=json.loads(media_item.audio_quality_metrics_json),
            )
            
            assert result is True
    
    def test_upload_failure_flow(self):
        """Test complete failure flow: upload error → bug report → email."""
        session = Mock()
        user = Mock(spec=User)
        user.id = uuid4()
        user.email = "user@example.com"
        
        # Report bug
        with patch("api.services.bug_reporter.FeedbackSubmission") as MockFeedback:
            mock_feedback = Mock(spec=FeedbackSubmission)
            mock_feedback.id = uuid4()
            MockFeedback.return_value = mock_feedback
            
            bug_id = report_upload_failure(
                session=session,
                user=user,
                filename="test.mp3",
                error_message="GCS upload failed",
                error_code="GCS_ERROR",
            )
            
            assert bug_id is not None
        
        # Send failure email
        with patch("api.services.upload_completion_mailer.mailer") as mock_mailer:
            mock_mailer.send.return_value = True
            
            email_result = send_upload_failure_email(
                user=user,
                filename="test.mp3",
                error_message="GCS upload failed",
                error_code="GCS_ERROR",
                request_id=str(bug_id),
            )
            
            assert email_result is True
            
            # Verify reference ID in email
            call_args = mock_mailer.send.call_args
            email_text = call_args[1]["text"]
            assert str(bug_id) in email_text or "GCS_ERROR" in email_text


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
