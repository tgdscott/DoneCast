from typing import Protocol, runtime_checkable, List, Optional
from datetime import datetime

# Import real models from the project structure
from backend.api.models.transcription import TranscriptionWatch
from backend.api.models.media import MediaItem
from backend.api.models.subscription import Subscription

@runtime_checkable
class ITranscriptionService(Protocol):
    """
    Interface for any transcription provider (e.g., AssemblyAI, Deepgram).
    """
    def submit_job(self, audio_url: str, user_id: str) -> TranscriptionWatch:
        """Starts a new transcription job."""
        ...

    def check_status(self, job_id: str) -> TranscriptionWatch:
        """Retrieves the current status of a job."""
        ...

    def get_transcript(self, job_id: str) -> str:
        """Fetches the final transcript text."""
        ...

@runtime_checkable
class IBillingService(Protocol):
    """
    Interface for a payment provider (e.g., Stripe, PayPal).
    """
    def create_customer(self, user_email: str) -> str:
        """Creates a customer record in the billing system and returns the ID."""
        ...

    def get_subscription_status(self, customer_id: str) -> Subscription:
        """Returns the current subscription details."""
        ...

    def create_subscription(self, customer_id: str, plan_id: str) -> Subscription:
        """Creates a new subscription for the customer."""
        ...

@runtime_checkable
class IStorageBackend(Protocol):
    """
    Interface for abstracting file storage (e.g., GCS, S3, local disk).
    """
    def upload_file(self, local_path: str, remote_path: str) -> MediaItem:
        """Uploads a local file to the remote storage and returns metadata."""
        ...

    def download_file(self, remote_path: str, local_path: str) -> bool:
        """Downloads a remote file to a local path."""
        ...

    def list_files(self, prefix: str) -> List[MediaItem]:
        """Lists files within a given remote path prefix."""
        ...