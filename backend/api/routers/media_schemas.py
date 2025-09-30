"""Compatibility layer re-exporting media schema definitions.

Historically the media endpoints lived in modules such as
``api.routers.media_read`` which imported ``MediaItemUpdate`` and
``MainContentItem`` from ``api.routers.media_schemas``.  The media router has
since been reorganized into the ``api.routers.media`` package where the shared
schemas now live in ``api.routers.media.schemas``.  To avoid breaking any
legacy imports that still reference the old module path we re-export the
definitions from their new location.
"""

from .media.schemas import MainContentItem, MediaItemUpdate

__all__ = ["MediaItemUpdate", "MainContentItem"]

