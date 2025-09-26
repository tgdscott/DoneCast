import { test, expect } from '@playwright/test';

function json(data: any, status = 200) {
  return { status, contentType: 'application/json', body: JSON.stringify(data) } as const;
}

test.describe('Visual snapshots: Home, Onboarding, Episode Creator', () => {
  test.beforeEach(async ({ page }) => {
    // Common default routes
    await page.route('**/api/users/me', (route) => route.fulfill(json({ id: 'u1', email: 'user@example.com', first_name: 'Test', role: 'user', is_admin: false })));
    await page.route('**/api/users/me/capabilities', (route) => route.fulfill(json({ has_elevenlabs: false, has_google_tts: false, has_any_sfx_triggers: false })));
    await page.route('**/api/billing/usage', (route) => route.fulfill(json({ processing_minutes_used_this_month: 0, max_processing_minutes_month: 1000 })));
    await page.route('**/api/users/me/stats', (route) => route.fulfill(json({ episodes_last_30d: 0, upcoming_scheduled: 0 })));
    await page.route('**/api/notifications/**', (route) => route.fulfill(json([])));
  });

  test('Home (landing) snapshot', async ({ page }) => {
    // Ensure anon state
    await page.addInitScript(() => { try { window.localStorage.removeItem('authToken'); } catch {} });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Podcast Plus Plus' })).toBeVisible();
    await expect(page).toHaveScreenshot('home-landing.png', { fullPage: true, animations: 'disabled' });
  });

  test('Onboarding snapshot (branch selector)', async ({ page }) => {
    await page.addInitScript(() => { try { window.localStorage.setItem('authToken', 'e2e-token'); } catch {} });
    await page.route('**/api/podcasts/', (route) => route.fulfill(json([])));
    await page.goto('/?onboarding=1');
    await expect(page.getByRole('heading', { name: /Welcome! Let's get your podcast set up\./i })).toBeVisible();
    await expect(page).toHaveScreenshot('onboarding-branch.png', { fullPage: true, animations: 'disabled' });
  });

  test('Episode Creator Step 5 snapshot', async ({ page }) => {
    await page.addInitScript(() => { try { window.localStorage.setItem('authToken', 'e2e-token'); } catch {} });
    await page.route('**/api/podcasts/', (route) => route.fulfill(json([{ id: 'pod1', title: 'My Show' }])));
    const tpl = { id: 'tpl1', name: 'Tpl One', podcast_id: 'pod1', ai_settings: { auto_fill_ai: true, auto_generate_tags: true }, segments: [{ id: 'seg-content', segment_type: 'content', source: { source_type: 'content' } }] };
    await page.route('**/api/templates/', (route) => route.fulfill(json([tpl])));
    await page.route('**/api/templates/tpl1', (route) => route.fulfill(json(tpl)));
    await page.route('**/api/episodes/last/numbering', (route) => route.fulfill(json({ season_number: 1, episode_number: 1 })));
    await page.route('**/api/ai/transcript-ready**', (route) => route.fulfill(json({ ready: true })));
    await page.route('**/api/media/upload/main_content', (route) => route.fulfill(json([{ filename: 'in.wav', friendly_name: 'in.wav' }])));
    await page.route('**/api/flubber/prepare-by-file', (route) => route.fulfill(json({ contexts: [] })));

    await page.goto('/');
    await page.getByRole('button', { name: /New Episode/i }).click();
    const chooseBtn = page.getByRole('button', { name: /Choose Audio File/i });
    const fileChooserPromise = page.waitForEvent('filechooser');
    await chooseBtn.click();
    const fc = await fileChooserPromise;
    await fc.setFiles({ name: 'in.wav', mimeType: 'audio/wav', buffer: Buffer.from([82,73,70,70,0,0,0,0,87,65,86,69]) });
    const continueBtn = page.getByRole('button', { name: /^Continue$/i });
    if (await continueBtn.isVisible()) await continueBtn.click();
    await page.getByRole('button', { name: /Continue to Details/i }).click();
    const skipBtn = page.getByRole('button', { name: /^Skip$/i });
    if (await skipBtn.isVisible()) await skipBtn.click();
    await expect(page.getByText(/Details & Schedule|Details & Review/i)).toBeVisible();
    await expect(page).toHaveScreenshot('episode-creator-step5.png', { fullPage: true, animations: 'disabled' });
  });
});
