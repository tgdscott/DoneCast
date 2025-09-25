from typing import Any, Dict, List, Optional, Union, Literal, Annotated
from datetime import datetime
import enum

try:
    from pydantic import BaseModel, Field, ConfigDict
except Exception:  # pragma: no cover
    from pydantic import BaseModel, Field  # type: ignore
    ConfigDict = dict  # type: ignore

__all__: List[str] = []
