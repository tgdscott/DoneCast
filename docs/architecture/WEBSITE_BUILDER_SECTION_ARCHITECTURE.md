# Website Builder - Section-Based Architecture

**Created:** October 15, 2025  
**Status:** Design & Implementation Plan

## Overview

Transform the website builder from pure AI-generated layouts to a **structured section-based approach** with drag-and-drop configuration, followed by AI refinement for polish and personalization.

### Core Philosophy

1. **Start with Structure** - Users build their site by selecting and arranging pre-defined sections
2. **Visual Configuration** - Drag-and-drop reordering, toggle sections on/off, configure section-specific options
3. **AI for Refinement** - Once structure is set, use AI to refine copy, adjust styling, and personalize content
4. **Non-Technical Friendly** - Visual builders are more intuitive than chat-based AI for non-technical users

## Essential Website Sections

### Tier 1: Required Sections (Always Included)
These form the backbone of every podcast website:

1. **Hero Section**
   - Large header with podcast name, tagline, cover art
   - Primary CTA button (Subscribe, Latest Episode, etc.)
   - Background color/image customization
   - **Config:** Title, subtitle, CTA text, CTA link, background style

2. **About Section**
   - Overview of the podcast concept
   - Target audience statement
   - Show format and schedule
   - **Config:** Heading, body text (markdown), optional image

3. **Latest Episodes**
   - Display recent episodes (3-5) with play buttons
   - Episode titles, descriptions, publish dates
   - Links to full episode pages or audio players
   - **Config:** Number of episodes to show, layout style (list/grid/cards)

4. **Subscribe Section**
   - Links to Apple Podcasts, Spotify, RSS feed, etc.
   - Platform icons with direct links
   - QR code option for mobile subscriptions
   - **Config:** Platform selection, custom links, show/hide RSS

### Tier 2: Recommended Sections (Enabled by Default)
High-value sections most podcasts benefit from:

5. **Meet the Hosts**
   - Host names, photos, bios
   - Social media links per host
   - **Config:** Add/edit hosts, photo uploads, bio text, social links

6. **Newsletter Sign-Up**
   - Email capture form
   - Value proposition for subscribers
   - Privacy policy link
   - **Config:** Form service integration, heading, description, button text

7. **Listener Testimonials**
   - Quotes from reviews/listeners
   - Star ratings, reviewer names
   - Pull from Apple Podcasts/Spotify if available
   - **Config:** Add manual testimonials, select review sources

8. **Call-to-Action (Support)**
   - Patreon, Buy Me a Coffee, merch store links
   - Sponsorship inquiry contact
   - **Config:** CTA type, heading, body, button label/link

### Tier 3: Optional Sections (User-Selected)
Sections for specific use cases:

9. **Events Calendar**
   - Upcoming live shows, watch parties, AMAs
   - Date, time, location, ticket links
   - **Config:** Add/edit events, date pickers, location/virtual toggle

10. **Community Highlights**
    - Fan art, social media embeds
    - Listener shout-outs
    - **Config:** Upload images, add social embeds, text blocks

11. **Press & Media**
    - Notable press mentions
    - Media kit download
    - Contact for interviews
    - **Config:** Add press items (outlet, headline, link, date)

12. **Sponsors Showcase**
    - Current sponsor logos and descriptions
    - Thank you messages
    - Sponsorship inquiry CTA
    - **Config:** Add sponsors (logo, name, link, description)

13. **Resource Library**
    - Episode companion guides
    - Templates, worksheets, downloads
    - Links to mentioned products/services
    - **Config:** Add resources (title, description, file/link)

14. **FAQ**
    - Common questions about the show
    - Accordion-style Q&A
    - **Config:** Add Q&A pairs

15. **Contact Form**
    - Guest pitch, feedback, general inquiries
    - Form fields customization
    - **Config:** Form service, custom fields, success message

16. **Transcript Archive**
    - Searchable episode transcripts
    - SEO value for content discoverability
    - **Config:** Enable/disable, search settings

17. **Social Media Feed**
    - Embedded Twitter/Instagram/TikTok feed
    - Show latest social posts
    - **Config:** Platform selection, handle/account, number of posts

