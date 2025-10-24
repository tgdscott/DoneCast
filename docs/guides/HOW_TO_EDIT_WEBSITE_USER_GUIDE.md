# How to Edit Your Podcast Website - User Guide

## Accessing the Website Builder

### From Dashboard:
1. Log into your Podcast++ account
2. Click **"Website Builder"** button in the navigation sidebar
3. Select which podcast you want to create a website for

---

## Building Your Website (Two Modes)

### Visual Builder Mode (Recommended)
**What you can do:**
- ✅ **Drag & drop sections** to reorder them
- ✅ **Toggle sections on/off** with the eye icon
- ✅ **Configure each section** with the settings gear icon
- ✅ **Add new sections** from the palette
- ✅ **Delete sections** with the trash icon
- ✅ **See live preview** as you make changes

**How to use it:**
1. Click **"Visual Builder"** button (if not already there)
2. Drag sections up/down to reorder
3. Click eye icon to hide/show sections
4. Click gear icon to edit section content (titles, colors, text, etc.)
5. Click **"Save"** after configuring each section

### AI Mode (Legacy)
- Type instructions like "Make the hero section purple"
- AI will adjust the layout based on your request
- Less precise than Visual Builder

---

## Available Sections

### Layout Sections (Sticky Behavior)
- **Header** - Logo, navigation menu, optional audio player (stays at top while scrolling)
- **Footer** - Social links, subscribe buttons, copyright info (bottom of page)

### Core Content Sections
- **Hero** - Large banner with podcast name, tagline, and call-to-action
- **About** - Overview of your show
- **Latest Episodes** - Display recent episodes with play buttons
- **Subscribe** - Platform links (Apple Podcasts, Spotify, etc.)

### Marketing & Community Sections
- **Newsletter** - Email signup form
- **Testimonials** - Listener reviews/quotes
- **Sponsors** - Showcase partners
- **Gallery** - Photo/video grid
- **FAQ** - Frequently asked questions
- **Reviews** - Rating displays
- **Events** - Upcoming shows/appearances
- **Donation** - Support links
- **Merch** - Product showcase
- **Transcripts** - Episode transcripts
- **Community Links** - Discord, Slack, forums
- **Press Kit** - Media resources

---

## Publishing Your Website

### Steps to Publish:
1. **Create/edit your website** using the Visual Builder
2. **Click "Publish Website"** button (green button in status card)
3. **Wait 10-15 minutes** for SSL certificate provisioning
4. **Notification appears** when website is live
5. **Visit your subdomain** (e.g., `your-podcast-name.podcastplusplus.com`)

