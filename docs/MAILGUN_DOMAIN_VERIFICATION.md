# Mailgun Domain Verification - CRITICAL FOR EMAIL DELIVERY

## The Problem

**SMTP connection succeeds, but emails don't arrive.**

This is because Mailgun **requires domain verification** before you can send emails from a custom domain. Even though SMTP authentication works, Mailgun will silently reject emails from unverified domains.

## Current Configuration

- **SMTP_HOST**: `smtp.mailgun.org` ✅
- **SMTP_USER**: `admin@podcastplusplus.com` ✅
- **SMTP_FROM**: `no-reply@PodcastPlusPlus.com` ⚠️ **DOMAIN NOT VERIFIED**

## Solution: Verify Domain in Mailgun

### Step 1: Go to Mailgun Dashboard
1. Log in to https://app.mailgun.com
2. Go to **Sending** → **Domains**
3. Click **Add New Domain** or find `podcastplusplus.com`

### Step 2: Add DNS Records
Mailgun will provide DNS records you need to add:

**TXT Record** (for domain verification):
```
Name: podcastplusplus.com
Value: (provided by Mailgun)
```

**MX Records** (if using Mailgun for receiving):
```
(Usually not needed for sending only)
```

**SPF Record** (for sender authentication):
```
Name: podcastplusplus.com
Value: v=spf1 include:mailgun.org ~all
```

**DKIM Records** (for email signing):
```
Name: (provided by Mailgun, e.g., s1._domainkey.podcastplusplus.com)
Value: (provided by Mailgun)
```

### Step 3: Wait for Verification
- DNS propagation can take 24-48 hours
- Mailgun will show verification status in dashboard
- Once verified, emails will start delivering

## Temporary Workaround: Use Sandbox Domain

If you need emails working immediately:

1. **Get your Mailgun sandbox domain**:
   - Go to Mailgun dashboard → Sending → Domains
   - Find your sandbox domain (format: `sandboxXXXXX.mailgun.org`)

2. **Update SMTP_FROM**:
   ```bash
   SMTP_FROM=postmaster@sandboxXXXXX.mailgun.org
   ```

3. **Limitation**: Sandbox domain can only send to authorized recipients
   - Go to Mailgun → Authorized Recipients
   - Add email addresses you want to receive emails

## How to Check if Domain is Verified

1. **Mailgun Dashboard**: Sending → Domains → Check status
2. **Test Email Endpoint**: `POST /api/auth/test-email` (admin only)
3. **Check Logs**: Look for `SMTPDataError` or domain verification errors

## Production Checklist

- [ ] Domain `podcastplusplus.com` added to Mailgun
- [ ] DNS records added to domain registrar
- [ ] Domain verified in Mailgun dashboard (green checkmark)
- [ ] Test email sent and received successfully
- [ ] Verification emails arriving for new users

## Common Errors

### "SMTPDataError: 550 Domain not verified"
- **Cause**: Domain not verified in Mailgun
- **Fix**: Complete domain verification steps above

### "SMTPRecipientsRefused: 550 Relay denied"
- **Cause**: Wrong SMTP credentials or domain not authorized
- **Fix**: Verify SMTP_USER and SMTP_PASS, check domain verification

### Emails accepted but never arrive
- **Cause**: Domain not verified (most common)
- **Fix**: Verify domain in Mailgun dashboard

## Monitoring

After fixing, monitor:
1. **Mailgun Dashboard** → Logs → See delivery status
2. **Cloud Run Logs** → Look for `[RESEND_VERIFICATION]` and `[REGISTRATION]` entries
3. **Test Endpoint** → `/api/auth/test-email` to verify working


