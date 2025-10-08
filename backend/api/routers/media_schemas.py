"""Compatibility layer re-exporting media schema definitions.

Historically the media endpoints lived in modules such as
``api.routers.media_read`` which imported ``MediaItemUpdate`` and
``MainContentItem`` from ``api.routers.media_schemas``.  The schemas are
defined in ``api.routers.media`` so we re-export them here for backwards
compatibility.
"""

from .media import MainContentItem, MediaItemUpdate

__all__ = ["MediaItemUpdate", "MainContentItem"]