18. **Behind the Scenes**
    - Production notes, outtakes, bonus content
    - Exclusive content teasers
    - **Config:** Add content blocks (text, images, videos)

## Section Metadata Structure

Each section type includes:

```typescript
interface SectionDefinition {
  id: string;                    // unique identifier (e.g., "hero", "latest-episodes")
  label: string;                 // display name in UI
  category: 'core' | 'content' | 'marketing' | 'community' | 'advanced';
  icon: string;                  // lucide-react icon name
  description: string;           // short explanation of purpose
  defaultEnabled: boolean;       // pre-selected in wizard
  requiredFields: Field[];       // config fields that must be set
  optionalFields: Field[];       // additional customization options
  previewComponent: React.Component;  // render preview in editor
  aiPromptHints: string[];       // guide AI when refining this section
}

interface Field {
  name: string;
  type: 'text' | 'textarea' | 'url' | 'image' | 'select' | 'multiselect' | 'toggle';
  label: string;
  placeholder?: string;
  options?: string[];            // for select fields
  validation?: RegExp | Function;
}
```

## User Workflow

### Phase 1: Guided Setup Wizard (New Approach)

**Step 1: Choose Your Focus**
- What's the primary goal of your website?
  - [ ] Get more subscribers
  - [ ] Build community
  - [ ] Monetize/sponsorships
  - [ ] Showcase expertise
  
Based on selection, recommend section package

**Step 2: Select Sections**
- Visual gallery of section cards with previews
- Tier 1 sections (required) shown as locked/enabled
- Tier 2 sections (recommended) pre-checked
- Tier 3 sections with "Add" buttons
- Live preview updates as sections selected

**Step 3: Configure Essentials**
- Hero: Title, tagline, CTA
- About: Quick description
- Subscribe: Platform links
- Hosts: Names and bios (quick version)

**Step 4: Review & Generate**
- Show section order preview
- Generate initial site with basic content
- Proceed to editor for refinement

### Phase 2: Visual Editor

**Section Palette (Left Sidebar)**
- Categorized sections: Core, Content, Marketing, Community
- Drag sections from palette to canvas
- Icons and labels for each section type

**Canvas (Center)**
- Live preview of website
- Drag handles on each section for reordering
- Section controls: Edit (modal), Disable/Enable, Duplicate, Delete
- Visual indicators for section state (enabled, disabled, needs-config)

**Properties Panel (Right Sidebar)**
- Selected section configuration
- Form fields based on section type
- Real-time preview updates
- "AI Refine" button per section

**AI Chat Panel (Bottom)**
- Context-aware refinements
- "Make the hero more energetic"
- "Add testimonials from my Apple Podcasts reviews"
- "Adjust colors to be more professional"

### Phase 3: AI Refinement

**Section-Specific AI Commands:**
- "Write a better tagline for my hero section"
- "Expand my about section with SEO-friendly content"
- "Generate host bios based on podcast topics"

**Global AI Commands:**
- "Make the whole site more playful/professional/minimal"
- "Improve all section copy for conversion"
- "Suggest missing sections based on my podcast niche"

**AI Workflow:**
1. User makes structural changes (add/remove/reorder sections)
2. User configures basic content in forms
3. AI refines copy, suggests improvements, fills gaps
4. User reviews changes, accepts/rejects per section

## Technical Implementation

### Backend Changes

**1. Section Library (`api/services/website_sections.py`)**
```python
SECTION_DEFINITIONS = {
    "hero": {
        "id": "hero",
        "label": "Hero Section",
        "category": "core",
        "default_enabled": True,
        "required_fields": ["title", "subtitle"],
        "optional_fields": ["cta_text", "cta_url", "background_image"],
        "ai_prompt_hints": [
            "Create an attention-grabbing headline",
            "Summarize the podcast value proposition",
        ]
    },
    # ... more sections
}
```

**2. Website Model Extension (`models/website.py`)**
```python
# Add to PodcastWebsite model:
sections_order: List[str] = Field(default_factory=list)  # ordered section IDs
sections_config: Dict[str, Dict] = Field(default_factory=dict)  # section-specific data
sections_enabled: Dict[str, bool] = Field(default_factory=dict)  # toggle state
```

