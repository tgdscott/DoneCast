# AI Theme Generator - Implementation Plan

## Overview

Combine AI-generated custom designs (like the Cinema IRL example in `test.html`) with the existing block-based website builder. The AI will analyze a podcast and automatically generate building blocks styled to match a custom, themed design.

## Goal

**Yes, we can absolutely make sites that look like the Cinema IRL example using building blocks automatically assembled by AI!**

The key insight: The `test.html` design is still built from standard sections (Hero, Episodes, Footer), but with:
- Custom CSS variables for theming
- Custom animations and effects
- Custom component styling
- Custom typography and color palettes

## Architecture

### Current State
- ✅ Block-based section system (`website_sections.py`)
- ✅ CSS generation from theme colors (`_generate_css_from_theme()`)
- ✅ AI CSS generation (`generate_css_with_ai()`)
- ✅ `global_css` field on `PodcastWebsite` model
- ✅ Visual editor with section configuration

### What We Need to Add

1. **AI Theme Analysis Service** - Analyzes podcast and generates design specifications
2. **Theme-to-Blocks Mapper** - Maps design specs to existing building blocks
3. **Enhanced CSS Generator** - Generates CSS that styles blocks to match the design
4. **Section Variant System** - Allows sections to have different visual styles

## Implementation Steps

### Phase 1: AI Theme Analysis

Create a new service that analyzes a podcast and generates a design specification:

```python
# backend/api/services/ai_theme_generator.py

def analyze_podcast_for_theme(podcast: Podcast, cover_url: str) -> ThemeSpec:
    """
    Analyze podcast metadata and cover art to generate a theme specification.
    
    Returns:
        ThemeSpec with:
        - color_palette: dict of CSS variable colors
        - typography: font choices for headings/body
        - visual_motifs: list of design elements (e.g., "marquee lights", "cinema tickets")
        - mood: overall vibe (e.g., "playful-cinematic", "professional", "cozy")
        - animations: list of animation types to include
        - component_styles: dict mapping section types to style variants
    """
```

**AI Prompt Template:**
```
You are a web design expert analyzing a podcast for theme generation.

Podcast Title: {podcast.name}
Description: {podcast.description}
Tagline: {tagline if available}
Cover Art: {description of cover art colors and imagery}

Analyze this podcast and generate a design theme specification in JSON format:

{
  "mood": "playful-cinematic-horror-comedy",
  "color_palette": {
    "primary": "#0f1220",
    "secondary": "#ffc107",
    "accent": "#56ccf2",
    "background": "#0f1220",
    "text": "#fff8e6",
    "danger": "#b71c1c"
  },
  "typography": {
    "heading_font": "Anton, Impact, sans-serif",
    "body_font": "Inter, system-ui, sans-serif",
    "heading_style": "uppercase, bold, letter-spacing: 0.5px"
  },
  "visual_motifs": [
    "retro-marquee-lights",
    "cinema-tickets",
    "theater-bulbs",
    "movie-posters"
  ],
  "animations": [
    "rotating-border-bulbs",
    "twinkling-lights",
    "spinning-saw-icon"
  ],
  "component_styles": {
    "hero": "marquee-frame-with-animated-border",
    "buttons": "ticket-style-with-perforations",
    "episode_cards": "movie-poster-style",
    "audio_player": "retro-cassette-style"
  },
  "effects": [
    "glowing-text-shadows",
    "gradient-overlays",
    "spotlight-backgrounds"
  ]
}

Output ONLY valid JSON, no explanations.
```

### Phase 2: Theme-to-Blocks Mapper

Map the theme specification to existing building blocks:

```python
def map_theme_to_sections(theme_spec: ThemeSpec) -> Dict[str, Dict]:
    """
    Map theme specification to section configurations.
    
    Returns:
        {
            "sections_order": ["hero", "latest-episodes", "footer"],
            "sections_config": {
                "hero": {
                    "variant": "marquee-style",  # New: section variants
                    "show_animated_border": True,
                    "background_style": "gradient-with-spotlight"
                },
                "latest-episodes": {
                    "variant": "movie-poster-cards",
                    "layout": "grid",
                    "card_style": "cinema-poster"
                }
            },
            "section_styles": {
                # Custom CSS classes for each section variant
            }
        }
    """
```

### Phase 3: Enhanced CSS Generator

Generate CSS that styles the blocks according to the theme:

```python
def generate_theme_css(theme_spec: ThemeSpec, section_configs: Dict) -> str:
    """
    Generate complete CSS that styles building blocks to match the theme.
    
    This CSS will:
    1. Define CSS variables from color palette
    2. Add typography rules
    3. Style section variants
    4. Include animations
    5. Add component-specific styles
    """
```

**Key Features:**
- CSS variables for all colors (like `test.html`)
- Section-specific styling (`.hero.marquee-style`, `.episode-card.movie-poster-style`)
- Animation keyframes
- Responsive breakpoints
- Accessibility considerations (contrast ratios, focus states)

