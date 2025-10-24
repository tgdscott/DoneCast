# Database Verification Guide - Website Sections

Use these SQL queries in PGAdmin to verify the website sections migration and test the new functionality.

## 1. Verify Migration Ran Successfully

Check that the new columns were added to the `podcast_website` table:

```sql
SELECT 
    column_name, 
    data_type, 
    is_nullable,
    column_default
FROM information_schema.columns 
WHERE table_name = 'podcast_website'
    AND column_name IN ('sections_order', 'sections_config', 'sections_enabled')
ORDER BY ordinal_position;
```

**Expected Output:**
```
column_name      | data_type | is_nullable | column_default
-----------------+-----------+-------------+---------------
sections_order   | text      | YES         | NULL
sections_config  | text      | YES         | NULL
sections_enabled | text      | YES         | NULL
```

## 2. View Current Website Table Structure

See all columns in the podcast_website table:

```sql
SELECT 
    column_name,
    data_type,
    character_maximum_length,
    is_nullable
FROM information_schema.columns
WHERE table_name = 'podcast_website'
ORDER BY ordinal_position;
```

## 3. Check Existing Websites

List all websites and their current section data:

```sql
SELECT 
    pw.id,
    pw.subdomain,
    pw.status,
    p.name AS podcast_name,
    pw.sections_order,
    pw.sections_config,
    pw.sections_enabled,
    pw.last_generated_at,
    pw.created_at
FROM podcast_website pw
JOIN podcast p ON pw.podcast_id = p.id
ORDER BY pw.created_at DESC;
```

## 4. Manually Test Section Storage

### Add Test Section Data to an Existing Website

Replace `YOUR_PODCAST_ID` with an actual UUID from your database:

```sql
-- First, find a podcast ID
SELECT id, name FROM podcast LIMIT 5;

-- Then update its website with test section data
UPDATE podcast_website 
SET 
    sections_order = '["hero", "about", "latest-episodes", "newsletter", "subscribe"]',
    sections_config = '{
        "hero": {
            "title": "Test Podcast",
            "subtitle": "Testing the new section builder",
            "cta_text": "Listen Now",
            "background_color": "#1e293b"
        },
        "about": {
            "heading": "About the Show",
            "body": "This is a test of the new section-based website builder."
        },
        "newsletter": {
            "heading": "Stay Updated",
            "description": "Get episode updates",
            "form_action_url": "https://example.com/subscribe"
        }
    }',
    sections_enabled = '{
        "hero": true,
        "about": true,
        "latest-episodes": true,
        "newsletter": true,
        "subscribe": true
    }',
    updated_at = NOW()
WHERE podcast_id = 'YOUR_PODCAST_ID';
```

### Verify the Update

```sql
SELECT 
    subdomain,
    sections_order,
    sections_config,
    sections_enabled
FROM podcast_website
WHERE podcast_id = 'YOUR_PODCAST_ID';
```

## 5. Query Section Configuration

### Get websites with specific sections enabled

```sql
SELECT 
    pw.subdomain,
    pw.sections_order
FROM podcast_website pw
WHERE sections_enabled::jsonb ? 'hero'  -- Has 'hero' key
    AND sections_enabled::jsonb->>'hero' = 'true'  -- Hero is enabled
ORDER BY pw.created_at DESC;
```

### Find websites using newsletter section

```sql
SELECT 
    pw.subdomain,
    pw.sections_config::jsonb->'newsletter'->>'heading' AS newsletter_heading,
    pw.sections_config::jsonb->'newsletter'->>'form_action_url' AS form_url
FROM podcast_website pw
WHERE sections_enabled::jsonb->>'newsletter' = 'true';
```

## 6. Backup Before Testing

Create a backup of website data before making changes:

```sql
-- Create backup table
CREATE TABLE podcast_website_backup_oct15 AS 
SELECT * FROM podcast_website;

-- Verify backup
SELECT COUNT(*) FROM podcast_website_backup_oct15;
```

## 7. Rollback Test Data

If you need to undo test changes:

```sql
-- Clear section data for a specific website
UPDATE podcast_website
SET 
    sections_order = NULL,
    sections_config = NULL,
    sections_enabled = NULL
WHERE podcast_id = 'YOUR_PODCAST_ID';

-- Or restore from backup
UPDATE podcast_website pw
SET 
    sections_order = bak.sections_order,
    sections_config = bak.sections_config,
    sections_enabled = bak.sections_enabled
FROM podcast_website_backup_oct15 bak
WHERE pw.id = bak.id;
```

## 8. Analytics Queries

### Count websites by number of sections

```sql
SELECT 
    jsonb_array_length(sections_order::jsonb) AS section_count,
    COUNT(*) AS website_count
FROM podcast_website
WHERE sections_order IS NOT NULL
GROUP BY section_count
ORDER BY section_count;
```

### Most popular sections

