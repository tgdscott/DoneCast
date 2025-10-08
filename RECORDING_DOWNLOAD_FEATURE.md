# Recording Download & Email Notification Feature

## Summary
Add email notifications and prominent download link for in-app recordings with 24-hour retention (even if used in episode).

## Frontend Changes - Recorder.jsx

### 1. Add imports (line 7-11)
```jsx
import { ArrowLeft, Mic, Square, Loader2, CheckCircle, Download } from "lucide-react";  // Add Download
import { useAuth } from "@/AuthContext";  // NEW
```

### 2. Get user from auth context (line 13-14)
```jsx
export default function Recorder({ onBack, token, onFinish, onSaved, source="A" }) {
  const { user: authUser } = useAuth();  // NEW
```

### 3. Update uploadMediaDirect call (around line 592-598)
```jsx
// BEFORE:
const uploaded = await uploadMediaDirect({
  category: 'main_content',
  file,
  friendlyName: baseName,
  token,
});

// AFTER:
const userEmail = authUser?.email || '';
const uploaded = await uploadMediaDirect({
  category: 'main_content',
  file,
  friendlyName: baseName,
  token,
  notifyWhenReady: !!userEmail,
  notifyEmail: userEmail || undefined,
});
```

### 4. Update success toast (around line 604)
```jsx
// BEFORE:
toast({ title: "Saved", description: "Saved. Transcription has started." });

// AFTER:
const emailMsg = userEmail ? ` We'll email you at ${userEmail} when it's ready.` : '';
toast({ 
  title: "Recording Saved!", 
  description: `Transcription started.${emailMsg} Download link available for 24 hours.` 
});
```

### 5. Add prominent download section (after line 972, before showTimeoutNotice)
```jsx
{/* INSERT AFTER the closing </div> of the status flex container */}

{/* Prominent download button - available for 24 hours */}
{audioUrl && audioBlob && (
  <div className="border-t pt-3 mt-3">
    <div className="flex items-start gap-3">
      <div className="flex-1">
        <div className="text-sm font-medium text-blue-900 mb-1">
          💾 Download Raw Recording
        </div>
        <div className="text-xs text-muted-foreground">
          Save a backup copy now! Download link available for 24 hours.
          {authUser?.email && <span className="block mt-1">Link also emailed to {authUser.email}</span>}
        </div>
      </div>
      <Button
        variant="outline"
        size="sm"
        className="shrink-0"
        onClick={() => {
          if (!audioUrl || !audioRef.current) return;
          const link = document.createElement('a');
          link.href = audioUrl;
          link.download = savedDisplayName || `${recordingName || 'recording'}.wav`;
          document.body.appendChild(link);
          link.click();
          document.body.removeChild(link);
          toast({ title: "Downloaded!", description: "Raw recording saved to your device." });
        }}
      >
        <Download className="w-4 h-4 mr-2" />
        Download Now
      </Button>
    </div>
  </div>
)}
```

## Backend Changes - Media Retention

### File: backend/api/core/cleanup.py or wherever overnight purge runs

Need to update media cleanup logic:
1. **Current**: Deletes main_content files immediately after use
2. **New**: Keep main_content files for 24 hours after upload, even if used
3. **Implementation**: 
   - Add `uploaded_at` timestamp to media items
   - Purge runs after first midnight following 24 hours
   - Delete only if `uploaded_at + 24 hours < first_midnight_after_24h`

### Example Logic:
```python
def should_purge_recording(media_item):
    """
    Keep recordings for 24 hours + until next overnight purge.
    This gives users "oops" time to download.
    """
    if media_item.category != 'main_content':
        return False  # Don't touch other categories
    
    uploaded_at = media_item.uploaded_at or media_item.created_at
    if not uploaded_at:
        return True  # No timestamp, purge it
    
    now = datetime.now(timezone.utc)
    age_hours = (now - uploaded_at).total_seconds() / 3600
    
    # If less than 24 hours old, keep it
    if age_hours < 24:
        return False
    
    # If 24+ hours old, purge on first overnight run
    # (This happens automatically since cleanup runs overnight)
    return True
```

## Email Template Changes

### File: backend/api/services/transcription/watchers.py

Update email body (around line 149-152):
```python
# BEFORE:
body = (
    f"Good news! The audio file '{friendly_text}' has finished processing and is ready in Podcast Plus Plus.\n\n"
    "You can return to the dashboard to continue building your episode."
)

# AFTER:
body = (
    f"Good news! Your recording '{friendly_text}' has finished processing and is ready in Podcast Plus Plus.\n\n"
    f"📥 Download link (valid for 24 hours): https://app.podcastplusplus.com/media/download/{filename}\n\n"
    "💡 Tip: Download a backup copy now! The raw file will be automatically deleted after 24 hours.\n\n"
    "You can return to the dashboard to continue building your episode."
)
```

## Testing Checklist

### Frontend:
- [ ] Record audio in-browser
- [ ] Verify toast shows email address and 24-hour notice
- [ ] Verify download section appears after save
- [ ] Click "Download Now" button
- [ ] Verify file downloads correctly
- [ ] Verify toast confirms download

### Backend:
- [ ] Upload triggers email with download link
- [ ] Email arrives within 2 minutes
- [ ] Email includes 24-hour notice
- [ ] Download link works for 24 hours
- [ ] File persists for 24+ hours even if used in episode
- [ ] File purges on first overnight cleanup after 24 hours

### Edge Cases:
- [ ] User has no email (should still work, no email sent)
- [ ] Recording used in episode immediately (file still available for 24h)
- [ ] Multiple recordings in same day (all kept for 24h each)
- [ ] User downloads multiple times (blob URL persists in browser)

## Deployment Notes

1. Deploy frontend changes first (non-breaking)
2. Deploy backend retention changes (extend, don't restrict)
3. Monitor for 24 hours to ensure no premature deletions
4. Update documentation/help text

## User Communication

After deployment, add to Help/FAQ:
> **Q: How long do I have to download my recordings?**
> 
> A: Raw recordings are available for download for 24 hours after you record them. We'll email you a download link, and you can also download directly from the recording screen. After 24 hours, the file will be automatically deleted during our overnight cleanup process.
> 
> **Important**: Always download a backup of your raw recording! While we keep it for 24 hours even if you use it in an episode, you're responsible for long-term storage of your raw audio files.
