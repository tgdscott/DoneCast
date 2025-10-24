"""
Website section definitions API endpoint.

Lists available section types and their configuration schemas.
"""

from typing import List

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.services.website_sections import (
    SectionDefinition,
    SectionFieldDefinition,
    get_all_sections_sorted,
    get_sections_by_category,
    get_default_enabled_sections,
)


router = APIRouter(prefix="/website-sections", tags=["Website Sections"])


class SectionFieldResponse(BaseModel):
    """API response model for section field definitions."""
    
    name: str
    type: str
    label: str
    placeholder: str | None = None
    default: str | int | bool | List[str] | None = None  # Support list defaults for multiselect
    options: List[str] | None = None
    validation_pattern: str | None = None
    help_text: str | None = None
    required: bool = False


class SectionDefinitionResponse(BaseModel):
    """API response model for section definitions."""
    
    id: str
    label: str
    category: str
    icon: str
    description: str
    default_enabled: bool
    order_priority: int
    behavior: str | None = "normal"  # Layout behavior: sticky, fixed, normal
    required_fields: List[SectionFieldResponse]
    optional_fields: List[SectionFieldResponse]
    ai_prompt_hints: List[str]
    preview_image_url: str | None = None


def _serialize_section(section: SectionDefinition) -> SectionDefinitionResponse:
    """Convert SectionDefinition to API response model."""
    return SectionDefinitionResponse(
        id=section.id,
        label=section.label,
        category=section.category,
        icon=section.icon,
        description=section.description,
        default_enabled=section.default_enabled,
        order_priority=section.order_priority,
        behavior=section.behavior,
        required_fields=[
            SectionFieldResponse(**field.model_dump()) for field in section.required_fields
        ],
        optional_fields=[
            SectionFieldResponse(**field.model_dump()) for field in section.optional_fields
        ],
        ai_prompt_hints=section.ai_prompt_hints,
        preview_image_url=section.preview_image_url,
    )


@router.get("", response_model=List[SectionDefinitionResponse])
def list_sections(
    category: str | None = None,
    default_only: bool = False,
):
    """
    List available website section types.
    
    Query Parameters:
    - category: Filter by category (core, content, marketing, community, advanced)
    - default_only: If true, only return sections enabled by default
    """
    if default_only:
        sections = get_default_enabled_sections()
    elif category:
        sections = get_sections_by_category(category)
    else:
        sections = get_all_sections_sorted()
    
    return [_serialize_section(s) for s in sections]


@router.get("/categories", response_model=List[str])
def list_categories():
    """List all available section categories."""
    return ["layout", "core", "content", "marketing", "community", "advanced"]
