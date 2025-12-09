import re
from playwright.sync_api import Page, expect


# NOTE: The base URL must point to your *running* application's frontend.
# The locators ('Email', 'Password', 'Sign In') must match the text or placeholders in your UI.


def test_successful_login(page: Page):
    """
    Tests the full end-to-end workflow of a user logging in successfully.
    """
    # 1. Navigate to the login page
    page.goto("http://localhost:8000/login")  # <<< CONFIRM THIS URL IS CORRECT

    # 2. Input valid credentials
    page.get_by_role("textbox", name="Email Address").fill("test_user@example.com") 
    page.get_by_role("textbox", name="password").fill("SuperSecretPassword")
    # 3. Click the login button
   
    # 4. Assert successful navigation/state change
    # Wait for the page to navigate to the dashboard/home URL
    # Playwright will wait for the navigation before checking the URL
    expect(page).to_have_url(re.compile(".*/dashboard"))  # <<< CONFIRM THE POST-LOGIN URL PATH

    # Optional: Check for a visible element on the dashboard (e.g., a "Sign Out" button)
    expect(page.get_by_role("link", name="Sign Out")).to_be_visible()