### What Happens When You Publish:
- ✅ Website status changes to **"Published"**
- ✅ **FREE SSL certificate** is automatically provisioned by Google
- ✅ Your **subdomain is activated** (e.g., `cinema-irl.podcastplusplus.com`)
- ✅ **10-15 minute wait** while SSL certificate is created (you'll get notified)
- ✅ Website becomes **publicly accessible** with HTTPS

### Subdomain Configuration:
- Your subdomain is automatically created from your podcast name
- Format: `podcast-name.podcastplusplus.com`
- No manual DNS configuration needed
- SSL certificate is FREE (Google-managed)

---

## Making Changes After Publishing

### Editing Published Websites:
1. Make changes in Visual Builder (sections, content, colors, etc.)
2. Changes are **automatically saved**
3. **Refresh your live site** to see updates (may take a few seconds)

### Unpublishing:
1. Click **"Unpublish"** button (same button as "Publish")
2. Website goes back to **draft** status
3. Subdomain still resolves but shows "Website Not Found" error
4. Note: Domain mapping is NOT deleted (can republish instantly)

---

## Status Indicators

### Draft
- Amber badge: **"Draft"**
- Website is NOT publicly accessible
- Only visible in preview mode
- Can still edit and test

### Published
- Green badge: **"Published"**
- Website is live and accessible
- SSL certificate active
- Subdomain working

### Updating
- Blue badge: **"Updating"**
- Changes being deployed
- Brief status during saves

---

## Technical Details (For Power Users)

### URL Structure:
```
Published site:     https://your-podcast.podcastplusplus.com
Preview endpoint:   https://api.podcastplusplus.com/api/sites/your-podcast/preview
API endpoint:       https://api.podcastplusplus.com/api/sites/your-podcast
```

### SSL Certificate:
- **Provisioning time:** 10-15 minutes
- **Cost:** FREE (Google-managed)
- **Auto-renewal:** Yes, automatic
- **Rate limit:** 50 certificates per week (can be increased to 300/week for free)

### Domain Mapping:
- **Wildcard DNS:** `*.podcastplusplus.com` → `ghs.googlehosted.com`
- **Per-podcast mapping:** Created automatically on publish
- **Custom domains:** Coming soon (bring your own domain)

### Backend API:
```
POST /api/podcasts/{id}/website/publish
  → Publishes website & provisions subdomain

GET /api/podcasts/{id}/website/domain-status
  → Check SSL certificate readiness

POST /api/podcasts/{id}/website/unpublish
  → Set back to draft mode
```

---

## Troubleshooting

### "Publish" button is disabled:
- Make sure you've created a website first (click "Create my site")
- Website must have a subdomain configured
- Check that you're not already publishing

### Website shows "Not Found" after publishing:
- **Wait 10-15 minutes** for SSL certificate to provision
- Check "Last generated" time in status card
- Try visiting `/preview` endpoint for draft version

### SSL certificate not ready:
- Automatic notifications will alert you when ready
- Poll status: Check every 30 seconds via "Refresh" button
- Max wait time: 15 minutes (usually 10 minutes)

### Changes not appearing on live site:
- Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
- Wait a few seconds for CDN propagation
- Check that you saved section configurations

### Can't edit header or footer:
- Header/footer are special layout sections
- Click gear icon on the section to configure
- Toggle visibility with eye icon
- Drag to reorder (header always top, footer always bottom)

---

## FAQ

**Q: How much does publishing cost?**
A: Publishing is **FREE**. SSL certificates are provided by Google at no cost.

**Q: Can I use my own domain?**
A: Custom domains (BYOD - Bring Your Own Domain) are coming soon. Currently only `*.podcastplusplus.com` subdomains are supported.

**Q: How many websites can I create?**
A: One website per podcast. You can have multiple podcasts, each with its own website.

**Q: Can I unpublish and republish?**
A: Yes! Unpublishing sets the site to draft mode. Republishing is instant (SSL cert already exists).

**Q: What happens if I delete a section?**
A: Deleted sections are removed from the database. You can re-add them from the palette.

**Q: Can I preview before publishing?**
A: Yes! The preview panel shows exactly how your site will look. Or use the preview endpoint URL.

**Q: Do I need to configure DNS?**
A: No. DNS is handled automatically via wildcard CNAME. Your subdomain works instantly after SSL cert provisioning.

**Q: Can I change my subdomain?**
A: Currently no. Subdomain is derived from podcast name. Changing podcast name MAY change subdomain (to be implemented).

---

## Feature Requests & Roadmap

### Planned Features:
- ✅ Header/Footer sections (DONE)
- ✅ Subdomain publishing (DONE)
- ✅ Auto SSL provisioning (DONE)
- 🔄 Custom domains (BYOD) - Coming soon
- 🔄 Multi-page websites - Phase 3
- 🔄 Persistent audio player - Phase 3
- 🔄 Interactive forms - Phase 3
- 🔄 Analytics dashboard - Future
- 🔄 SEO optimization tools - Future

### Beta Notes:
- This is a **beta feature** - report bugs to support
- SSL provisioning is reliable but may occasionally take longer
- Rate limit: 50 websites/week (contact support if you need more)

---

*Last updated: Oct 16, 2025*
*For support: Contact your Podcast++ admin*
