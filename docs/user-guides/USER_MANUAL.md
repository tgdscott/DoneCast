# Podcast Plus Plus - User Manual

**Version:** 2.0  
**Last Updated:** October 11, 2025  
**For:** Content Creators, Podcasters, Audio Professionals

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Creating Your First Podcast](#creating-your-first-podcast)
3. [Understanding Templates](#understanding-templates)
4. [Creating Episodes](#creating-episodes)
5. [Audio Processing Features](#audio-processing-features)
6. [AI-Powered Tools](#ai-powered-tools)
7. [Publishing & Distribution](#publishing--distribution)
8. [Media Library](#media-library)
9. [Analytics & Insights](#analytics--insights)
10. [Billing & Subscriptions](#billing--subscriptions)
11. [Settings & Configuration](#settings--configuration)
12. [Troubleshooting](#troubleshooting)

---

## Getting Started

### Welcome to Podcast Plus Plus!

Podcast Plus Plus is your all-in-one podcast creation platform. Whether you're a first-time podcaster or a seasoned pro, this platform makes it easy to:

- ✅ Record or upload audio
- ✅ Edit with AI assistance
- ✅ Add professional intros/outros and music
- ✅ Generate show notes automatically
- ✅ Publish to all major podcast platforms
- ✅ Track your audience

### First Login

1. **Sign in with Google** at https://app.podcastplusplus.com
2. **Complete the onboarding wizard** (takes 2-3 minutes)
3. **Create your first podcast show**
4. **Upload your first episode**

That's it! You're ready to start podcasting.

### Dashboard Overview

After logging in, you'll see your main dashboard with these tabs:

| Tab | Purpose |
|-----|---------|
| **Episodes** | View, create, and manage your episodes |
| **Templates** | Design reusable episode structures |
| **Media** | Manage uploaded audio files and music |
| **Analytics** | Track downloads, plays, and listener data |
| **Settings** | Configure your podcast and account |

---

## Creating Your First Podcast

### Step 1: Onboarding Wizard

When you first log in, the onboarding wizard will guide you through:

1. **Import or Create**
   - Import existing podcast from Spreaker
   - Create new podcast from scratch

2. **Podcast Details**
   - Show name
   - Description
   - Category (e.g., Technology, Comedy, News)
   - Cover art (1400x1400px recommended)

3. **Template Setup**
   - Choose episode structure
   - Add intro/outro audio (optional)
   - Select background music (optional)

4. **Voice Selection**
   - Pick AI voice for text-to-speech segments
   - Preview different voices

### Step 2: Podcast Settings

After onboarding, you can refine your podcast in **Settings**:

**Basic Information:**
- Title and description
- Author name
- Website URL
- Contact email

**Podcast Details:**
- Language
- Category and subcategory
- Explicit content flag
- Copyright notice

**iTunes Settings:**
- iTunes type (episodic vs. serial)
- Owner name and email
- iTunes categories

**Distribution:**
- RSS feed URL (auto-generated)
- Distribution status (Apple, Spotify, etc.)
- Embed player code

---

## Understanding Templates

### What is a Template?

A **template** is like a recipe for your episodes. It defines:
- **Episode structure** (intro, main content, outro)
- **Background music rules** (when and where music plays)
- **AI generation settings** (how to auto-create titles/descriptions)

Think of it this way:
- **Template** = Reusable structure (like a recipe)
- **Episode** = Single instance using that template (like a meal)

### Why Use Templates?

Templates save you time by:
- ✅ Reusing the same intro/outro for every episode
- ✅ Applying consistent music to all episodes
- ✅ Automating metadata generation
- ✅ Maintaining brand consistency

### Creating a Template

1. **Go to Templates tab**
2. **Click "Create Template"**
3. **Name your template** (e.g., "Standard Episode Format")
4. **Add segments:**

#### Available Segment Types

| Segment Type | Purpose | Example |
|--------------|---------|---------|
| **Intro** | Opening music/voiceover | "Welcome to My Podcast!" |
| **Main Content** | Your core episode audio | Interview, discussion, story |
| **Outro** | Closing music/CTA | "Subscribe and rate us!" |
| **Ad/Commercial** | Sponsorship reads | "This episode brought to you by..." |
| **Transition** | Between-segment music | Short musical break |

#### Adding Segments

For each segment, choose a **source**:

- **Upload Audio** - Use a file from your Media Library
- **Generate TTS** - Convert text to speech with AI voices
- **Record** - Record directly in your browser
- **Episode-Specific** - Prompt for audio when creating episode

**Example Template:**
```
1. Intro (Upload) → "MyPodcastIntro.mp3" (15 seconds)
2. Main Content (Episode-Specific) → User provides each time
3. Outro (TTS) → "Thanks for listening! Subscribe for more."
4. Ad (Upload) → "SponsorAd.mp3" (30 seconds)
```

### Background Music

Add background music that plays behind your segments:

1. **Click "Add Music Rule"**
2. **Select music file** from Media Library
3. **Choose segments** to apply music to (intro, content, outro)
4. **Configure timing:**
   - Start offset (seconds from segment start)
   - End offset (seconds before segment end)
   - Fade in/out duration
   - Volume level (dB)

**Music Ducking**: Music automatically lowers when speech is detected.

### AI Guidance Settings

Configure how AI generates content for episodes using this template:

**Auto-Fill AI:** Enable/disable automatic suggestions

**Title Instructions:**
```
Generate catchy, SEO-friendly titles under 60 characters.
Always include the episode number.
```

**Description Instructions:**
```
Write engaging 2-3 paragraph descriptions.
Include key talking points and guest names.
End with a call-to-action to subscribe.
```

**Tags:**
- Auto-generate tags from transcript
- Always include specific tags (e.g., "gardening", "comedy")

---

## Creating Episodes

### Quick Create (3-Minute Workflow)

1. **Click "Create Episode"** button
2. **Select template** (or start from scratch)
3. **Upload main audio** (drag & drop or browse)
4. **Wait for transcription** (2-3 minutes per hour of audio)
5. **Review AI-generated metadata** (title, description, tags)
6. **Click "Assemble & Review"**
7. **Preview assembled episode**
8. **Publish!**

### Detailed Episode Creation

#### Step 1: Choose Template

Select a template or create custom structure for this episode.

#### Step 2: Upload Main Content

**Supported formats:** MP3, WAV, M4A, OGG, FLAC  
**Max file size:** 500 MB  
**Recommended quality:** 128 kbps or higher

**Upload methods:**
- Drag & drop onto upload area
- Click to browse files
- Record directly in browser (coming soon)

**Processing begins immediately:**
- File uploads to cloud storage
- Transcription starts automatically
- Progress bar shows upload status

#### Step 3: Process Audio (Optional)

While transcription runs, you can:

**Intern Mode** - Detect editing commands
- Say "cut that out" or "remove this part"
- AI detects these commands in your recording
- Marks sections for removal

**Flubber Detection** - Remove filler words
- Automatically detects "um", "uh", "like"
- Removes awkward pauses
- Smooths out speech

Click **"Prepare with Intern"** or **"Apply Flubber"** to enable.

#### Step 4: Episode Details

**Required Fields:**
- Episode Title
- Episode Number
- Season Number (optional)

**Optional Fields:**
- Description
- Tags (comma-separated)
- Cover art (overrides show default)
- Explicit content flag

**AI Suggestions:**
- Click "AI Suggest Title" for automatic titles
- Click "AI Suggest Description" for show notes
- Click "Generate Tags" for automatic tagging

#### Step 5: Assemble Episode

Click **"Assemble & Review"** to:
1. Stitch all segments together
2. Apply background music with ducking
3. Normalize audio levels
4. Add fade-ins/fade-outs
5. Export final MP3

**Assembly takes:** 30-90 seconds for typical episode

#### Step 6: Review

**Audio Player:**
- Listen to full assembled episode
- Scrub through timeline
- View waveform visualization

**If not satisfied:**
- Go back and adjust segments
- Change music timing
- Tweak volume levels
- Re-assemble

#### Step 7: Publish

**Publishing Options:**

**Publish Now:**
- Episode goes live immediately
- RSS feed updates within 5 minutes
- Shows in all podcast apps

**Schedule for Later:**
- Choose date and time
- Timezone-aware scheduling
- Automatic publication at specified time

**Save as Draft:**
- Keep private until ready
- Edit anytime before publishing

---

## Audio Processing Features

### Automatic Transcription

Every uploaded audio file is automatically transcribed using Assembly AI.

**Features:**
- Speaker diarization (labels different speakers)
- Punctuation and formatting
- Timestamp for every word
- Searchable transcript viewer

**Transcript Access:**
- View in Episode Details
- Download as TXT or JSON
- Used for AI suggestions

### Intern Mode (Spoken Commands)

Intern detects spoken editing instructions in your recording.

**Supported Commands:**
- "Cut that out"
- "Remove this part"
- "Delete the last minute"
- "Start over from here"

**How to Use:**
1. Record your podcast naturally
2. Say editing commands when you make mistakes
3. Upload to Podcast Plus Plus
4. Click "Prepare with Intern"
5. Review detected commands
6. Apply edits automatically

**Best Practices:**
- Pause 1 second before and after command
- Speak command clearly
- Use consistent phrasing

### Flubber (Filler Word Removal)

Flubber automatically removes filler words and awkward pauses.

**What it Removes:**
- Um, uh, er
- Like, you know, I mean
- Long pauses (>2 seconds)
- Stutters and false starts

**How to Use:**
1. Upload audio
2. Click "Apply Flubber"
3. AI detects filler words
4. Review suggested removals
5. Apply selected edits

**Settings:**
- Aggressiveness (conservative, balanced, aggressive)
- Minimum pause length to remove
- Preserve natural speech patterns

### Audio Enhancement

**Automatic Processing:**
- Normalization (consistent volume)
- Noise gate (remove background noise)
- Compression (balanced dynamics)
- EQ (optimize for podcast distribution)

**Music Mixing:**
- Automatic ducking (lower music during speech)
- Crossfades between segments
- Fade in/out at episode start/end

---

## AI-Powered Tools

### AI Assistant "Mike"

Mike is your always-available AI helper, accessible from any page.

**Click the chat bubble** in the bottom-right corner to:
- Ask questions about features
- Get step-by-step guidance
- Find settings or pages
- Troubleshoot issues

**Example Questions:**
- "How do I add an intro to my podcast?"
- "Where's my uploaded audio file?"
- "What's the difference between a template and an episode?"
- "How do I schedule an episode for later?"

**Special Features:**
- **Context-aware** - Knows what page you're on
- **UI highlighting** - Can point to specific buttons/fields
- **Proactive help** - Offers assistance when you seem stuck

### AI Content Generation

#### Title Generation

Click **"AI Suggest Title"** to generate episode titles.

**AI considers:**
- Transcript content
- Guest names (if mentioned)
- Key topics discussed
- Template instructions
- SEO best practices

**Example Output:**
> "Episode 42: Climate Change Solutions with Dr. Jane Smith"

**Customization:**
- Edit AI instructions in template
- Specify tone (professional, casual, funny)
- Include/exclude specific words

#### Description Generation

Click **"AI Suggest Description"** for show notes.

**AI creates:**
- 2-3 paragraph summary
- Key talking points
- Guest bio (if applicable)
- Call-to-action

**Example Output:**
> In this episode, we sit down with renowned climate scientist Dr. Jane Smith to discuss innovative solutions for combating climate change. From renewable energy breakthroughs to policy recommendations, we cover the latest developments in environmental science.
>
> Dr. Smith shares insights from her 20 years of research, including her groundbreaking work on carbon capture technology. We also discuss practical steps individuals can take to reduce their carbon footprint.
>
> Subscribe to never miss an episode! Rate us on Apple Podcasts.

#### Tag Generation

Click **"Generate Tags"** for automatic categorization.

**AI extracts:**
- Main topics
- Named entities (people, places, organizations)
- Themes and concepts
- Technical terms

**Example Output:**
```
climate change, renewable energy, carbon capture, 
environmental policy, sustainability, Dr. Jane Smith
```

### Cover Art Generation (Coming Soon)

Generate custom episode cover art with AI.

**Features:**
- Text-to-image generation
- Match your brand colors
- Include episode title
- Professional templates

---

## Publishing & Distribution

### Publishing Process

#### 1. Draft Stage
- Episode saved but not public
- Visible only to you
- Can edit freely

#### 2. Processing Stage
- Audio being assembled
- Transcription running
- Metadata being generated

#### 3. Published Stage
- Live in RSS feed
- Visible to all podcast apps
- Downloadable by listeners

#### 4. Failed Stage
- Error during processing
- Check logs for details
- Contact support if persistent

### RSS Feed

Your podcast has a unique RSS feed URL:

```
https://app.podcastplusplus.com/feeds/podcast/{your-podcast-id}
```

**Submit this URL to:**
- Apple Podcasts Connect
- Spotify for Podcasters
- Google Podcasts Manager
- Amazon Music
- Pocket Casts
- Overcast
- And more...

**RSS Feed Features:**
- iTunes-compliant tags
- Episode enclosures with file size/duration
- Show artwork
- Episode artwork
- Explicit content flags
- Season/episode numbering
- GUID for each episode (stable IDs)

### Episode Management

**View All Episodes:**
- Go to Episodes tab
- Filter by status (draft, published, etc.)
- Sort by date, title, episode number

**Edit Published Episodes:**
- Click episode to open
- Modify metadata (title, description)
- Update cover art
- Replace audio (re-uploads)
- Changes reflected in RSS feed

**Delete Episodes:**
- Removes from RSS feed
- Mark as deleted (doesn't delete files)
- Cannot undo deletion

### Distribution Status

Track where your podcast is available:

**Distribution Status Table:**
| Platform | Status | Submitted | Approved |
|----------|--------|-----------|----------|
| Apple Podcasts | ✅ Live | 2025-01-10 | 2025-01-12 |
| Spotify | ✅ Live | 2025-01-10 | 2025-01-11 |
| Google Podcasts | 🟡 Pending | 2025-01-15 | - |
| Amazon Music | ❌ Not Submitted | - | - |

**Status Meanings:**
- ✅ **Live** - Approved and publicly available
- 🟡 **Pending** - Submitted, awaiting review
- ❌ **Not Submitted** - Not yet submitted
- 🔴 **Rejected** - Submission rejected (see notes)

---

## Media Library

### Overview

The Media Library stores all your audio files:
- Episode audio
- Intro/outro clips
- Background music
- Sound effects
- Commercial reads

### Uploading Files

1. **Go to Media tab**
2. **Click "Upload Audio"**
3. **Select category:**
   - Main Content
   - Intro
   - Outro
   - Background Music
   - Sound Effects
   - Ads/Commercials

4. **Choose file** (drag & drop or browse)
5. **Wait for upload** (progress bar shown)

**Upload Limits:**
- Max file size: 500 MB
- Supported formats: MP3, WAV, M4A, OGG, FLAC
- No limit on number of files

### Organizing Files

**Filter by:**
- Category
- Date uploaded
- File name
- File size

**Actions:**
- Play preview
- Download original
- Delete
- Rename

### Waveform Viewer

Click any audio file to view:
- Visual waveform
- Duration
- File size
- Upload date
- Used in episodes (reference count)

---

## Analytics & Insights

### Dashboard Overview

**Key Metrics:**
- Total plays (last 30 days)
- Total downloads
- Unique listeners
- Average completion rate

### Episode Performance

**Per-Episode Stats:**
- Play count
- Download count
- Completion rate
- Drop-off points

**Time Series:**
- Plays over time (daily, weekly, monthly)
- Geographic distribution
- Listening apps used

### OP3 Analytics Integration

Podcast Plus Plus uses OP3 (Open Podcast Prefix Project) for accurate download tracking.

**What OP3 Tracks:**
- Downloads per episode
- Unique listeners
- Listening apps
- Geographic location (country-level)

**Privacy-Friendly:**
- No personal data collection
- Anonymous aggregate stats
- GDPR compliant

### Exporting Data

**Export Options:**
- CSV (all episode data)
- JSON (API format)
- PDF (visual reports)

---

## Billing & Subscriptions

### Subscription Plans

#### Free Tier
- 50 minutes per month
- 1 podcast
- 10 episodes
- Basic support

#### Creator ($19/month)
- 500 minutes per month
- 3 podcasts
- Unlimited episodes
- Email support
- Advanced AI features

#### Professional ($49/month)
- 2000 minutes per month
- 10 podcasts
- Unlimited episodes
- Priority support
- Custom branding
- Analytics API access

#### Enterprise (Custom)
- Unlimited minutes
- Unlimited podcasts
- White-label option
- Dedicated account manager
- SLA guarantee

### Usage Tracking

**View Current Usage:**
- Go to Settings → Billing
- See minutes consumed this month
- See minutes remaining
- Overage warnings

**How Minutes Are Calculated:**
- Transcription: 1 minute = 1 minute consumed
- TTS generation: 1 minute = 1 minute consumed
- Assembly/processing: No charge

### Managing Subscription

**Upgrade/Downgrade:**
1. Go to Settings → Billing
2. Click "Change Plan"
3. Select new tier
4. Confirm change

**Billing applies:**
- Upgrades: Prorated immediately
- Downgrades: Take effect next billing cycle

**Cancel Subscription:**
1. Go to Settings → Billing
2. Click "Cancel Subscription"
3. Confirm cancellation
4. Access continues until end of billing period

### Payment Methods

**Accepted:**
- Credit card (Visa, Mastercard, Amex)
- Debit card
- Apple Pay / Google Pay

**Stripe Integration:**
- Secure payment processing
- PCI compliant
- Automatic billing

---

## Settings & Configuration

### Account Settings

**Profile:**
- Display name
- Email address (used for login)
- Timezone (for scheduling)
- Avatar image

**Security:**
- Change password
- Two-factor authentication (coming soon)
- Connected accounts (Google)

### Podcast Settings

**Basic Info:**
- Show title
- Description
- Category
- Cover art

**Advanced:**
- Custom RSS feed URL slug
- iTunes settings
- Copyright text
- Language code

**Distribution:**
- Platform submission links
- RSS feed URL
- Embed player code

### Notification Preferences

**Email Notifications:**
- Episode published
- Processing failed
- Usage limits reached
- New features announced

**In-App Notifications:**
- Transcription complete
- Assembly finished
- Comments on episodes (coming soon)

---

## Troubleshooting

### Common Issues

#### "Uploaded file not found"

**Cause:** File hasn't finished uploading or was deleted.

**Solution:**
1. Check Media Library to verify file exists
2. Re-upload if missing
3. Wait a few minutes for cloud sync

#### "Processing" stuck for hours

**Cause:** Large file or temporary service issue.

**Solution:**
1. Refresh the page
2. Check episode status in Episodes tab
3. Contact support if still stuck after 30 minutes

#### "Transcript not ready"

**Cause:** Transcription takes 2-3 minutes per hour of audio.

**Solution:**
1. Wait for processing to complete
2. Check notification for completion
3. Refresh page to see transcript

#### RSS feed not updating

**Cause:** Changes take 5-10 minutes to propagate.

**Solution:**
1. Wait 10 minutes
2. Clear podcast app cache
3. Verify episode is published (not draft)

#### Audio quality issues

**Cause:** Low-quality source file or processing settings.

**Solution:**
1. Upload higher-bitrate source (128 kbps minimum)
2. Check music volume isn't too loud
3. Adjust normalization settings

### Getting Help

**AI Assistant Mike:**
- Click chat bubble in bottom-right
- Available 24/7
- Instant answers

**Documentation:**
- Browse [Full Documentation Index](../DOCS_INDEX.md)
- Check [FAQ](FAQ.md)
- Read [Troubleshooting Guide](../troubleshooting/TROUBLESHOOTING_GUIDE.md)

**Support:**
- Email: support@podcastplusplus.com
- Response time: 24-48 hours (Creator/Professional)
- Priority support: 4-hour response (Enterprise)

---

## Tips & Best Practices

### Recording Quality

✅ **DO:**
- Use a good microphone
- Record in a quiet space
- Speak 6-12 inches from mic
- Use pop filter
- Record at 44.1kHz or higher

❌ **DON'T:**
- Record in echoey rooms
- Use built-in laptop mic
- Eat or drink while recording
- Touch the microphone
- Record too quietly

### Episode Optimization

**For SEO:**
- Use descriptive titles with keywords
- Write detailed show notes (200+ words)
- Include guest names and topics
- Add relevant tags

**For Engagement:**
- Hook listeners in first 30 seconds
- Include clear call-to-action
- Ask for ratings/reviews
- Mention next episode topic

### Consistent Publishing

**Create a schedule:**
- Weekly, bi-weekly, or monthly
- Same day and time
- Set expectations with audience

**Batch recording:**
- Record 3-4 episodes at once
- Schedule ahead
- Reduce production stress

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Ctrl + K` | Open Mike (AI Assistant) |
| `Ctrl + N` | New Episode |
| `Ctrl + S` | Save (in editor) |
| `Space` | Play/Pause audio |
| `←` / `→` | Skip backward/forward 5s |
| `Shift + ←/→` | Skip backward/forward 30s |

---

## Next Steps

Now that you understand the basics:

1. ✅ Create your first template
2. ✅ Upload and publish an episode
3. ✅ Submit RSS feed to Apple Podcasts
4. ✅ Explore AI features
5. ✅ Check your analytics

**Need more help?** Ask Mike or check the [Full Documentation Index](../DOCS_INDEX.md).

Happy podcasting! 🎙️
