import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { 
  ArrowLeft, BookOpen, Search, ChevronRight, 
  Mic, Upload, Settings, Wand2, Music, BarChart,
  CreditCard, Zap, AlertCircle, CheckCircle, PlayCircle,
  FileAudio, Sparkles, Globe, Clock, TrendingUp
} from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function Guides() {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');

  const guides = [
    {
      category: 'Getting Started',
      icon: PlayCircle,
      description: 'New to DoneCast? Start here to learn the basics',
      items: [
        {
          title: 'Quick Start Guide',
          description: 'Get up and running in 5 minutes',
          link: '#quick-start',
          content: `
## Quick Start Guide

Welcome to DoneCast! Here's how to create your first episode:

### 1. Complete Onboarding
- Click through the onboarding wizard
- Set up your podcast name and description
- Choose your intro/outro audio
- Select a voice for AI features

### 2. Upload Your Audio
- Click **Record or Upload Audio** button from the dashboard
- Choose to either upload a file already recorded, or record one directly in your browser
- After the audio has been uploaded and transcribed, click **Assemble New Episode** from the dashboard

### 3. Process & Publish
- Approve any AI-features you may have, like Intern commands or Flubber markers
- Enter text for any AI-generated intro or outro segments
- Upload a cover image for your episode (optional)
- Double check all the AI-generated title, notes, and tags and correct anything as needed
- Verify the publish date and time and click **Publish Episode**
- After a few minutes of processing, your episode will be live or scheduled, whichever you chose!
- Your RSS feed updates automatically!

**That's it!** Your episode is now live and available on all podcast platforms.
          `
        },
        {
          title: 'Dashboard Overview',
          description: 'Understanding your main dashboard',
          link: '#dashboard',
          content: `
## Dashboard Overview

Your dashboard is divided into several key sections:

### Episodes Tab
- **View all episodes** in your podcast
- **Edit or delete** existing episodes
- **Monitor or change processing status for exisiting episodes** (pending, processing, published)

### Templates Tab
- **Design reusable structures** for your episodes
- **Set default intro/outro** audio
- **Configure AI settings** for show notes
- Set up as many templates as you want for different episode types

### Media Library
- **Upload and manage** all intro, outro, music, and sound effect audio files
- **Organize by category** (intro, outro, music, sound effects)
- **Preview audio** before using
- **Delete unused files** to keep organized
- See Global Music and Sound Effects libraries available to all users

### Analytics
- **Track downloads** and plays
- **See geographic data** of your listeners
- **Monitor growth** over time
- **Identify top episodes**

## Subscription
-  See, manage, and change your current plan
-  See how many credits you have, and buy more if needed

### Settings
- **Manage account** (email, password, subscription)
- **Configure RSS feed** settings
- **Set up billing** and view usage

## Website Builder
-  See your podcast's website
-  Customize everything from colors, fonts, layouts, and more
          `
        },
        {
          title: 'Creating Your First Podcast',
          description: 'Complete walkthrough of podcast setup',
          link: '#first-podcast',
          content: `
## Creating Your First Podcast

### Onboarding Wizard

The onboarding wizard guides you through essential setup:

#### Step 1: Import or Create
- **Upload Pre-exisiting show** (if you have an existing show)
- **Create from scratch** (recommended for new podcasters)

#### Step 2: Podcast Details
- **Show Name:** Keep it memorable and searchable
- **Description:** Explain what your podcast is about (250 words max)
- **Category:** Choose the most relevant category
- **Cover Art:** Upload 1400x1400px image (required for podcast platforms)

#### Step 3: Template Setup
- **Intro Audio:** Upload or generate with AI voice
- **Outro Audio:** Upload or generate with AI voice
- **Background Music:** Choose from our library or upload your own

#### Step 4: Voice Selection
- **Preview voices** available for text-to-speech
- **Select default voice** for AI-generated segments
- **Test with sample text** to hear results

### After Onboarding

Once complete, you can:
- Create your first episode
- Refine podcast settings
- Add more media to your library
- Explore analytics dashboard
          `
        }
      ]
    },
    {
      category: 'Episode Creation',
      icon: Mic,
      description: 'Learn how to create, edit, and manage your podcast episodes',
      items: [
        {
          title: 'Uploading Audio Files',
          description: 'How to upload and manage your recordings',
          link: '#upload',
          content: `
## Uploading Audio Files

### Supported Formats
- **MP3** (recommended)
- **WAV**
- **M4A**
- **FLAC**
- **OGG**

### Upload Methods

#### 1. Drag & Drop
- Drag files directly onto the upload area
- Multiple files supported
- Progress bar shows upload status

#### 2. File Browser
- Click "Choose File" button
- Browse your computer
- Select one or more files

#### 3. Voice Recorder
- Record directly in browser
- No external software needed
- Instant upload when done

### File Size Limits
- **Free Plan:** Up to 500 MB per file
- **Pro Plan:** Up to 2 GB per file
- **Enterprise:** Unlimited

### Processing Time
- Small files (< 50 MB): 1-2 minutes
- Medium files (50-200 MB): 3-5 minutes
- Large files (> 200 MB): 5-10 minutes

### Tips for Best Results
- ✅ Use high-quality recordings (44.1kHz or 48kHz sample rate)
- ✅ Normalize audio levels before uploading
- ✅ Remove long silences at start/end
- ✅ Save original files as backup
          `
        },
        {
          title: 'Episode Assembly',
          description: 'How episode processing works',
          link: '#assembly',
          content: `
## Episode Assembly

### What Happens During Assembly?

When you click "Assemble Episode," the system:

1. **Transcribes** your audio (if not already done)
2. **Applies edits** from Intern or Flubber (if used)
3. **Adds intro/outro** from your template
4. **Mixes background music** (if configured)
5. **Generates show notes** with AI (if enabled)
6. **Creates final audio** file
7. **Uploads to cloud storage**

### Assembly Status

- **Pending:** Waiting in queue
- **Processing:** Currently assembling (2-5 minutes typically)
- **Processed:** Ready to publish
- **Published:** Live on RSS feed
- **Error:** Something went wrong (check logs)

### Troubleshooting Assembly

**Episode stuck in "Processing"?**
- Wait 10 minutes (large files take time)
- Refresh the page
- Check error logs in episode details
- Contact support if persists

**Assembly failed?**
- Check that all required files are uploaded
- Ensure intro/outro are valid audio files
- Verify template settings are complete
- Try re-uploading main content

**Audio quality issues?**
- Upload higher quality source file
- Check template music volume settings
- Adjust ducking rules in template editor
          `
        },
        {
          title: 'Publishing Episodes',
          description: 'Making your episode live',
          link: '#publishing',
          content: `
## Publishing Episodes

### Before Publishing

Make sure you have:
- ✅ Assembled the episode successfully
- ✅ Previewed the final audio
- ✅ Written episode title and description
- ✅ Set publication date (optional: schedule for future)
- ✅ Reviewed show notes (if AI-generated)

### Publishing Steps

1. **Click "Publish"** on your processed episode
2. **Confirm details** in modal dialog
3. **Set publication date** (or publish immediately)
4. **Click "Confirm"** to go live

### After Publishing

Your episode will:
- Appear in your RSS feed automatically
- Be available on all podcast apps within 24 hours
- Show up in your public episode list
- Start tracking analytics data

### Unpublishing

To remove an episode from your feed:
1. Go to episode details
2. Click "Unpublish"
3. Confirm the action
4. Episode removed from RSS (but data preserved)

### Scheduling Episodes

You can schedule episodes for future release:
1. During publish, select "Schedule"
2. Choose date and time
3. Episode will auto-publish at that time
4. Edit or cancel scheduled episodes anytime
          `
        },
        {
          title: 'Manual Editor',
          description: 'Fine-tune your episodes with precision editing',
          link: '#manual-editor',
          content: `
## Manual Editor

### What is the Manual Editor?

The Manual Editor gives you complete control over your episode's final audio. You can:
- View and edit the full waveform
- Cut, trim, and rearrange segments
- Adjust volume levels
- Add fade in/out effects
- Preview changes in real-time

### Opening the Manual Editor

1. Go to **Episodes** tab
2. Find your episode (must be assembled)
3. Click the **"Edit"** button or three-dot menu
4. Select **"Manual Editor"**

### Editor Interface

**Waveform Display:**
- Visual representation of your audio
- Zoom in/out for precision
- Click to set playback position

**Timeline Tools:**
- Play/Pause controls
- Skip forward/backward
- Zoom controls
- Selection tools

**Edit Actions:**
- **Cut:** Remove selected section
- **Split:** Divide audio at cursor
- **Fade:** Add fade in/out
- **Volume:** Adjust level of selection

### Making Edits

1. **Select audio segment:**
   - Click and drag on waveform
   - Or use keyboard shortcuts (Shift + Arrow keys)

2. **Choose action:**
   - Cut: Delete selection
   - Fade: Gradual volume change
   - Normalize: Balance audio levels

3. **Preview changes:**
   - Play edited section
   - Undo if needed (Ctrl+Z)

4. **Save:**
   - Click "Save Changes"
   - Episode re-processes with edits

### Tips for Best Results

✅ **Zoom in for precision:** Use zoom for exact cuts  
✅ **Preview before saving:** Always listen to your edits  
✅ **Use fade in/out:** Avoid abrupt starts/stops  
✅ **Save frequently:** Changes persist in editor  
❌ Don't make too many tiny cuts (can sound choppy)  
❌ Don't forget to save before closing

### Keyboard Shortcuts

- **Space:** Play/Pause
- **→ / ←:** Skip 5 seconds
- **Shift + →/←:** Skip 30 seconds
- **Ctrl + Z:** Undo
- **Ctrl + S:** Save
          `
        },
        {
          title: 'RSS Feeds & Distribution',
          description: 'Submit your podcast to Apple, Spotify, and more',
          link: '#rss-distribution',
          content: `
## RSS Feeds & Distribution

### Your RSS Feed URL

Every podcast gets a unique RSS feed URL:

https://donecast.com/rss/your-show-name.xml

This feed updates automatically when you publish episodes.

### Finding Your RSS URL

1. Go to **Settings** tab
2. Look for **"RSS Feed URL"** section
3. Click **"Copy URL"** button
4. Use this URL to submit to directories

### Submitting to Apple Podcasts

1. **Go to:** [Apple Podcasts Connect](https://podcastsconnect.apple.com)
2. **Sign in** with Apple ID
3. Click **"Add a Show"**
4. **Paste your RSS feed URL**
5. **Fill in show details** (Apple pulls most from RSS)
6. **Submit for review** (takes 2-5 business days)

### Submitting to Spotify

1. **Go to:** [Spotify for Creators](https://creators.spotify.com)
2. **Log in** or create account
3. Click **"Get Started"**
4. **Enter RSS feed URL**
5. **Claim your podcast**
6. **Publish** (usually approved within 24 hours)

### Other Major Directories

**Google Podcasts:**
- Visit [Google Podcasts Manager](https://podcastsmanager.google.com)
- Add RSS feed
- Verify ownership

**Amazon Music/Audible:**
- Visit [Amazon Music for Podcasters](https://music.amazon.com/podcasters)
- Submit RSS feed
- Complete podcast details

**iHeartRadio:**
- Go to [iHeartRadio Podcast Directory](https://www.iheart.com/podcast-contact/)
- Fill out submission form
- Include RSS feed URL

### RSS Feed Updates

When you publish a new episode:
- RSS feed updates within **1 minute**
- Podcast apps check every **1-24 hours**
- Some platforms may take **48 hours** to show new episodes

### Custom Domain (Pro Feature)

Upgrade to Pro to use your own domain:
- https://yourwebsite.com/podcast.xml
- Better branding
- More professional
- SEO benefits
          `
        },
        {
          title: 'Analytics & Tracking',
          description: 'Understand your audience and grow your show',
          link: '#analytics',
          content: `
## Analytics & Tracking

### Accessing Analytics

1. Click **Analytics** tab in dashboard
2. View data for all episodes or individual ones
3. Filter by date range (last 7 days, 30 days, all time)

### Key Metrics

**Downloads:**
- Total number of episode downloads
- Unique vs. repeat listeners
- Download trends over time

**Geographic Data:**
- Where your listeners are located
- Country-level breakdown
- Top cities (Pro feature)

**Listening Apps:**
- Which apps people use (Apple Podcasts, Spotify, etc.)
- Platform distribution
- Mobile vs. desktop

**Episode Performance:**
- Most popular episodes
- Average listen duration
- Completion rate

### Understanding the Data

**What's a "Download"?**
- Someone starts playing your episode
- Counts once per IP address per 24 hours
- Industry standard metric (IAB certified)

**Why Don't Numbers Match?**
Different platforms report differently:
- **Apple:** Reports streams + downloads
- **Spotify:** Only reports Spotify listeners
- **Analytics Dashboard:** Shows ALL downloads across platforms

**When Does Data Update?**
- Real-time for new downloads (within 1 hour)
- Geographic data updates every 4 hours
- Historical data available for all published episodes

### OP3 Analytics Integration

DoneCast uses OP3 (Open Podcast Prefix Project) for accurate tracking:
- Privacy-respecting analytics
- Cross-platform aggregation
- Industry-standard metrics
- No listener surveillance

### Tips for Growing Your Audience

✅ **Publish consistently:** Weekly schedule works best  
✅ **Promote on social media:** Share episode links  
✅ **Encourage reviews:** Ask listeners to rate/review  
✅ **Collaborate:** Guest on other podcasts  
✅ **Optimize titles:** Make them searchable and compelling  
✅ **Use show notes:** Include keywords and links

### Analytics Best Practices

- Check analytics weekly, not daily (reduces anxiety)
- Focus on trends, not individual spikes
- Compare episodes to find what resonates
- Use geographic data to plan guest topics
- Track completion rates to optimize episode length
          `
        }
      ]
    },
    {
      category: 'AI Features',
      icon: Sparkles,
      description: 'Discover how AI can help you create better podcasts faster',
      items: [
        {
          title: 'AI-Powered Editing (Intern)',
          description: 'Edit by speaking commands',
          link: '#intern',
          content: `
## AI-Powered Editing: Intern

### What is Intern?

Intern listens to your audio and detects spoken editing commands like:
- "Insert intro here"
- "Cut this out"
- "Add music"

### How to Use Intern

1. **Record with commands:** While recording, say editing instructions out loud
2. **Upload to platform:** Upload your audio as usual
3. **Run Intern:** Click "Prepare with Intern" before assembly
4. **Review markers:** See detected commands and their timestamps
5. **Approve edits:** Choose which commands to apply
6. **Assemble:** Process episode with edits applied

### Supported Commands

**Insertion:**
- "Insert intro" / "Add intro"
- "Insert outro" / "Add outro"
- "Play music" / "Add background music"

**Removal:**
- "Cut this out" / "Delete this"
- "Remove this section"
- "Skip this part"

**Markers:**
- "Chapter marker: [title]"
- "Bookmark this"
- "Note: [text]"

### Tips for Best Results

- ✅ **Speak clearly** when giving commands
- ✅ **Pause briefly** before and after commands
- ✅ **Use exact phrases** from supported list
- ✅ **Review all markers** before assembly
- ❌ Don't mumble or speak too fast
- ❌ Don't give commands while talking over others
          `
        },
        {
          title: 'Mistake Markers (Flubber)',
          description: 'Mark mistakes while recording by saying "flubber"',
          link: '#flubber',
          content: `
## Mistake Markers: Flubber

### What is Flubber?

Flubber lets you mark audio mistakes while recording by simply saying the word "flubber" out loud. When you make a mistake, just say "flubber" and continue - the system will help you remove that section later.

**Example:**
"The capital of France is Berlin... flubber... The capital of France is Paris."

### How to Use Flubber

1. **While recording:** When you make a mistake, say "flubber" clearly
2. **Continue recording:** No need to stop or start over
3. **Upload audio** to episode
4. **Click "Prepare Flubber Contexts"** in episode details
5. **Review snippets:** Each "flubber" creates an audio clip with context
6. **Mark mistake start:** Listen and indicate where the flub actually began
7. **Apply cuts:** System removes from mistake start to "flubber" keyword
8. **Assemble episode** with all flubs removed

### What Flubber Detects

The system listens for the spoken word "flubber" and creates audio snippets with:
- **45 seconds before** the "flubber" keyword (configurable)
- **10 seconds after** the "flubber" keyword (configurable)

This gives you enough context to identify exactly where the mistake started.

### Flubber Settings

**Window Configuration:**
- **Before window:** Seconds of audio before "flubber" (default: 45)
- **After window:** Seconds of audio after "flubber" (default: 10)

**Fuzzy Matching:**
- Optional tolerance for mishearing (e.g., "flober", "rubber")
- Useful if transcription isn't perfect

### Best Practices

- ✅ **Say "flubber" clearly:** Enunciate so it's detected
- ✅ **Pause briefly:** Before and after saying "flubber"
- ✅ **Review all snippets:** Make sure cuts are correct
- ✅ **Mark exact start:** Precisely indicate where mistake began
- ✅ **Test first:** Try with a short recording
- ❌ Don't mumble "flubber"
- ❌ Don't say it while others are talking
- ❌ Don't skip the review step (auto-cut might be wrong)
          `
        },
        {
          title: 'AI Show Notes',
          description: 'Automatically generate episode descriptions',
          link: '#show-notes',
          content: `
## AI Show Notes Generation

### What Are AI Show Notes?

The platform can automatically generate:
- **Episode summary** (1-2 paragraphs)
- **Key topics discussed**
- **Timestamps** for main segments
- **Quotes** from the episode
- **Keywords** for SEO

### How to Enable

1. **In Template Editor:**
   - Go to Templates tab
   - Edit your template
   - Toggle "Generate show notes with AI"
   - Save template

2. **Per Episode:**
   - Create or edit episode
   - Check "Generate show notes"
   - Notes created during assembly

### Editing AI-Generated Notes

After generation, you can:
- Edit the text manually
- Add/remove sections
- Adjust timestamps
- Change formatting
- Add custom links

### Tips for Better Results

- ✅ **Use clear speech:** AI transcription works best with clean audio
- ✅ **Mention topics explicitly:** Say "Today we're discussing X"
- ✅ **Include guest names:** "My guest today is [Name]"
- ✅ **Provide context:** Briefly intro each segment
- ❌ Don't rely on AI 100% (always review)
- ❌ Don't use for episodes with poor audio quality

### Show Notes Style

Choose from presets:
- **Professional:** Formal tone, full sentences
- **Casual:** Conversational, bullet points
- **Detailed:** Long form with timestamps
- **Brief:** Short summary only
          `
        }
      ]
    },
    {
      category: 'Media & Templates',
      icon: FileAudio,
      description: 'Organize your audio files and create reusable templates',
      items: [
        {
          title: 'Media Library Management',
          description: 'Organizing your audio files',
          link: '#media',
          content: `
## Media Library Management

### Categories

**Intro:** Opening segments for episodes  
**Outro:** Closing segments for episodes  
**Music:** Background music tracks  
**SFX:** Sound effects  
**Main Content:** Your episode recordings  
**Commercial:** Ad reads or sponsorships  

### Uploading to Library

1. **Go to Media tab**
2. **Click "Upload"**
3. **Select category** from dropdown
4. **Choose file(s)** from computer
5. **Add friendly name** (optional but recommended)
6. **Click "Upload"**

### Using Library Items

- **In Templates:** Select from dropdowns
- **In Episodes:** Choose intro/outro when creating
- **In Editor:** Drag and drop onto timeline
- **Quick preview:** Click play icon to listen

### Storage Limits

- **Free Plan:** 1 GB total storage
- **Pro Plan:** 10 GB total storage
- **Enterprise:** Unlimited storage

### Best Practices

- ✅ **Name files clearly:** "Intro_Show123_v2.mp3"
- ✅ **Delete unused files:** Keep library organized
- ✅ **Use standard formats:** MP3 for compatibility
- ✅ **Keep originals:** Don't delete source files
- ✅ **Tag with keywords:** Makes searching easier
          `
        },
        {
          title: 'Template Creation',
          description: 'Building reusable episode structures',
          link: '#templates',
          content: `
## Template Creation

### What Are Templates?

Templates define the structure of your episodes:
- Intro/outro audio
- Background music settings
- AI configuration
- Default episode settings
- Publishing preferences

### Creating a Template

1. **Go to Templates tab**
2. **Click "Create Template"**
3. **Name your template** (e.g., "Standard Episode")
4. **Configure sections:**
   - Intro audio (select from library or upload)
   - Outro audio (select from library or upload)
   - Background music (optional)
   - Music ducking rules
5. **Set AI options:**
   - Generate show notes? (yes/no)
   - TTS voice selection
   - Editing preferences
6. **Save template**

### Using Templates

When creating a new episode:
1. Select template from dropdown
2. Episode inherits all template settings
3. Override any settings per-episode if needed

### Template Settings

**Audio:**
- Intro/outro files
- Music track
- Volume levels
- Fade in/out duration

**Processing:**
- Auto-run Flubber
- Auto-run Intern
- Transcription enabled
- Show notes generation

**Publishing:**
- Default category
- Explicit content flag
- Auto-publish on completion
          `
        },
        {
          title: 'Background Music & Audio Mixing',
          description: 'Add music and control audio levels',
          link: '#background-music',
          content: `
## Background Music & Audio Mixing

### Adding Background Music

1. **In Template Editor:**
   - Go to Templates tab
   - Edit your template
   - Scroll to "Background Music" section
   - Select music from library or upload new

2. **Per Episode (Override):**
   - Create/edit episode
   - Toggle "Custom music for this episode"
   - Choose different track

### Music Ducking

Ducking automatically lowers music volume when you're speaking:

**Ducking Settings:**
- **Level:** How much to reduce music (e.g., -12 dB)
- **Attack:** How fast music drops when speech starts (0.5s recommended)
- **Release:** How fast music returns when speech stops (1.0s recommended)

**Example Settings:**
- **Subtle ducking:** -6 dB, 1.0s attack, 2.0s release
- **Moderate ducking (recommended):** -12 dB, 0.5s attack, 1.0s release
- **Aggressive ducking:** -18 dB, 0.3s attack, 0.5s release

### Volume Normalization

Normalization ensures consistent volume across your episode:

- **Target Level:** -16 LUFS (industry standard for podcasts)
- **Peak Limiting:** Prevents audio from clipping
- **Auto-applied:** Enabled by default in templates

### Audio Formats & Quality

**Supported Input Formats:**
- MP3 (recommended for music)
- WAV (best quality, larger files)
- M4A/AAC
- FLAC (lossless)
- OGG

**Output Format:**
- MP3, 128 kbps (spoken word)
- MP3, 192 kbps (music-heavy shows)
- Mono for single-speaker
- Stereo for multi-speaker or music

### Tips for Great Audio

✅ **Choose instrumental music:** Avoid lyrics that compete with speech  
✅ **Use consistent ducking:** Keeps listener experience smooth  
✅ **Test with headphones:** Catch issues that speakers miss  
✅ **Match music to tone:** Upbeat for comedy, mellow for storytelling  
✅ **Fade music:** Use fade in/out at episode start/end  
❌ Don't use copyrighted music (use library or royalty-free)  
❌ Don't make music too loud (should enhance, not overpower)
          `
        },
        {
          title: 'Podcast Website Builder',
          description: 'Create a custom website for your podcast',
          link: '#website-builder',
          content: `
## Podcast Website Builder

### What is the Website Builder?

Create a professional podcast website with zero coding:
- Custom domain or free subdomain
- Responsive design (mobile-friendly)
- Automatic episode listings
- Player embedded in each page
- Contact form and links
- SEO-optimized

### Getting Started

1. **Go to Settings > Website**
2. **Click "Build Website"**
3. **Choose domain:**
   - Free: yourshow.donecast.com
   - Custom: yourshow.com (requires DNS setup)
4. **Select theme/style**
5. **Customize sections**

### Website Sections

**Header:**
- Show logo
- Navigation menu
- Social media links

**Homepage:**
- Hero section with show description
- Latest episodes
- Subscribe buttons (Apple, Spotify, etc.)

**Episodes Page:**
- All episodes in grid or list
- Search and filter
- Embedded player for each

**About Page:**
- Host bio
- Show description
- Contact information

**Contact Form:**
- Let listeners reach you
- Submissions emailed to you

### Customization Options

**Colors & Branding:**
- Primary color (buttons, links)
- Secondary color (accents)
- Background color
- Text color
- Upload logo and favicon

**Layout:**
- Grid or list view for episodes
- Sidebar or full-width
- Card style (bordered, shadowed, etc.)

**Content:**
- Add custom pages (About, Sponsors, etc.)
- Edit all text and headings
- Rearrange sections with drag-and-drop

### Publishing Your Website

1. **Preview changes** before publishing
2. **Click "Publish Website"**
3. **Site goes live** within 2 minutes
4. **Share URL** on social media

### Custom Domain Setup (Pro)

1. **Purchase domain** from registrar (Namecheap, GoDaddy, etc.)
2. **Add DNS records:**
   - Type: CNAME
   - Name: www (or @)
   - Value: podcasts.donecast.com
3. **In Website Builder:** Enter your domain
4. **Verify:** Takes 24-48 hours for DNS to propagate

### SEO & Discovery

The website builder automatically includes:
- ✅ Podcast RSS feed link
- ✅ Schema.org markup for podcasts
- ✅ Open Graph tags for social sharing
- ✅ Sitemap for search engines
- ✅ Mobile-optimized meta tags

### Tips for a Great Website

✅ **Use high-quality cover art:** First impression matters  
✅ **Write compelling show description:** Hook visitors immediately  
✅ **Add host photos:** Builds personal connection  
✅ **Include call-to-action:** "Subscribe on Apple Podcasts"  
✅ **Update regularly:** Add new episodes as published  
❌ Don't clutter with too many sections  
❌ Don't forget mobile preview (most visitors on mobile)
          `
        }
      ]
    },
    {
      category: 'Account & Billing',
      icon: CreditCard,
      description: 'Manage your subscription, usage, and billing information',
      items: [
        {
          title: 'Subscription Plans',
          description: 'Understanding plan features and limits',
          link: '#plans',
          content: `
## Subscription Plans

### Free Plan
- ✅ 5 episodes per month
- ✅ 1 GB storage
- ✅ Basic AI features
- ✅ RSS feed hosting
- ❌ No analytics
- ❌ No Intern/Flubber
- ❌ No custom branding

### Pro Plan ($19/month)
- ✅ Unlimited episodes
- ✅ 10 GB storage
- ✅ All AI features
- ✅ Advanced analytics
- ✅ Intern & Flubber
- ✅ Priority support
- ✅ Custom RSS slug

### Enterprise Plan (Custom pricing)
- ✅ Everything in Pro
- ✅ Unlimited storage
- ✅ White-label option
- ✅ Dedicated support
- ✅ Custom integrations
- ✅ SLA guarantee

### Upgrading

1. **Go to Settings > Billing**
2. **Click "Upgrade Plan"**
3. **Select tier**
4. **Enter payment info**
5. **Confirm purchase**

Upgrade takes effect immediately!

### Downgrading

Contact support to downgrade. Note:
- New limits apply at next billing cycle
- Existing content remains accessible
- May need to delete files if over new storage limit
          `
        },
        {
          title: 'How Our Credit System Works',
          description: 'Understanding credits, costs, and refunds',
          link: '#credits',
          content: `
## How Our Credit System Works

We like to keep things simple and transparent — you always know what you're getting and what it costs.

### Recording and Uploading

Every second of audio you record or upload uses **1 credit**.  

Want studio-quality sound? Our premium processing automatically upgrades lower-quality recordings (like from webcams or phones) for **just 1 extra credit per second**.

### Editing and Finishing

When you're ready to assemble your final episode, that's where the magic happens.  

Final audio assembly costs **3 credits per second** — covering your intros, outros, and all the polishing that makes your episode shine.

### Plan Overview

Choose the plan that fits your production style:

- **Hobby:** 28,800 credits = about 2 hours of finished audio  

- **Creator:** 72,000 credits = about 5 hours  

- **Pro:** 172,800 credits = about 12 hours  

- **Executive:** 288,000 credits = about 20 hours  

### Optional Features

Enhance your workflow with add-ons:

- **AI Titles, Descriptions & Tags:** 1–3 credits each — perfect for quick content creation.  

- **Intern Feature:** 1 credit per answer — your built-in helper.  

- **Text-to-Speech:** 12–15 credits per second — natural, studio-grade voices for intros, outros, or responses.

### Refunds and Flexibility

We're still in alpha, which means we're improving fast and keeping things fair.  

If something goes wrong, just request a refund in your subscription page — we'll make it right.

You can also undo and get credits back:

- Delete within **24 hours** → refund of 2 out of every 3 credits.  

- Delete within **7 days** → refund of 1 out of every 3 credits.  

- After 7 days, refunds close automatically.

Simple, fair, and transparent — so you can focus on creating, not calculating.
          `
        },
        {
          title: 'Usage & Minutes',
          description: 'How usage is calculated',
          link: '#usage',
          content: `
## Usage & Minutes

### What Counts as Usage?

**Included in Minutes:**
- TTS (text-to-speech) generation
- AI show notes generation
- Transcription time
- Intern analysis
- Flubber processing

**NOT Counted:**
- Uploading files
- Downloading episodes
- Listening to previews
- Editing metadata
- Dashboard access

### Monthly Minute Allocation

**Free Plan:** 60 minutes  
**Pro Plan:** 600 minutes  
**Enterprise:** Unlimited  

### Checking Your Usage

1. **Go to Settings > Billing**
2. **View "Usage This Month"**
3. **See breakdown** by feature type
4. **Track toward monthly limit**

### What Happens When You Run Out?

- You can still upload and publish
- AI features disabled until next billing cycle
- Transcription queued (processed next month)
- OR purchase additional minutes ($0.10/min)

### Tips to Conserve Minutes

- ✅ **Manually edit show notes** instead of AI generation
- ✅ **Upload pre-edited audio** (less processing needed)
- ✅ **Use templates** to reduce per-episode setup
- ✅ **Batch process episodes** to minimize overhead
          `
        }
      ]
    },
    {
      category: 'Troubleshooting',
      icon: AlertCircle,
      description: 'Solutions to common problems and how to get help',
      items: [
        {
          title: 'Common Issues',
          description: 'Solutions to frequent problems',
          link: '#common-issues',
          content: `
## Common Issues & Solutions

### Upload Failures

**Problem:** File won't upload or gets stuck at 99%

**Solutions:**
- Check file size (must be under limit for your plan)
- Verify file format (MP3, WAV, M4A, FLAC, OGG only)
- Try different browser (Chrome recommended)
- Disable browser extensions (especially ad blockers)
- Check internet connection speed
- Try uploading smaller file first

### Processing Errors

**Problem:** Episode stuck in "Processing" for > 10 minutes

**Solutions:**
- Refresh the page and check again
- Wait 30 minutes for large files
- Check Cloud Run logs (Settings > Advanced)
- Contact support with episode ID

### Audio Quality Issues

**Problem:** Published episode sounds distorted or quiet

**Solutions:**
- Upload higher quality source (44.1kHz+ recommended)
- Check template music volume (shouldn't overpower voice)
- Adjust ducking rules in template
- Normalize audio before uploading
- Don't exceed 0 dB peaks in source file

### RSS Feed Not Updating

**Problem:** New episode doesn't show in Apple Podcasts after 24 hours

**Solutions:**
- Verify episode is actually "Published" (not just processed)
- Check RSS feed URL is correct in podcast platform
- Force refresh in platform settings
- Wait 24-48 hours (some platforms are slow)
- Validate RSS feed at podba.se/validate

### Login Issues

**Problem:** Can't log in or session expired

**Solutions:**
- Clear browser cookies and cache
- Try incognito/private browsing mode
- Reset password via email
- Check if email is verified
- Contact support if account locked
          `
        },
        {
          title: 'Getting Help',
          description: 'How to contact support',
          link: '#support',
          content: `
## Getting Help

### Self-Service Resources

1. **This Guide:** Start here for most questions
2. **In-App Tooltips:** Hover over ⓘ icons for quick help
3. **Video Tutorials:** [Coming Soon]
4. **Community Forum:** [Coming Soon]

### Contact Support

**For Technical Issues:**
- Email: support@donecast.com
- Include: Account email, episode ID (if applicable), screenshot
- Response time: 24-48 hours

**For Billing Questions:**
- Email: billing@donecast.com
- Include: Account email, invoice number (if applicable)
- Response time: 24 hours

**For Feature Requests:**
- Email: feedback@donecast.com
- Or use the in-app feedback button
- We review all suggestions!

### What to Include in Support Requests

✅ **Do include:**
- Your account email
- Specific episode or file that has issue
- Steps to reproduce the problem
- Screenshots or error messages
- Browser and OS version

❌ **Don't include:**
- Your password (we'll never ask for it)
- Sensitive personal info in screenshots
- Multiple unrelated issues in one email

### Emergency Support

For urgent production issues affecting live podcasts:
- Email: urgent@donecast.com (Pro/Enterprise only)
- Expected response: 4 hours during business hours
- Available: Monday-Friday, 9am-5pm PT
          `
        }
      ]
    }
  ];

  const filteredGuides = guides.map(category => ({
    ...category,
    items: category.items.filter(item =>
      searchTerm.trim() === '' ||
      item.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      item.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
      category.category.toLowerCase().includes(searchTerm.toLowerCase())
    )
  })).filter(category => category.items.length > 0);

  const [selectedGuide, setSelectedGuide] = useState(null);
  const [expandedCategories, setExpandedCategories] = useState(guides.map(g => g.category));

  const handleGuideClick = (guide) => {
    setSelectedGuide(guide);
  };

  const toggleCategory = (categoryName) => {
    setExpandedCategories(prev => 
      prev.includes(categoryName) 
        ? prev.filter(c => c !== categoryName)
        : [...prev, categoryName]
    );
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b sticky top-0 z-10">
        <div className="max-w-7xl mx-auto px-4 py-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-4">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => navigate(-1)}
              >
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back
              </Button>
              <div className="flex items-center gap-2">
                <BookOpen className="h-5 w-5 text-primary" />
                <h1 className="text-xl font-bold">Guides</h1>
              </div>
            </div>
            <div className="relative max-w-xs w-full">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                type="text"
                placeholder="Search..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10 h-9 text-sm"
              />
            </div>
          </div>
        </div>
      </div>

      {/* Main Content */}
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="flex gap-6">
          {/* Left Sidebar - Outline */}
          <div className="w-64 flex-shrink-0">
            <Card className="sticky top-24">
              <CardContent className="p-4">
                <div className="space-y-1">
                  {filteredGuides.map((category, idx) => {
                    const CategoryIcon = category.icon || BookOpen;
                    const isExpanded = expandedCategories.includes(category.category);
                    
                    return (
                      <div key={idx}>
                        <button
                          onClick={() => toggleCategory(category.category)}
                          className="flex items-center gap-2 w-full px-2 py-1.5 text-left rounded hover:bg-gray-100 transition-colors"
                        >
                          <CategoryIcon className="h-3.5 w-3.5 text-gray-500 flex-shrink-0" />
                          <span className="text-xs font-medium text-gray-700 flex-1">
                            {category.category}
                          </span>
                          <ChevronRight 
                            className={`h-3.5 w-3.5 text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`} 
                          />
                        </button>
                        
                        {isExpanded && (
                          <div className="ml-6 mt-1 space-y-0.5">
                            {category.items.map((guide, gIdx) => (
                              <button
                                key={gIdx}
                                onClick={() => handleGuideClick(guide)}
                                className={`w-full text-left px-2 py-1 rounded text-xs transition-colors ${
                                  selectedGuide?.title === guide.title
                                    ? 'bg-primary/10 text-primary font-medium'
                                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'
                                }`}
                              >
                                {guide.title}
                              </button>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>

                {filteredGuides.length === 0 && (
                  <div className="text-center py-8">
                    <p className="text-xs text-gray-500">
                      No guides found
                    </p>
                    <Button
                      variant="link"
                      size="sm"
                      onClick={() => setSearchTerm('')}
                      className="mt-2 text-xs"
                    >
                      Clear search
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Right Content Area */}
          <div className="flex-1 min-w-0">
            {selectedGuide ? (
              <Card>
                <CardHeader>
                  <CardTitle className="text-2xl">{selectedGuide.title}</CardTitle>
                  <p className="text-sm text-muted-foreground">{selectedGuide.description}</p>
                </CardHeader>
                <CardContent>
                  <div className="prose prose-sm max-w-none">
                    {selectedGuide.content.split('\n').map((line, idx) => {
                      if (line.startsWith('## ')) {
                        return <h2 key={idx} className="text-2xl font-bold mt-6 mb-3">{line.replace('## ', '')}</h2>;
                      } else if (line.startsWith('### ')) {
                        return <h3 key={idx} className="text-xl font-semibold mt-4 mb-2">{line.replace('### ', '')}</h3>;
                      } else if (line.startsWith('#### ')) {
                        return <h4 key={idx} className="text-lg font-medium mt-3 mb-2">{line.replace('#### ', '')}</h4>;
                      } else if (line.startsWith('- ')) {
                        return <li key={idx} className="ml-6">{line.replace('- ', '')}</li>;
                      } else if (line.startsWith('**') && line.endsWith('**')) {
                        return <p key={idx} className="font-bold mt-3">{line.replace(/\*\*/g, '')}</p>;
                      } else if (line.trim() === '') {
                        return <br key={idx} />;
                      } else {
                        return <p key={idx} className="my-2">{line}</p>;
                      }
                    })}
                  </div>
                </CardContent>
              </Card>
            ) : (
              <Card>
                <CardContent className="py-16 text-center">
                  <BookOpen className="h-16 w-16 text-gray-300 mx-auto mb-4" />
                  <h2 className="text-xl font-semibold text-gray-700 mb-2">
                    Select a guide to get started
                  </h2>
                  <p className="text-sm text-gray-500 max-w-md mx-auto">
                    Choose a topic from the left sidebar to view detailed instructions and information.
                  </p>
                </CardContent>
              </Card>
            )}

            {/* Help Card */}
            <Card className="mt-6">
              <CardContent className="py-6">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="font-semibold">Still need help?</h3>
                    <p className="text-sm text-muted-foreground mt-1">
                      Can't find what you're looking for? Contact our support team.
                    </p>
                  </div>
                  <Button onClick={() => navigate('/contact')}>
                    Contact Support
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
