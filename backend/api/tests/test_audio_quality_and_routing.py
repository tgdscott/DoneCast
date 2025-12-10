"""Unit tests for audio quality analyzer and Auphonic decision helper.

Tests cover:
- Audio quality metrics computation (LUFS, SNR, dnsmos proxy)
- Quality label assignment (good → abysmal)
- Decision helper with matrix, tier, and operator overrides
- Edge cases and fallback behavior
"""
import json
import pytest
from unittest.mock import Mock, patch, MagicMock


class TestAudioQualityAnalyzer:
    """Test audio quality analyzer metrics and label assignment."""

    def test_analyze_audio_file_returns_metrics_dict(self):
        """Analyzer should return dict with quality_label and metrics."""
        from api.services.audio.quality import analyze_audio_file

        # Mock GCS download and ffmpeg calls
        with patch('api.services.audio.quality.gcs_client') as mock_gcs, \
             patch('api.services.audio.quality.subprocess.run') as mock_run:
            
            # Mock GCS download
            mock_gcs.download_blob.return_value = b'mock_audio_data'
            
            # Mock ffprobe output (duration)
            ffprobe_result = Mock()
            ffprobe_result.stdout = '{"format": {"duration": "60.5"}}'
            
            # Mock ffmpeg ebur128 output
            ebur128_result = Mock()
            ebur128_result.stderr = (
                '[Parsed_ebur128_0 @ 0x123] "LUFS": -20.0, "LU": 0.5'
            )
            
            # Mock ffmpeg volumedetect output
            volumedetect_result = Mock()
            volumedetect_result.stderr = (
                'n_samples: 2646000 \n'
                'mean_volume: -25.0 dB \n'
                'max_volume: -5.0 dB \n'
                'histogram_1db: 0, 0, 0 \n'
                'histogram_0.1db: 0, 0, 0 \n'
            )
            
            mock_run.side_effect = [ffprobe_result, ebur128_result, volumedetect_result]
            
            result = analyze_audio_file('gs://bucket/test.mp3')
            
            assert isinstance(result, dict)
            assert 'quality_label' in result
            assert result['quality_label'] in [
                'good', 'slightly_bad', 'fairly_bad', 'very_bad',
                'incredibly_bad', 'abysmal', 'unknown'
            ]
            assert 'lufs' in result or 'duration' in result or 'error' in result

    def test_quality_label_assignment_good_audio(self):
        """Audio with LUFS -18 to -23 and high level should be 'good'."""
        from api.services.audio.quality import analyze_audio_file

        with patch('api.services.audio.quality.gcs_client') as mock_gcs, \
             patch('api.services.audio.quality.subprocess.run') as mock_run:
            
            mock_gcs.download_blob.return_value = b'mock'
            
            ffprobe_result = Mock(stdout='{"format": {"duration": "60.0"}}')
            ebur128_result = Mock(stderr='[Parsed_ebur128_0 @ 0x123] "LUFS": -20.0')
            volumedetect_result = Mock(stderr='max_volume: -8.0 dB')
            
            mock_run.side_effect = [ffprobe_result, ebur128_result, volumedetect_result]
            
            result = analyze_audio_file('gs://bucket/test.mp3')
            
            # Good audio should produce good label
            assert result.get('quality_label') in ['good', 'slightly_bad']

    def test_quality_label_assignment_abysmal_audio(self):
        """Audio with very low LUFS and peak should be 'abysmal'."""
        from api.services.audio.quality import analyze_audio_file

        with patch('api.services.audio.quality.gcs_client') as mock_gcs, \
             patch('api.services.audio.quality.subprocess.run') as mock_run:
            
            mock_gcs.download_blob.return_value = b'mock'
            
            ffprobe_result = Mock(stdout='{"format": {"duration": "60.0"}}')
            ebur128_result = Mock(stderr='[Parsed_ebur128_0 @ 0x123] "LUFS": -40.0')
            volumedetect_result = Mock(stderr='max_volume: -35.0 dB')
            
            mock_run.side_effect = [ffprobe_result, ebur128_result, volumedetect_result]
            
            result = analyze_audio_file('gs://bucket/test.mp3')
            
            # Very bad audio should produce abysmal label
            assert result.get('quality_label') in ['abysmal', 'incredibly_bad']

    def test_analyze_audio_file_with_missing_gcs_file(self):
        """Analyzer should gracefully handle missing GCS files."""
        from api.services.audio.quality import analyze_audio_file

        with patch('api.services.audio.quality.gcs_client') as mock_gcs:
            mock_gcs.download_blob.side_effect = Exception("404: Not found")
            
            result = analyze_audio_file('gs://bucket/missing.mp3')
            
            assert isinstance(result, dict)
            # Should return unknown or fallback metrics
            assert result.get('quality_label') in ['unknown', None] or 'error' in result


