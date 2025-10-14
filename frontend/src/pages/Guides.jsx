import { useState } from 'react';
import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { ArrowLeft, BookOpen, Search, ExternalLink, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export default function Guides() {
  const navigate = useNavigate();
  const [searchTerm, setSearchTerm] = useState('');

  const guides = [
    {
      category: 'Getting Started',
      items: [
        {
          title: 'Quick Start Guide',
          description: 'Get up and running in 5 minutes',
          link: '#quick-start',
          content: `
## Quick Start Guide

Welcome to Podcast Plus Plus! Here's how to create your first episode:

### 1. Complete Onboarding
- Click through the onboarding wizard
- Set up your podcast name and description
- Choose your intro/outro audio
- Select a voice for AI features

### 2. Upload Your Audio
- Go to **Episodes** tab
- Click "Create Episode"
- Upload your main content audio file
- Add episode title and description

### 3. Process & Publish
- Click "Assemble Episode" to process
- Preview the final result
- Hit "Publish" when ready
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
- **Create new episodes** with one click
- **Edit or delete** existing episodes
- **Monitor processing status** (pending, processing, published)

### Templates Tab
- **Design reusable structures** for your episodes
- **Set default intro/outro** audio
- **Configure AI settings** for show notes
- **Save time** by reusing templates

### Media Library
- **Upload and manage** all audio files
- **Organize by category** (intro, outro, music, SFX, main content)
- **Preview audio** before using
- **Delete unused files** to free up space

### Analytics
- **Track downloads** and plays
- **See geographic data** of your listeners
- **Monitor growth** over time
- **Identify top episodes**

### Settings
- **Edit podcast details** (name, description, cover art)
- **Manage account** (email, password, subscription)
- **Configure RSS feed** settings
- **Set up billing** and view usage
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
- **Import from Spreaker** (if you have an existing show)
- **Create from scratch** (recommended for new podcasters)

#### Step 2: Podcast Details
- **Show Name:** Keep it memorable and searchable
- **Description:** Explain what your podcast is about (250 words max)
- **Category:** Choose the most relevant category
- **Cover Art:** Upload 1400x1400px image (required for podcast platforms)

#### Step 3: Template Setup
- **Intro Audio:** Upload or generate with AI voice
- **Outro Audio:** Upload or generate with AI voice
- **Background Music:** Choose from library or upload your own
- **AI Settings:** Configure automatic show notes generation

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
        }
      ]
    },
    {
      category: 'AI Features',
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
          title: 'Filler Word Removal (Flubber)',
          description: 'Automatically remove ums, ahs, and pauses',
          link: '#flubber',
          content: `
## Filler Word Removal: Flubber

### What is Flubber?

Flubber analyzes your audio and identifies:
- Filler words ("um," "uh," "like," "you know")
- Long pauses (> 2 seconds)
- Repeated phrases
- False starts

### How to Use Flubber

1. **Upload audio** to episode
2. **Click "Run Flubber"** in episode details
3. **Wait for analysis** (1-2 minutes)
4. **Review snippets:** See all detected fillers with timestamps
5. **Expand/collapse** to hear context around each filler
6. **Select fillers** to remove (or keep)
7. **Apply changes** and assemble episode

### Flubber Settings

**Sensitivity:**
- **Low:** Only obvious, long fillers
- **Medium:** Standard detection (recommended)
- **High:** Aggressive removal (may cut too much)

**Filler Types:**
- Um/Uh/Er
- Like/You know
- Long pauses (> X seconds)
- Repeated words

### Best Practices

- ✅ **Review before applying:** Don't auto-remove all
- ✅ **Keep some fillers:** Natural speech needs a few
- ✅ **Test with one episode first:** Find your preferred settings
- ✅ **Listen to preview:** Make sure edits sound natural
- ❌ Don't remove ALL fillers (sounds robotic)
- ❌ Don't use highest sensitivity unless needed
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
        }
      ]
    },
    {
      category: 'Account & Billing',
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
- Email: support@podcastplusplus.com
- Include: Account email, episode ID (if applicable), screenshot
- Response time: 24-48 hours

**For Billing Questions:**
- Email: billing@podcastplusplus.com
- Include: Account email, invoice number (if applicable)
- Response time: 24 hours

**For Feature Requests:**
- Email: feedback@podcastplusplus.com
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
- Email: urgent@podcastplusplus.com (Pro/Enterprise only)
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

  const [expandedGuide, setExpandedGuide] = useState(null);

  const handleGuideClick = (guide) => {
    setExpandedGuide(expandedGuide?.title === guide.title ? null : guide);
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-6xl mx-auto">
        <Button
          variant="ghost"
          className="mb-4"
          onClick={() => navigate(-1)}
        >
          <ArrowLeft className="h-4 w-4 mr-2" />
          Back
        </Button>

        <Card className="mb-6">
          <CardHeader>
            <div className="flex items-center gap-3">
              <BookOpen className="h-6 w-6 text-primary" />
              <CardTitle>Guides & Documentation</CardTitle>
            </div>
            <p className="text-sm text-muted-foreground mt-2">
              Everything you need to know about using Podcast Plus Plus
            </p>
          </CardHeader>
          <CardContent>
            <div className="relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                type="text"
                placeholder="Search guides..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
          </CardContent>
        </Card>

        {expandedGuide ? (
          <Card>
            <CardHeader>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setExpandedGuide(null)}
                className="mb-2"
              >
                <ArrowLeft className="h-4 w-4 mr-2" />
                Back to all guides
              </Button>
              <CardTitle>{expandedGuide.title}</CardTitle>
              <p className="text-sm text-muted-foreground">{expandedGuide.description}</p>
            </CardHeader>
            <CardContent>
              <div className="prose prose-sm max-w-none">
                {expandedGuide.content.split('\n').map((line, idx) => {
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
          <div className="space-y-6">
            {filteredGuides.map((category, idx) => (
              <Card key={idx}>
                <CardHeader>
                  <CardTitle className="text-lg">{category.category}</CardTitle>
                </CardHeader>
                <CardContent>
                  <div className="space-y-3">
                    {category.items.map((guide, gIdx) => (
                      <button
                        key={gIdx}
                        onClick={() => handleGuideClick(guide)}
                        className="w-full text-left p-4 rounded-lg border hover:border-primary hover:bg-primary/5 transition-colors group"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex-1">
                            <h3 className="font-semibold text-base group-hover:text-primary transition-colors">
                              {guide.title}
                            </h3>
                            <p className="text-sm text-muted-foreground mt-1">
                              {guide.description}
                            </p>
                          </div>
                          <ChevronRight className="h-5 w-5 text-gray-400 group-hover:text-primary transition-colors" />
                        </div>
                      </button>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}

            {filteredGuides.length === 0 && (
              <Card>
                <CardContent className="py-12 text-center">
                  <p className="text-muted-foreground">
                    No guides found matching "{searchTerm}"
                  </p>
                  <Button
                    variant="link"
                    onClick={() => setSearchTerm('')}
                    className="mt-2"
                  >
                    Clear search
                  </Button>
                </CardContent>
              </Card>
            )}
          </div>
        )}

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
  );
}
