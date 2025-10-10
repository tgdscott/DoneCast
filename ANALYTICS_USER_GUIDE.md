# Analytics Feature - User Guide

## Accessing Analytics

### Method 1: Quick Tools Sidebar
```
Dashboard → Quick Tools → Analytics Button
```
- Click "Analytics" button in the Quick Tools card
- Automatically shows analytics for your first podcast
- Disabled if you have no podcasts created

### Method 2: From Podcast Manager
```
Dashboard → Quick Tools → Podcasts → View Analytics (per podcast)
```
- Click "Podcasts" in Quick Tools
- Each podcast card has a "View Analytics" button
- Click to see analytics for that specific show

## Analytics Dashboard Features

### Time Range Selector
Choose your analysis window:
- **7 days** - Weekly trends, recent performance
- **30 days** - Monthly overview (default)
- **90 days** - Quarterly analysis
- **365 days** - Annual performance, year-over-year

### Summary Cards
Four key metrics at the top:
1. **Total Downloads** - All-time download count for the time range
2. **Countries** - Number of different countries listening
3. **Apps** - Number of different podcast apps/platforms used
4. **Average/Day** - Daily average downloads in time range

### Download Trend Chart
- Line graph showing downloads over time
- X-axis: Days in selected time range
- Y-axis: Number of downloads
- Visualize growth, spikes, and trends

### Geographic Distribution
- Bar chart showing top countries by downloads
- See where your audience is located globally
- Understand regional popularity

### App & Platform Analytics
- Bar chart showing podcast apps/platforms used
- Examples: Apple Podcasts, Spotify, Overcast, Pocket Casts
- Helps understand listener preferences

### Top Episodes List
- Table showing top 10 episodes by downloads
- Episode number, title, and download count
- Identify your most popular content

## Data Availability

### Important Notes:
- **New Feature**: Analytics data begins collecting after deployment
- **Delay**: OP3 requires 24-48 hours to start showing data
- **Historical Limit**: Only tracks downloads after OP3 integration
- **Update Frequency**: Data updates periodically (not real-time)

### First-Time Users:
After deployment, you'll see:
- Day 0: "No data available" message
- Days 1-2: Data may still be processing
- Day 3+: Full analytics available

## Privacy & Compliance

### What We Track:
- Download counts (aggregated)
- Geographic location (country-level only)
- Podcast app/platform used
- Episode requested
- Timestamp of download

### What We DON'T Track:
- Personal information (PII)
- Email addresses
- User accounts
- Individual listener identity
- IP addresses (not stored)

### Compliance:
- ✅ GDPR compliant
- ✅ Privacy-respecting (uses OP3 - Open Podcast Prefix Project)
- ✅ No cookies or tracking scripts
- ✅ Aggregated data only

## Troubleshooting

### "No data available"
**Possible reasons:**
1. Analytics just deployed - wait 24-48 hours
2. No downloads in selected time range - try longer period
3. Episodes not yet published - verify RSS feed is live
4. Network error - check connection and retry

### "Failed to load analytics"
**Solutions:**
1. Refresh the page
2. Check your internet connection
3. Verify you own this podcast
4. Contact support if persists

### Downloads seem low
**Check:**
1. Is your RSS feed submitted to podcast directories?
2. Are episodes marked as "public" or "published"?
3. Are you viewing the right time range?
4. Historical data only tracks post-integration downloads

## Best Practices

### Optimize Your Content:
1. Check which episodes perform best
2. Create similar content to top performers
3. Analyze geographic data for international audiences
4. Understand platform preferences for optimization

### Monitor Growth:
1. Set a regular schedule to check analytics (weekly)
2. Compare 7-day vs 30-day trends
3. Look for spikes and investigate causes
4. Track seasonal patterns over 365 days

### Make Data-Driven Decisions:
- **High-performing topics**: Create more content on these themes
- **Geographic insights**: Consider language/regional content
- **Platform trends**: Optimize for popular podcast apps
- **Episode length**: Compare downloads vs duration

## Technical Details

### Powered by OP3
[Open Podcast Prefix Project](https://op3.dev) - Privacy-respecting podcast analytics

**How it works:**
1. Your RSS feed includes OP3 prefix URLs
2. Podcast apps request episodes from OP3
3. OP3 logs the download (anonymously)
4. OP3 redirects to your actual audio file
5. This dashboard queries OP3 API for stats

**Benefits:**
- Industry-standard analytics
- Cross-platform compatibility
- Privacy-respecting
- Free for most podcasters
- No client-side tracking needed

## Support

Need help with analytics?
- Check this guide first
- Verify deployment completed successfully
- Wait 48 hours for initial data
- Contact support with specific error messages

---
**Feature Status:** Live after deployment
**Data Provider:** OP3 (Open Podcast Prefix Project)
**Update Frequency:** Periodic (non-real-time)
**Historical Data:** Post-integration only
