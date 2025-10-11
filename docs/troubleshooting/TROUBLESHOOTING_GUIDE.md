# Troubleshooting Guide

**Podcast Plus Plus - Problem Resolution**  
**Version:** 2.0  
**Last Updated:** October 11, 2025

---

## Table of Contents

1. [Quick Diagnostics](#quick-diagnostics)
2. [Upload Issues](#upload-issues)
3. [Transcription Issues](#transcription-issues)
4. [Processing Issues](#processing-issues)
5. [Publishing Issues](#publishing-issues)
6. [Audio Quality Issues](#audio-quality-issues)
7. [Account & Billing Issues](#account--billing-issues)
8. [Performance Issues](#performance-issues)
9. [Error Messages](#error-messages)
10. [Getting Additional Help](#getting-additional-help)

---

## Quick Diagnostics

### Is the platform working?

**Check system status:**
1. Visit https://app.podcastplusplus.com
2. Look for system status banner (appears if issues)
3. Try logging in
4. Check Mike (AI assistant) is responsive

**Common quick fixes:**
- ✅ Refresh the page (Ctrl+F5 for hard refresh)
- ✅ Clear browser cache
- ✅ Try incognito/private mode
- ✅ Check internet connection
- ✅ Try different browser

### Can't log in?

**Symptoms:** Login button doesn't work, stuck on login screen, "Invalid credentials"

**Solutions:**
1. **Using Google OAuth?** 
   - Verify you're using the correct Google account
   - Check popup blockers aren't blocking OAuth window
   - Try "Sign in with Google" button

2. **Password login:**
   - Verify email is correct
   - Use "Forgot Password" to reset
   - Check email for reset link (check spam folder)

3. **Still stuck:**
   - Clear cookies for podcastplusplus.com
   - Try different browser
   - Contact support@podcastplusplus.com

---

## Upload Issues

### Upload Fails or Gets Stuck

**Problem:** File upload progress bar stuck at X%, "Upload failed", or silent failure

**Diagnostic steps:**
1. **Check file size** - Max 500MB per file
   - Right-click file → Properties → Size
   - If over 500MB, compress or split

2. **Check file format** - Must be audio
   - Supported: MP3, WAV, M4A, OGG, FLAC
   - Not supported: Video files, ZIP, documents

3. **Check internet connection**
   - Large files need stable connection
   - Try upload on better network

4. **Check browser console** (for developers)
   - Press F12 → Console tab
   - Look for error messages

**Solutions:**

**If file too large:**
```
Option 1: Compress audio
- Use Audacity or similar
- Export at lower bitrate (128 kbps instead of 320 kbps)

Option 2: Split episode
- Create two parts
- Upload separately
- Stitch in template
```

**If unsupported format:**
- Convert to MP3 using Audacity, FFmpeg, or online converter
- Re-upload converted file

**If connection drops:**
- Upload on wired connection if possible
- Disable VPN temporarily
- Try during off-peak hours

### Upload Succeeds But File Not Found

**Problem:** Upload shows "100% Complete" but file doesn't appear in Media Library or episode creator

**Causes:**
1. Upload completed but file processing pending
2. Category filter hiding file
3. Database sync delay

**Solutions:**
1. **Wait 30 seconds**, then refresh page
2. **Check Media tab** directly (not just episode creator)
3. **Check category filter** - Make sure "All" or correct category selected
4. **Re-upload** if file still missing after 2 minutes

### "Uploaded file not found" Error

**Problem:** Error when trying to use file in Intern, Flubber, or episode assembly

**Root cause:** File reference in database but not accessible in storage

**Solutions:**
1. **Refresh page** - Clears stale references
2. **Re-upload file** - Creates new storage reference
3. **Check Media Library** - Verify file actually exists
4. **Contact support** if persistent - May be storage sync issue

---

## Transcription Issues

### Transcript Stuck at "Processing"

**Problem:** Transcript shows "Processing..." for extended time (>30 minutes)

**Normal processing time:** 2-3 minutes per hour of audio

**Diagnostic steps:**
1. **How long has it been?**
   - Under 10 min for 1-hour audio → Still processing normally
   - Over 30 min → Likely stuck

2. **Check file size**
   - Larger files (>200MB) take longer
   - 3-hour episode might take 10-15 minutes

3. **Check audio quality**
   - Very low quality or corrupted audio can fail
   - Non-standard formats may time out

**Solutions:**

**If under 30 minutes:**
- Wait patiently
- Transcription happens in background
- You'll see notification when complete

**If over 30 minutes:**
1. **Refresh page** - Transcript may be ready, status not updated
2. **Check Episodes tab** - Episode status should show "draft" or "published", not "processing"
3. **Re-upload file** if still stuck after refresh
4. **Contact support** with episode ID

### Transcript Ready But Status Shows "Processing"

**Problem:** After page refresh or redeployment, drafts show "Processing" even though transcript is ready

**Cause:** localStorage cached old status, no server verification on mount

**Solution:**
- **Refresh page** - Fixed in v2.0, now auto-checks server
- If still showing processing after refresh:
  - Clear browser cache
  - Hard refresh (Ctrl+F5)

### Transcript Accuracy Issues

**Problem:** Transcript has many errors, wrong words, missing content

**Causes:**
1. Poor audio quality (background noise, echo)
2. Heavy accents or unusual vocabulary
3. Multiple overlapping speakers
4. Music playing during speech

**Solutions:**

**Improve audio quality before upload:**
- Record in quiet environment
- Use good microphone (not built-in laptop mic)
- Reduce background noise
- Speak clearly, not too fast

**For existing transcript:**
- Transcript editing coming in future version
- For now, generate AI content (works despite errors)
- Critical corrections: re-record segment

---

## Processing Issues

### Episode Stuck in "Processing"

**Problem:** Episode shows "Processing" status for hours, assembly never completes

**Normal processing time:** 30-90 seconds for typical episode

**Diagnostic steps:**
1. **How long has it been?**
   - Under 2 minutes → Normal, wait
   - 2-10 minutes → May be large/complex episode
   - Over 10 minutes → Likely stuck

2. **Check episode complexity:**
   - Many segments → Longer processing
   - Large audio files (>200MB) → Longer
   - Multiple music rules → Longer

3. **Check system status:**
   - Is platform generally slow?
   - Are other episodes processing normally?

**Solutions:**

**If under 10 minutes:**
- Wait and refresh periodically
- Processing happens in background queue

**If over 10 minutes:**
1. **Refresh page** - Status may be outdated
2. **Check Episodes tab** - Look for error message
3. **Check episode status API:**
   ```
   GET /api/episodes/{episode_id}
   Look for "status" and "error_message" fields
   ```
4. **Retry assembly:**
   - Go to episode editor
   - Make small change (add space to title)
   - Save
   - Re-assemble

**If consistently failing:**
- Check audio files are valid (play in media player)
- Try simpler template (fewer segments)
- Contact support with episode ID

### Intern/Flubber Fails

**Problem:** "Prepare with Intern" or "Apply Flubber" fails with error

**Common errors:**
- "uploaded file not found"
- "Audio processing failed"
- "No editing commands detected" (Intern)

**Solutions:**

**"Uploaded file not found":**
1. Verify file in Media Library
2. Re-upload audio file
3. Wait 30 seconds for sync
4. Try again

**"Audio processing failed":**
1. Check file format (must be audio)
2. Check file isn't corrupted (play in media player)
3. Try with smaller file
4. Contact support if persistent

**"No editing commands detected" (Intern):**
- This is normal if you didn't say commands
- Intern requires spoken phrases like "cut that out"
- Try recording with intentional commands
- Or skip Intern if no commands needed

---

## Publishing Issues

### RSS Feed Not Updating

**Problem:** Published episode doesn't appear in podcast apps, RSS feed shows old episodes

**Normal behavior:** RSS updates within 5 minutes, podcast apps cache for 15-60 minutes

**Diagnostic steps:**
1. **Check episode status** - Must be "published", not "draft"
2. **Check RSS feed directly** - Open feed URL in browser
3. **Check podcast app** - Some apps cache aggressively

**Solutions:**

**If episode not in RSS feed (direct browser check):**
1. **Verify published status:**
   - Go to Episodes tab
   - Find episode
   - Status should show "Published"
   - If "Draft", click "Publish"

2. **Check publication date:**
   - If scheduled for future, won't appear yet
   - Check "Published At" field

3. **Regenerate feed:**
   - Make small edit to episode (add space to description)
   - Save
   - Wait 5 minutes
   - Check RSS again

**If episode in RSS but not in app:**
- **Podcast app caching** - Normal
- Force refresh in app (pull down to refresh)
- Wait 30-60 minutes for automatic refresh
- Try different podcast app to verify

### Episode Appears But Audio Won't Play

**Problem:** Episode listed in podcast app but audio fails to load or play

**Causes:**
1. Signed URL expired (>7 days old)
2. Storage permissions issue
3. Audio file format incompatibility
4. File not actually uploaded

**Solutions:**

1. **Check signed URL:**
   - URLs auto-regenerate every 7 days
   - If episode older than 7 days, trigger regeneration:
     - Edit episode metadata
     - Save
     - RSS updates with new URL

2. **Check audio file exists:**
   - Go to episode in Episodes tab
   - Play audio in platform (should work)
   - If doesn't play in platform, file missing

3. **Re-publish episode:**
   - Edit episode
   - Re-assemble (if audio changed)
   - Publish again

### Can't Submit RSS to Apple/Spotify

**Problem:** Apple Podcasts Connect or Spotify rejects RSS feed

**Common rejection reasons:**

**Apple Podcasts:**
- Missing show artwork (must be 1400x1400 - 3000x3000)
- Missing required iTunes tags
- Invalid enclosure (audio URL)
- Explicit content not flagged properly

**Spotify:**
- RSS format issues
- Missing show description
- Invalid audio files

**Solutions:**

1. **Verify RSS feed is valid:**
   - Use validator: https://castfeedvalidator.com
   - Paste your RSS URL
   - Fix any errors shown

2. **Check required fields:**
   - Show title and description
   - Show artwork (1400x1400 minimum)
   - Episode audio file exists and plays
   - Contact email (iTunes)

3. **Verify RSS URL is accessible:**
   - Open in browser (should show XML)
   - Not redirecting or requiring login
   - HTTPS (not HTTP)

4. **Common fixes:**
   - Re-upload show artwork at correct size
   - Add missing description
   - Set explicit content flag if needed
   - Ensure at least 1 published episode

---

## Audio Quality Issues

### Low Volume

**Problem:** Assembled episode audio too quiet

**Causes:**
1. Source audio recorded too quietly
2. Music too loud (drowning out speech)
3. Normalization not working

**Solutions:**

1. **Check source audio:**
   - Play original file - if quiet there, problem is source
   - Re-record at higher input level
   - Use audio editor to boost volume before upload

2. **Check music volume:**
   - Music rules have `volume_db` setting
   - Try lower value (more negative = quieter)
   - -8 dB to -12 dB good for background music

3. **Re-assemble with adjusted settings:**
   - Edit template music rules
   - Lower music volume
   - Re-assemble episode

### Poor Audio Quality

**Problem:** Audio sounds compressed, garbled, or distorted

**Causes:**
1. Low-quality source file (low bitrate)
2. Multiple re-encodings
3. File corruption

**Solutions:**

1. **Check source file quality:**
   - 128 kbps minimum recommended
   - 192 kbps or higher for best quality
   - Record at highest quality your tool supports

2. **Upload highest quality version:**
   - Don't pre-compress if possible
   - Platform handles optimization
   - WAV or high-bitrate MP3 best

3. **Avoid multiple conversions:**
   - Record → Upload directly
   - Don't: Record → Convert → Edit → Convert → Upload

### Music Not Playing

**Problem:** Background music not audible in assembled episode

**Diagnostic steps:**
1. **Check template music rules exist**
   - Go to Templates tab
   - Open template
   - Verify music rules added

2. **Check music file uploaded**
   - Go to Media tab
   - Filter: Background Music
   - Verify file exists

3. **Check music rule settings**
   - `apply_to_segments`: Must include segment types
   - `volume_db`: Not too low (try -6 dB)
   - Music file selected in rule

**Solutions:**

1. **Re-add music rule:**
   - Templates → Edit template
   - Add music rule
   - Select music file
   - Set volume to -6 dB (to start)
   - Apply to correct segments (intro, content, outro)
   - Save template

2. **Re-assemble episode:**
   - Go to episode
   - Click "Assemble & Review" again
   - Listen for music

### Music Too Loud

**Problem:** Music overpowers speech, speech hard to hear

**Solution:**
- Edit template music rules
- Lower `volume_db` (more negative = quieter)
- Typical values:
  - -4 dB: Prominent background music
  - -8 dB: Moderate background music (recommended)
  - -12 dB: Subtle background music
  - -16 dB: Very quiet background

---

## Account & Billing Issues

### Usage Limit Reached

**Problem:** "Insufficient credits" error, can't process new audio

**Explanation:** Each plan has monthly minute limit for transcription and TTS

**Check your usage:**
1. Go to Settings → Billing
2. See "Usage This Month"
3. Compare to plan limit

**Solutions:**

**Short-term:**
- Wait for monthly reset (shown in billing)
- Use draft episodes already processed
- Schedule episodes to publish after reset

**Long-term:**
- Upgrade to higher tier plan
- Creator: 500 minutes/month
- Professional: 2000 minutes/month
- Enterprise: Unlimited

### Billing Issues

**Problem:** Payment failed, subscription cancelled, can't access features

**Diagnostic steps:**
1. **Check payment method:**
   - Settings → Billing → Payment Method
   - Is card expired?
   - Sufficient funds?

2. **Check subscription status:**
   - Settings → Billing → Subscription
   - Status: Active, Cancelled, Past Due?

**Solutions:**

**Payment failed:**
1. Update payment method
2. Retry payment
3. Contact support if issue persists

**Subscription cancelled:**
- Re-subscribe in Settings → Billing
- Previous data remains intact

**Can't change plan:**
- Log out and log back in
- Clear browser cache
- Contact support

---

## Performance Issues

### Platform Slow

**Problem:** Pages load slowly, actions take long time

**Diagnostic steps:**
1. **Is it widespread or specific page?**
   - Specific page: May be data loading issue
   - All pages: Network or platform issue

2. **Check network:**
   - Run speed test
   - Check other websites loading normally

3. **Check browser:**
   - Too many tabs open?
   - Extensions interfering?
   - Try incognito mode

**Solutions:**

**For specific features:**
- Episodes tab slow: May be loading many episodes
  - Use filters to reduce results
  - Pagination coming in future version

**For general slowness:**
1. Clear browser cache
2. Close other tabs
3. Disable extensions
4. Try different browser
5. Check if platform status banner showing issues

### Audio Player Laggy

**Problem:** Audio player stutters, waveform slow to load, scrubbing delayed

**Causes:**
1. Large audio file (>200MB)
2. Slow network
3. Browser memory issue

**Solutions:**
1. **Wait for full load:**
   - Waveform loads progressively
   - Wait for completion before scrubbing

2. **Reduce file size:**
   - Export at lower bitrate if editing source

3. **Close other tabs:**
   - Audio player memory-intensive
   - Free up browser resources

---

## Error Messages

### "Please select a valid audio file"

**Meaning:** File type not supported or corrupted

**Fix:** Use MP3, WAV, M4A, OGG, or FLAC. Verify file plays in media player.

### "File size exceeds limit (500MB)"

**Meaning:** Uploaded file too large

**Fix:** Compress file or split into multiple parts. Use lower bitrate (128 kbps acceptable).

### "Transcription failed"

**Meaning:** Assembly AI couldn't process audio

**Fix:** Check audio quality and format. Try re-uploading. Contact support if persists.

### "Template not found"

**Meaning:** Template was deleted or user lacks access

**Fix:** Select different template or create new one.

### "Insufficient credits"

**Meaning:** Monthly usage limit reached

**Fix:** Wait for billing cycle reset or upgrade plan.

### "Authentication failed"

**Meaning:** Session expired or login issue

**Fix:** Log out and log back in. Check internet connection.

### "Episode not found"

**Meaning:** Episode doesn't exist or was deleted

**Fix:** Check Episodes tab for correct episode. May have been deleted.

### "Audio processing failed"

**Meaning:** Error during assembly or processing

**Fix:** Check source audio files are valid. Simplify template. Retry. Contact support with episode ID if persistent.

---

## Getting Additional Help

### Self-Service Resources

1. **AI Assistant "Mike"**
   - Click chat bubble (bottom-right)
   - Available 24/7
   - Can guide through features

2. **Documentation**
   - [User Manual](../user-guides/USER_MANUAL.md)
   - [FAQ](../user-guides/FAQ.md)
   - [Full Docs Index](../DOCS_INDEX.md)

3. **System Status**
   - Check app banner for outages
   - Platform updates announced in-app

### Contact Support

**Email:** support@podcastplusplus.com

**Response Times:**
- Free tier: 2-3 business days
- Creator/Professional: 24-48 hours
- Enterprise: 4-hour response (business hours)

**What to include:**
1. **Problem description** - What happened, what you expected
2. **Steps to reproduce** - How to trigger the issue
3. **Episode/template ID** - Find in URL or Episodes tab
4. **Screenshots** - If visual issue
5. **Browser/OS** - Chrome 120 on Windows 11, etc.
6. **Timestamp** - When it happened (helps check logs)

**Example good support request:**
```
Subject: Episode assembly stuck in "Processing"

Hi, my episode is stuck processing for 2 hours.

Episode ID: abc123-def456-789
Podcast: "My Great Podcast"
Uploaded: 2025-10-11 at 2:30 PM PST
Audio file: 45-minute interview (120MB MP3)
Template: "Standard Episode"

Steps:
1. Uploaded audio
2. Waited for transcription (completed)
3. Clicked "Assemble & Review"
4. Status shows "Processing" since then

Expected: Assembly completes in 1-2 minutes
Actual: Still processing after 2 hours

Browser: Chrome 120 on Windows 11

Screenshot attached.
```

---

## Historical Issues (Resolved)

For context on past platform issues and their resolutions, see:

- [Archive](../archive/) - October 2025 troubleshooting docs
- [Deployment History](../deployment/DEPLOYMENT_HISTORY.md) - Past deployments and fixes

---

## Preventing Future Issues

### Best Practices

**For reliable uploads:**
- Use wired internet when possible
- Upload during off-peak hours
- Keep files under 300MB when possible
- Use standard audio formats (MP3 preferred)

**For reliable processing:**
- Record high-quality audio (good mic, quiet room)
- Use templates tested previously
- Test new templates with short clips first
- Keep segments simple initially

**For reliable publishing:**
- Verify RSS feed before submitting to platforms
- Test episodes in podcast app before announcing
- Schedule releases during business hours (easier to fix issues)

---

**Last Updated:** October 11, 2025  
**Need more help?** Contact support@podcastplusplus.com
