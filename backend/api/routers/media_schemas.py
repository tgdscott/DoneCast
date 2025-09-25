from pydantic import BaseModel
from typing import Optional


class MediaItemUpdate(BaseModel):
    friendly_name: Optional[str] = None
    trigger_keyword: Optional[str] = None

__all__ = ["MediaItemUpdate"]
