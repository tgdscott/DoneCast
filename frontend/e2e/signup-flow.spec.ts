import { test, expect } from '@playwright/test';

// Utility to stub JSON responses
function json(data: any, status = 200) {
    return {
        status,
        contentType: 'application/json',
        body: JSON.stringify(data),
    } as const;
}

test.describe('New User Signup & Onboarding Flow', () => {
    test('complete onboarding wizard for new user', async ({ page }) => {
        // Debug logging
        page.on('console', (msg) => console.log(`[console:${msg.type()}]`, msg.text()));
        page.on('pageerror', (err) => console.log('[pageerror]', err.message));

        // 1. Mock Authentication & User State
        await page.addInitScript(() => {
            window.localStorage.setItem('authToken', 'mock-token');
        });

        // Mock User (Fresh user, no onboarding completed)
        await page.route('**/api/users/me', route => route.fulfill(json({
            id: 'u1',
            email: 'newuser@example.com',
            first_name: '',
            last_name: '',
            is_admin: false,
            is_active: true
        })));

        // Mock Capabilities & Stats
        await page.route('**/api/users/me/capabilities', route => route.fulfill(json({ has_elevenlabs: true, has_google_tts: true })));
        await page.route('**/api/users/me/stats', route => route.fulfill(json({ episodes_last_30d: 0 })));
        await page.route('**/api/billing/usage', route => route.fulfill(json({ processing_minutes_used_this_month: 0, max_processing_minutes_month: 100 })));
        await page.route('**/api/notifications/**', route => route.fulfill(json([])));
        await page.route('**/api/admin/summary', route => route.fulfill({ status: 403 })); // Not admin

        // Mock User Preferences Update
        await page.route('**/api/auth/users/me/prefs', route => route.fulfill(json({ success: true })));

        // Mock Onboarding Status (Not completed)
        await page.route('**/api/assistant/onboarding/status', route => route.fulfill(json({ completed: false })));

        // Mock Media & Assets
        await page.route('**/api/media/', route => route.fulfill(json([])));
        await page.route('**/api/music/assets**', route => route.fulfill(json({ assets: [{ id: 'm1', name: 'Funky Beat', url: 'http://example.com/music.mp3' }] })));
        await page.route('**/api/elevenlabs/voices**', route => route.fulfill(json({ voices: [{ voice_id: 'v1', name: 'Rachel' }] })));

        // Mock TTS Generation with verification
        await page.route('**/api/media/tts', async route => {
            const body = route.request().postDataJSON();
            if (!body.text || !body.category) {
                console.error('Invalid TTS request:', body);
                return route.abort();
            }
            return route.fulfill(json({ id: 'tts1', filename: 'intro.mp3', url: 'http://example.com/intro.mp3' }));
        });

        // Mock Website Checks
        await page.route('**/api/websites/check-subdomain**', route => route.fulfill(json({ available: true })));

        // Verify Podcast Creation Payload
        let podcastCreated = false;
        await page.route('**/api/podcasts/', async route => {
            if (route.request().method() === 'POST') {
                // Check if it's a multipart request (FormData)
                const headers = route.request().headers();
                if (!headers['content-type']?.includes('multipart/form-data')) {
                    console.error('Podcast creation must use FormData');
                    return route.abort();
                }
                podcastCreated = true;
                return route.fulfill(json({ id: 'pod1', name: 'My Awesome Podcast', slug: 'my-awesome-podcast' }));
            }
            return route.fulfill(json([]));
        });

        // Verify Template Creation Payload
        let templateCreated = false;
        await page.route('**/api/templates/', async route => {
            if (route.request().method() === 'POST') {
                const body = route.request().postDataJSON();
                // Verify critical fields
                if (!body.podcast_id || !body.segments || !Array.isArray(body.segments)) {
                    console.error('Invalid template payload:', body);
                    return route.abort();
                }
                templateCreated = true;
                return route.fulfill(json({ id: 'tpl1', name: 'My First Template' }));
            }
            return route.fulfill(json([]));
        });

        // 2. Start Test - Navigate to Onboarding
        await page.goto('/onboarding');

        // Step 1: Your Name
        await expect(page.getByRole('heading', { name: 'What can we call you?' })).toBeVisible();
        await page.getByPlaceholder('e.g., Alex').fill('Test');
        await page.getByPlaceholder('(Optional)').fill('User');
        await page.getByRole('button', { name: 'Continue' }).click();

        // Step 2: Choose Path (New vs Existing)
        await expect(page.getByRole('heading', { name: 'Do you have an existing podcast?' })).toBeVisible();
        await page.getByRole('button', { name: 'Start new' }).click();

        // Step 3: Show Details
        await expect(page.getByRole('heading', { name: 'About your show' })).toBeVisible();
        await page.getByPlaceholder('Enter your podcast name').fill('My Awesome Podcast');
        await page.getByPlaceholder('Describe your podcast in a few sentences').fill('A podcast about testing.');
        await page.getByRole('button', { name: 'Continue' }).click();

        // Step 4: Format
        await expect(page.getByRole('heading', { name: 'Format' })).toBeVisible();
        await page.getByText('Solo Monologue').click();
        await page.getByRole('button', { name: 'Continue' }).click();

        // Step 5: Cover Art (Skip)
        await expect(page.getByRole('heading', { name: 'Podcast Cover Art' })).toBeVisible();
        await page.getByRole('button', { name: 'Continue' }).click();

        // Step 6: Website Style (Design)
        await expect(page.getByRole('heading', { name: 'Website Style' })).toBeVisible();
        await page.getByRole('button', { name: 'Continue' }).click();

        // Step 7: Intro & Outro (Greeting)
        await expect(page.getByRole('heading', { name: 'How would you like to greet your listeners?' })).toBeVisible();
        // Use defaults (Script/TTS)
        await page.getByRole('button', { name: 'Continue' }).click();

        // Step 8: Music (Audio Setup)
        await expect(page.getByRole('heading', { name: 'Background music' })).toBeVisible();
        await page.getByRole('button', { name: 'Continue' }).click();

        // Step 9: Final Details (Frequency)
        await expect(page.getByRole('heading', { name: 'Final details' })).toBeVisible();
        await page.getByRole('combobox').selectOption('weekly');
        await page.getByRole('button', { name: 'Continue' }).click();

        // Step 10: Distribution
        await expect(page.getByRole('heading', { name: 'Get ready to distribute' })).toBeVisible();
        await page.getByRole('button', { name: 'Continue' }).click();

        // Step 11: Review (Finish)
        await expect(page.getByRole('heading', { name: 'Review' })).toBeVisible();
        await page.getByRole('button', { name: 'Finish' }).click();

        // Verify critical actions occurred
        await expect(async () => {
            expect(podcastCreated).toBe(true);
            expect(templateCreated).toBe(true);
        }).toPass();

        // Should redirect to success page or dashboard
        await expect(page.getByText('All set')).toBeVisible();
        await page.getByRole('link', { name: 'Go to Dashboard' }).click();

        // Verify critical actions occurred
        await expect(async () => {
            expect(podcastCreated).toBe(true);
            expect(templateCreated).toBe(true);
        }).toPass();

        // Should redirect to dashboard (or show loading)
        // We can check if we left the onboarding page
        await expect(page).not.toHaveURL(/\/onboarding/);
    });
});
