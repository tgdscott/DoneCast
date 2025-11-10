"""
Unit tests for ElevenLabs TTS billing rounding and metering.

Tests cover:
- Rounding behavior (3.2s → 4s, 0.1s → 1s)
- Batching behavior (sum durations, then ceil)
- Per-plan rates (Starter 15, Creator 14, Pro 13, Executive 12)
- Metadata structure (provider, raw_seconds, billed_seconds)
"""
import pytest
import math
from uuid import uuid4
from unittest.mock import Mock, patch, MagicMock

from sqlmodel import Session

from api.services.billing import credits
from api.models.user import User
from api.models.usage import ProcessingMinutesLedger, LedgerReason
from api.billing.plans import RATES_ELEVENLABS


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = Mock(spec=Session)
    session.add = Mock()
    session.commit = Mock()
    session.refresh = Mock()
    return session


@pytest.fixture
def starter_user():
    """Create a mock user with Starter tier."""
    user = Mock(spec=User)
    user.id = uuid4()
    user.tier = "starter"
    return user


@pytest.fixture
def creator_user():
    """Create a mock user with Creator tier."""
    user = Mock(spec=User)
    user.id = uuid4()
    user.tier = "creator"
    return user


@pytest.fixture
def pro_user():
    """Create a mock user with Pro tier."""
    user = Mock(spec=User)
    user.id = uuid4()
    user.tier = "pro"
    return user


@pytest.fixture
def executive_user():
    """Create a mock user with Executive tier."""
    user = Mock(spec=User)
    user.id = uuid4()
    user.tier = "executive"
    return user


class TestElevenLabsRounding:
    """Test rounding behavior for ElevenLabs TTS billing."""

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_rounding_3_2_seconds_to_4(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test that 3.2 seconds rounds up to 4 seconds."""
        # Arrange
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        # Act
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=starter_user,
            duration_seconds=3.2,
            use_elevenlabs=True
        )
        
        # Assert
        assert breakdown['raw_seconds'] == 3.2
        assert breakdown['billed_seconds'] == 4
        assert breakdown['provider'] == 'elevenlabs'
        assert breakdown['rate_per_sec'] == RATES_ELEVENLABS['starter']
        assert breakdown['total_credits'] == 4 * RATES_ELEVENLABS['starter']
        
        # Verify charge_credits was called with correct credits
        mock_charge_credits.assert_called_once()
        call_kwargs = mock_charge_credits.call_args[1]
        assert call_kwargs['credits'] == 4 * RATES_ELEVENLABS['starter']
        assert call_kwargs['reason'] == LedgerReason.TTS_GENERATION
        
        # Verify metadata structure
        cost_breakdown = call_kwargs['cost_breakdown']
        assert cost_breakdown['provider'] == 'elevenlabs'
        assert cost_breakdown['raw_seconds'] == 3.2
        assert cost_breakdown['billed_seconds'] == 4

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_rounding_0_1_seconds_to_1(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test that 0.1 seconds rounds up to 1 second (minimum billing)."""
        # Arrange
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        # Act
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=starter_user,
            duration_seconds=0.1,
            use_elevenlabs=True
        )
        
        # Assert
        assert breakdown['raw_seconds'] == 0.1
        assert breakdown['billed_seconds'] == 1  # Ceil(0.1) = 1
        assert breakdown['provider'] == 'elevenlabs'
        assert breakdown['total_credits'] == 1 * RATES_ELEVENLABS['starter']

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_exact_whole_seconds_no_rounding(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test that exact whole seconds don't round up."""
        # Arrange
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        # Act
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=starter_user,
            duration_seconds=5.0,
            use_elevenlabs=True
        )
        
        # Assert
        assert breakdown['raw_seconds'] == 5.0
        assert breakdown['billed_seconds'] == 5  # Ceil(5.0) = 5
        assert breakdown['total_credits'] == 5 * RATES_ELEVENLABS['starter']

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_standard_tts_no_rounding(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test that standard TTS (non-ElevenLabs) doesn't round."""
        # Arrange
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        # Act
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=starter_user,
            duration_seconds=3.2,
            use_elevenlabs=False
        )
        
        # Assert
        assert breakdown['raw_seconds'] == 3.2
        assert breakdown['billed_seconds'] == 3.2  # No rounding for standard
        assert breakdown['provider'] == 'standard'
        assert breakdown['rate_per_sec'] == 1
        assert breakdown['total_credits'] == 3.2