class TestAuphionicDecisionHelper:
    """Test audio processing decision logic with priority ordering."""

    def test_explicit_override_takes_precedence(self):
        """Explicit media-level override should override all other logic."""
        from api.services.auphonic_helper import decide_audio_processing

        result = decide_audio_processing(
            audio_quality_label='abysmal',  # Would normally trigger advanced
            current_user_tier='free',  # Free tier would normally be standard
            media_item_override_use_auphonic=False  # Explicit: don't use
        )
        
        assert result['use_auphonic'] is False
        assert result['decision'] == 'standard'
        assert result['reason'] == 'explicit_media_override'

    def test_explicit_override_force_auphonic(self):
        """Explicit True override should force Auphonic."""
        from api.services.auphonic_helper import decide_audio_processing

        result = decide_audio_processing(
            audio_quality_label='good',
            current_user_tier='free',
            media_item_override_use_auphonic=True
        )
        
        assert result['use_auphonic'] is True
        assert result['decision'] == 'advanced'
        assert result['reason'] == 'explicit_media_override'

    def test_pro_tier_always_auphonic(self):
        """Pro tier should always use Auphonic regardless of quality."""
        from api.services.auphonic_helper import decide_audio_processing

        result = decide_audio_processing(
            audio_quality_label='good',
            current_user_tier='pro',
            media_item_override_use_auphonic=None
        )
        
        assert result['use_auphonic'] is True
        assert result['decision'] == 'advanced'
        assert result['reason'] == 'pro_tier'

    def test_decision_matrix_bad_audio_uses_advanced(self):
        """Bad quality audio should use Auphonic (advanced)."""
        from api.services.auphonic_helper import decide_audio_processing

        for label in ['slightly_bad', 'fairly_bad', 'very_bad', 'incredibly_bad', 'abysmal']:
            result = decide_audio_processing(
                audio_quality_label=label,
                current_user_tier='free',
                media_item_override_use_auphonic=None
            )
            
            assert result['use_auphonic'] is True, f"Label {label} should use Auphonic"
            assert result['decision'] == 'advanced', f"Label {label} should be advanced"
            assert 'matrix:' in result['reason']

    def test_decision_matrix_good_audio_uses_standard(self):
        """Good quality audio should use standard (AssemblyAI)."""
        from api.services.auphonic_helper import decide_audio_processing

        result = decide_audio_processing(
            audio_quality_label='good',
            current_user_tier='free',
            media_item_override_use_auphonic=None
        )
        
        assert result['use_auphonic'] is False
        assert result['decision'] == 'standard'
        assert 'matrix:' in result['reason']

    def test_decision_matrix_unknown_label_uses_default(self):
        """Unknown label should fall back to default conservative."""
        from api.services.auphonic_helper import decide_audio_processing

        result = decide_audio_processing(
            audio_quality_label='unknown',
            current_user_tier='free',
            media_item_override_use_auphonic=None
        )
        
        assert result['use_auphonic'] is False
        assert result['decision'] == 'standard'
        assert result['reason'] == 'default_fallback'

    def test_priority_ordering(self):
        """Priority should be: explicit > pro_tier > matrix > default."""
        from api.services.auphonic_helper import decide_audio_processing

        # Explicit wins
        result = decide_audio_processing(
            audio_quality_label='good',
            current_user_tier='pro',
            media_item_override_use_auphonic=False
        )
        assert result['reason'] == 'explicit_media_override'

        # Pro tier wins over matrix
        result = decide_audio_processing(
            audio_quality_label='good',
            current_user_tier='pro',
            media_item_override_use_auphonic=None
        )
        assert result['reason'] == 'pro_tier'

        # Matrix wins over default
        result = decide_audio_processing(
            audio_quality_label='abysmal',
            current_user_tier='free',
            media_item_override_use_auphonic=None
        )
        assert 'matrix:' in result['reason']

    def test_case_insensitive_tier_matching(self):
        """Tier matching should be case-insensitive."""
        from api.services.auphonic_helper import decide_audio_processing

        for tier_variant in ['PRO', 'Pro', 'pRo']:
            result = decide_audio_processing(
                audio_quality_label='good',
                current_user_tier=tier_variant,
                media_item_override_use_auphonic=None
            )
            
            assert result['use_auphonic'] is True
            assert result['reason'] == 'pro_tier'

    def test_should_use_auphonic_for_media_wrapper(self):
        """Wrapper function should return boolean only."""
        from api.services.auphonic_helper import should_use_auphonic_for_media

        result = should_use_auphonic_for_media(
            audio_quality_label='abysmal',
            current_user_tier='free'
        )
        
        assert isinstance(result, bool)
        assert result is True  # abysmal should use Auphonic

    def test_none_parameters_handling(self):
        """Should handle None values gracefully."""
        from api.services.auphonic_helper import decide_audio_processing

        result = decide_audio_processing(
            audio_quality_label=None,
            current_user_tier=None,
            media_item_override_use_auphonic=None
        )
        
        assert result['use_auphonic'] is False
        assert result['reason'] == 'default_fallback'