### Phase 4: Section Variant System

Extend the section system to support visual variants:

```python
# backend/api/services/website_sections.py

class SectionDefinition(BaseModel):
    # ... existing fields ...
    variants: List[SectionVariant] = Field(default_factory=list)

class SectionVariant(BaseModel):
    id: str  # e.g., "marquee-style", "minimal", "cinema-poster"
    label: str
    description: str
    css_class: str  # Applied to section wrapper
    requires_fields: List[str] = []  # Additional config needed
```

**Example Variants:**
- Hero: `marquee-style`, `minimal`, `gradient-overlay`, `split-screen`
- Episodes: `movie-poster-cards`, `list-style`, `grid-minimal`, `cinema-tickets`
- Buttons: `ticket-style`, `neon-glow`, `minimal`, `gradient`

### Phase 5: Integration with Website Builder

Add a new "AI Theme Generator" button to the website builder:

```javascript
// frontend/src/components/dashboard/WebsiteBuilder.jsx

const handleGenerateAITheme = async () => {
  // 1. Call backend to analyze podcast and generate theme
  // 2. Apply theme to sections
  // 3. Generate and apply CSS
  // 4. Refresh preview
};
```

**User Flow:**
1. User clicks "Generate AI Theme" button
2. AI analyzes podcast (name, description, cover art, tone)
3. AI generates theme specification
4. System maps theme to building blocks
5. System generates custom CSS
6. Preview updates with new design
7. User can still edit sections manually if needed

## Example: Cinema IRL Theme Mapping

**Input:**
- Podcast: Cinema IRL
- Tagline: "What Would YOU Do?"
- Cover: Cartoon dinosaurs with chainsaws, popcorn, retro cinema vibe

**AI Analysis Output:**
```json
{
  "mood": "playful-cinematic-horror-comedy",
  "color_palette": {
    "bg": "#0f1220",
    "primary": "#ffc107",
    "accent": "#56ccf2",
    "danger": "#b71c1c"
  },
  "visual_motifs": ["marquee-lights", "cinema-tickets", "theater-bulbs"],
  "component_styles": {
    "hero": "marquee-frame",
    "buttons": "ticket-style",
    "episode_cards": "movie-poster"
  }
}
```

**Mapped to Blocks:**
- Hero section → `variant: "marquee-style"` with animated border
- Latest Episodes → `variant: "movie-poster-cards"` with grid layout
- Buttons → `variant: "ticket-style"` with perforated edges
- Footer → Decorative bulb row added

**Generated CSS:**
- CSS variables matching the color palette
- `.hero.marquee-style` with animated border
- `.btn.ticket-style` with perforations
- `.episode-card.movie-poster-style` with poster aesthetics
- Animations for bulbs, borders, etc.

## Technical Details

### Backend Endpoints

```python
# backend/api/routers/podcasts/websites.py

@router.post("/generate-ai-theme")
def generate_ai_theme(
    podcast_id: UUID,
    session: Session = Depends(get_session),
    current_user: User = Depends(get_current_user),
):
    """
    Analyze podcast and generate a complete themed design.
    
    Returns:
        {
            "theme_spec": {...},
            "sections_config": {...},
            "css": "...",
            "preview_url": "..."
        }
    """
```

### Frontend Components

```javascript
// frontend/src/components/website/AIThemeGenerator.jsx

export function AIThemeGenerator({ podcast, onThemeGenerated }) {
  // Shows preview of generated theme
  // Allows user to accept/reject
  // Shows what sections will be configured
}
```

### Database Schema

No schema changes needed! We can store:
- Theme spec in `sections_config` (as metadata)
- CSS in `global_css` (existing field)
- Section variants in `sections_config[section_id].variant`

## Benefits

1. **Best of Both Worlds**: Custom designs + maintainable building blocks
2. **Scalable**: Works for any podcast, not just Cinema IRL
3. **Editable**: Users can still modify sections after AI generation
4. **Consistent**: All sites use the same section system under the hood
5. **Accessible**: Building blocks ensure semantic HTML and accessibility

## Next Steps

1. ✅ Review and approve this plan
2. Implement `analyze_podcast_for_theme()` service
3. Implement `map_theme_to_sections()` mapper
4. Enhance `generate_theme_css()` to support variants
5. Add section variant definitions
6. Add "Generate AI Theme" UI to website builder
7. Test with Cinema IRL and other podcasts

## Success Criteria

- [ ] AI can generate a theme that looks similar to `test.html` for Cinema IRL
- [ ] Generated design uses existing building blocks
- [ ] User can still edit sections after AI generation
- [ ] Works for different podcast types (not just Cinema IRL)
- [ ] Generated CSS is clean, maintainable, and responsive
- [ ] Performance: Theme generation completes in < 10 seconds


