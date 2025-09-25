from datetime import time, timedelta
from typing import Optional
from pydantic import BaseModel, Field

class RecurringSchedule(BaseModel):
    id: Optional[str] = Field(default=None)
    user_id: str
    day_of_week: int  # 0=Monday, 6=Sunday
    time_of_day: time
    template_id: str
    podcast_id: Optional[str] = None
    title_prefix: Optional[str] = None
    description_prefix: Optional[str] = None
    enabled: bool = True
    advance_minutes: int = 60  # How far in advance to create the draft
    next_scheduled: Optional[str] = None  # ISO8601 string