```sql
WITH section_usage AS (
    SELECT 
        jsonb_array_elements_text(sections_order::jsonb) AS section_id
    FROM podcast_website
    WHERE sections_order IS NOT NULL
)
SELECT 
    section_id,
    COUNT(*) AS usage_count
FROM section_usage
GROUP BY section_id
ORDER BY usage_count DESC;
```

### Websites with custom configurations

```sql
SELECT 
    pw.subdomain,
    jsonb_object_keys(sections_config::jsonb) AS configured_section
FROM podcast_website pw
WHERE sections_config IS NOT NULL
    AND sections_config != '{}'
ORDER BY pw.subdomain;
```

## 9. Data Validation

### Check for invalid JSON

```sql
-- Find websites with malformed JSON
SELECT 
    id,
    subdomain,
    CASE 
        WHEN sections_order IS NOT NULL 
            AND sections_order::jsonb IS NULL 
            THEN 'Invalid sections_order'
        WHEN sections_config IS NOT NULL 
            AND sections_config::jsonb IS NULL 
            THEN 'Invalid sections_config'
        WHEN sections_enabled IS NOT NULL 
            AND sections_enabled::jsonb IS NULL 
            THEN 'Invalid sections_enabled'
        ELSE 'Valid'
    END AS validation_status
FROM podcast_website;
```

### Validate section IDs against known sections

```sql
-- This will need to be updated with actual section IDs from your code
WITH valid_sections AS (
    SELECT unnest(ARRAY[
        'hero', 'about', 'latest-episodes', 'subscribe',
        'hosts', 'newsletter', 'testimonials', 'support-cta',
        'events', 'community', 'press', 'sponsors', 'resources',
        'faq', 'contact', 'transcripts', 'social-feed', 'behind-scenes'
    ]) AS section_id
),
website_sections AS (
    SELECT 
        pw.id,
        pw.subdomain,
        jsonb_array_elements_text(sections_order::jsonb) AS section_id
    FROM podcast_website pw
    WHERE sections_order IS NOT NULL
)
SELECT 
    ws.subdomain,
    ws.section_id,
    CASE 
        WHEN vs.section_id IS NULL THEN '❌ Invalid'
        ELSE '✅ Valid'
    END AS validity
FROM website_sections ws
LEFT JOIN valid_sections vs ON ws.section_id = vs.section_id
WHERE vs.section_id IS NULL;  -- Show only invalid sections
```

## 10. Performance Testing

### Index recommendations (if needed)

```sql
-- Check if indexes would help (run EXPLAIN on common queries first)
-- Only create if query performance is slow

-- CREATE INDEX IF NOT EXISTS idx_podcast_website_sections_gin 
-- ON podcast_website USING gin (sections_order jsonb_path_ops);

-- CREATE INDEX IF NOT EXISTS idx_podcast_website_config_gin 
-- ON podcast_website USING gin (sections_config jsonb_path_ops);
```

## Common PGAdmin Tasks

### Quick Section Data Viewer

Create a view for easy section data inspection:

```sql
CREATE OR REPLACE VIEW v_website_sections AS
SELECT 
    pw.id,
    pw.subdomain,
    p.name AS podcast_name,
    pw.status,
    jsonb_array_length(sections_order::jsonb) AS section_count,
    jsonb_object_keys(sections_config::jsonb) AS configured_sections,
    pw.sections_order::jsonb AS ordered_sections,
    pw.last_generated_at,
    pw.updated_at
FROM podcast_website pw
JOIN podcast p ON pw.podcast_id = p.id
WHERE sections_order IS NOT NULL;

-- Use it
SELECT * FROM v_website_sections;
```

### Drop the migration (if needed for rollback)

**⚠️ WARNING: This will delete all section data!**

```sql
-- Backup first!
CREATE TABLE podcast_website_backup_pre_rollback AS 
SELECT * FROM podcast_website;

-- Then drop columns
ALTER TABLE podcast_website 
DROP COLUMN IF EXISTS sections_order,
DROP COLUMN IF EXISTS sections_config,
DROP COLUMN IF EXISTS sections_enabled;
```

---

## Next Steps After Verification

1. ✅ Confirm columns exist
2. ✅ Insert test section data
3. ✅ Test API endpoints with curl (see `test_website_sections_api.py`)
4. ✅ Verify JSON serialization works correctly
5. 🔄 Start frontend implementation

## Troubleshooting

### If migration didn't run:
- Check API startup logs for `[migrate] Ensured website sections columns`
- Manually run SQL from step 1 to add columns
- Restart API server

### If JSON validation fails:
- Ensure Python json.dumps() is used (not manual string concatenation)
- Test JSON parsing in Python: `json.loads(website.sections_order)`
- Check for escaped quotes or encoding issues

### If queries are slow:
- Consider adding GIN indexes on JSON columns
- Analyze query plans with EXPLAIN ANALYZE
- Check table statistics are up to date: `ANALYZE podcast_website;`