class TestElevenLabsBatching:
    """Test batching behavior: sum durations first, then ceil."""

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_batch_sums_then_ceils(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test that multiple clips are summed first, then rounded up."""
        # Arrange: [1.2s, 2.1s] = 3.3s total → 4s billed
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        # Act
        entry, breakdown = credits.charge_for_tts_batch(
            session=mock_session,
            user=starter_user,
            durations_seconds=[1.2, 2.1],
            use_elevenlabs=True
        )
        
        # Assert
        assert breakdown['raw_seconds'] == 3.3  # Sum of 1.2 + 2.1
        assert breakdown['billed_seconds'] == 4  # Ceil(3.3) = 4
        assert breakdown['clip_count'] == 2
        assert breakdown['total_credits'] == 4 * RATES_ELEVENLABS['starter']
        assert breakdown['durations'] == [1.2, 2.1]

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_batch_multiple_clips(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test batching with multiple clips."""
        # Arrange: [0.5s, 0.3s, 0.2s] = 1.0s total → 1s billed
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        # Act
        entry, breakdown = credits.charge_for_tts_batch(
            session=mock_session,
            user=starter_user,
            durations_seconds=[0.5, 0.3, 0.2],
            use_elevenlabs=True
        )
        
        # Assert
        assert breakdown['raw_seconds'] == 1.0
        assert breakdown['billed_seconds'] == 1  # Ceil(1.0) = 1
        assert breakdown['clip_count'] == 3

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_batch_rounds_after_sum(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test that rounding happens after summing, not per-clip."""
        # Arrange: [1.1s, 1.1s, 1.1s] = 3.3s total → 4s billed
        # NOT: ceil(1.1) + ceil(1.1) + ceil(1.1) = 2 + 2 + 2 = 6s
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        # Act
        entry, breakdown = credits.charge_for_tts_batch(
            session=mock_session,
            user=starter_user,
            durations_seconds=[1.1, 1.1, 1.1],
            use_elevenlabs=True
        )
        
        # Assert (use approximate comparison for floating point)
        assert abs(breakdown['raw_seconds'] - 3.3) < 0.0001
        assert breakdown['billed_seconds'] == 4  # Ceil(3.3) = 4, NOT 6
        assert breakdown['total_credits'] == 4 * RATES_ELEVENLABS['starter']

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_single_clip_via_batch_function(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test that charge_for_tts_generation uses batch function internally."""
        # Arrange
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        # Act
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=starter_user,
            duration_seconds=3.2,
            use_elevenlabs=True
        )
        
        # Assert - should have same behavior as batch with single item
        assert breakdown['raw_seconds'] == 3.2
        assert breakdown['billed_seconds'] == 4
        assert breakdown['clip_count'] == 1


class TestPerPlanRates:
    """Test per-plan ElevenLabs rates."""

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_starter_rate_15(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test Starter plan uses rate 15 credits/second."""
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=starter_user,
            duration_seconds=2.0,
            use_elevenlabs=True
        )
        
        assert breakdown['rate_per_sec'] == RATES_ELEVENLABS['starter']
        assert breakdown['rate_per_sec'] == 15
        assert breakdown['total_credits'] == 2 * 15

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_creator_rate_14(self, mock_wallet_debit, mock_charge_credits, mock_session, creator_user):
        """Test Creator plan uses rate 14 credits/second."""
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=creator_user,
            duration_seconds=2.0,
            use_elevenlabs=True
        )
        
        assert breakdown['rate_per_sec'] == RATES_ELEVENLABS['creator']
        assert breakdown['rate_per_sec'] == 14
        assert breakdown['total_credits'] == 2 * 14

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_pro_rate_13(self, mock_wallet_debit, mock_charge_credits, mock_session, pro_user):
        """Test Pro plan uses rate 13 credits/second."""
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=pro_user,
            duration_seconds=2.0,
            use_elevenlabs=True
        )
        
        assert breakdown['rate_per_sec'] == RATES_ELEVENLABS['pro']
        assert breakdown['rate_per_sec'] == 13
        assert breakdown['total_credits'] == 2 * 13

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_executive_rate_12(self, mock_wallet_debit, mock_charge_credits, mock_session, executive_user):
        """Test Executive plan uses rate 12 credits/second."""
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=executive_user,
            duration_seconds=2.0,
            use_elevenlabs=True
        )
        
        assert breakdown['rate_per_sec'] == RATES_ELEVENLABS['executive']
        assert breakdown['rate_per_sec'] == 12
        assert breakdown['total_credits'] == 2 * 12

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_unknown_tier_defaults_to_starter(self, mock_wallet_debit, mock_charge_credits, mock_session):
        """Test that unknown tier defaults to Starter rate."""
        user = Mock(spec=User)
        user.id = uuid4()
        user.tier = "unknown_tier"
        
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=user,
            duration_seconds=2.0,
            use_elevenlabs=True
        )
        
        # Should default to starter rate (15)
        assert breakdown['rate_per_sec'] == 15


class TestMetadataStructure:
    """Test that metadata includes required fields."""

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_metadata_includes_provider(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test that metadata includes 'provider' field."""
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=starter_user,
            duration_seconds=3.2,
            use_elevenlabs=True
        )
        
        assert 'provider' in breakdown
        assert breakdown['provider'] == 'elevenlabs'
        
        # Verify it's passed to charge_credits
        call_kwargs = mock_charge_credits.call_args[1]
        cost_breakdown = call_kwargs['cost_breakdown']
        assert cost_breakdown['provider'] == 'elevenlabs'

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_metadata_includes_raw_seconds(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test that metadata includes 'raw_seconds' field."""
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=starter_user,
            duration_seconds=3.2,
            use_elevenlabs=True
        )
        
        assert 'raw_seconds' in breakdown
        assert breakdown['raw_seconds'] == 3.2
        
        # Verify it's passed to charge_credits
        call_kwargs = mock_charge_credits.call_args[1]
        cost_breakdown = call_kwargs['cost_breakdown']
        assert cost_breakdown['raw_seconds'] == 3.2

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_metadata_includes_billed_seconds(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test that metadata includes 'billed_seconds' field."""
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=starter_user,
            duration_seconds=3.2,
            use_elevenlabs=True
        )
        
        assert 'billed_seconds' in breakdown
        assert breakdown['billed_seconds'] == 4
        
        # Verify it's passed to charge_credits
        call_kwargs = mock_charge_credits.call_args[1]
        cost_breakdown = call_kwargs['cost_breakdown']
        assert cost_breakdown['billed_seconds'] == 4

    @patch('api.services.billing.credits.charge_credits')
    @patch('api.services.billing.credits.wallet_debit')
    def test_metadata_complete_structure(self, mock_wallet_debit, mock_charge_credits, mock_session, starter_user):
        """Test that metadata has all required fields for ElevenLabs."""
        mock_entry = Mock(spec=ProcessingMinutesLedger)
        mock_charge_credits.return_value = mock_entry
        
        entry, breakdown = credits.charge_for_tts_generation(
            session=mock_session,
            user=starter_user,
            duration_seconds=3.2,
            use_elevenlabs=True
        )
        
        # Verify all required fields are present
        required_fields = ['provider', 'raw_seconds', 'billed_seconds', 'rate_per_sec', 'total_credits']
        for field in required_fields:
            assert field in breakdown, f"Missing required field: {field}"
        
        # Verify values
        assert breakdown['provider'] == 'elevenlabs'
        assert breakdown['raw_seconds'] == 3.2
        assert breakdown['billed_seconds'] == 4
        assert breakdown['rate_per_sec'] == RATES_ELEVENLABS['starter']
        assert breakdown['total_credits'] == 4 * RATES_ELEVENLABS['starter']
        
        # Verify it's passed to charge_credits with same structure
        call_kwargs = mock_charge_credits.call_args[1]
        cost_breakdown = call_kwargs['cost_breakdown']
        for field in required_fields:
            assert field in cost_breakdown, f"Missing field in cost_breakdown: {field}"
            assert cost_breakdown[field] == breakdown[field]