**3. New API Endpoints**
- `GET /api/website-sections` - List available sections
- `PATCH /api/podcasts/{id}/website/sections` - Reorder sections
- `PATCH /api/podcasts/{id}/website/sections/{section_id}` - Update section config
- `POST /api/podcasts/{id}/website/sections/{section_id}/refine` - AI refine single section

### Frontend Changes

**1. Section Components (`components/website/sections/`)**
- `HeroSection.jsx` - Configurable hero with preview
- `AboutSection.jsx`
- `LatestEpisodesSection.jsx`
- ... one component per section type

**2. Drag-and-Drop Library**
- **Option A:** `react-beautiful-dnd` (popular, well-maintained)
- **Option B:** `@dnd-kit/core` (modern, flexible)
- **Option C:** `react-dnd` (more complex, very customizable)

**Recommendation:** Start with `@dnd-kit/core` for better touch support and accessibility

**3. Setup Wizard (`components/website/SetupWizard.jsx`)**
- Multi-step form with progress indicator
- Section selection gallery
- Quick config forms
- Preview panel

**4. Visual Editor (`components/website/VisualEditor.jsx`)**
- Droppable canvas area
- Draggable section cards
- Section config modals
- AI chat integration

**5. Section Palette (`components/website/SectionPalette.jsx`)**
- Categorized, searchable section list
- Drag-to-add functionality
- Tooltips with descriptions

## Migration Strategy

### Phase 1: Backend Foundation (Week 1)
- Define section library with 18 initial sections
- Add section_order, sections_config, sections_enabled to website model
- Migration to convert existing layouts to section-based format
- New API endpoints for section management

### Phase 2: Basic UI (Week 2)
- Build section components for preview
- Implement drag-and-drop canvas (without AI)
- Create setup wizard (4-step flow)
- Manual section configuration forms

### Phase 3: AI Integration (Week 3)
- Per-section AI refinement
- Global AI commands
- Convert existing AI prompts to section-aware format
- Section-specific AI prompt engineering

### Phase 4: Polish & Launch (Week 4)
- Responsive design for all sections
- Advanced section options (animations, layouts)
- User testing and refinement
- Documentation and help system

## AI Prompt Engineering

### Section-Aware Prompts

**Old Approach:** "Generate a complete website layout"

**New Approach:**
```
The user has selected these sections: [hero, about, latest-episodes, newsletter, testimonials]

For the HERO section:
- Current config: {title: "My Podcast", subtitle: ""}
- Instruction: "Make it more exciting and add a clear value proposition"
- Return: {title: string, subtitle: string, cta_text: string}

For the ABOUT section:
- Current config: {heading: "About the Show", body: "We talk about tech"}
- Instruction: "Expand with SEO keywords and target audience"
- Return: {heading: string, body: string (markdown)}
```

### Context-Aware Refinement

AI receives:
1. Full section configuration
2. Podcast metadata (name, description, categories)
3. Recent episodes (for relevant examples)
4. User's specific instruction
5. Section position in overall layout

Returns:
- Updated section config
- Explanation of changes
- Suggestions for related sections

## Success Metrics

**User Experience:**
- Time to first complete website (target: <10 minutes)
- Section usage analytics (which sections are most popular)
- AI refinement acceptance rate (% of suggestions kept)
- User satisfaction (survey after publish)

**Technical:**
- Page load time for published sites (<2s)
- Section render performance (60fps drag-and-drop)
- AI response time for refinements (<5s)
- Mobile responsiveness score (100% sections mobile-ready)

## Future Enhancements

**Phase 5+:**
- Section marketplace (custom sections from community)
- A/B testing different section configurations
- Analytics integration (track section engagement)
- Advanced section types (countdown timers, live chat, etc.)
- Theme builder (color scheme variations)
- Section animations and transitions
- Export to WordPress/static HTML

---

## Next Steps

1. ✅ Review and approve this architecture document
2. ⏳ Create section definitions JSON/YAML file
3. ⏳ Implement backend section library
4. ⏳ Build frontend drag-and-drop prototype
5. ⏳ User testing with 5-10 beta users
6. ⏳ Iterate based on feedback
7. ⏳ Launch publicly with onboarding tutorial

---

*This document serves as the blueprint for the website builder redesign. All implementation should reference this architecture to maintain consistency.*