class TestIntegrationAudioQualityRouting:
    """Integration tests for quality → decision → routing pipeline."""

    def test_full_pipeline_good_audio_free_tier(self):
        """Good audio + free tier should → AssemblyAI."""
        from api.services.auphonic_helper import decide_audio_processing

        # Simulate good quality audio upload by free tier user
        metrics = {'quality_label': 'good', 'lufs': -19.5, 'max_db': -8.0}
        quality_label = metrics['quality_label']

        result = decide_audio_processing(
            audio_quality_label=quality_label,
            current_user_tier='free',
            media_item_override_use_auphonic=None
        )

        # Should use standard (AssemblyAI)
        assert result['use_auphonic'] is False
        assert result['decision'] == 'standard'

    def test_full_pipeline_bad_audio_free_tier(self):
        """Bad audio + free tier should → Auphonic (advanced)."""
        from api.services.auphonic_helper import decide_audio_processing

        # Simulate bad quality audio upload by free tier user
        metrics = {'quality_label': 'very_bad', 'lufs': -35.0, 'max_db': -25.0}
        quality_label = metrics['quality_label']

        result = decide_audio_processing(
            audio_quality_label=quality_label,
            current_user_tier='free',
            media_item_override_use_auphonic=None
        )

        # Should use advanced (Auphonic) despite free tier
        assert result['use_auphonic'] is True
        assert result['decision'] == 'advanced'

    def test_full_pipeline_pro_tier_always_auphonic(self):
        """Pro tier should always use Auphonic regardless of quality."""
        from api.services.auphonic_helper import decide_audio_processing

        for quality_label in ['good', 'abysmal', 'unknown']:
            result = decide_audio_processing(
                audio_quality_label=quality_label,
                current_user_tier='pro',
                media_item_override_use_auphonic=None
            )

            # Pro tier always uses Auphonic
            assert result['use_auphonic'] is True
            assert result['decision'] == 'advanced'


# Run tests with pytest
if __name__ == '__main__':
    pytest.main([__file__, '-v'])
