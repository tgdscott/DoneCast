from api.models.settings import AdminSettings, load_admin_settings, save_admin_settings


def test_admin_settings_persist_browser_flag(session):
    default_settings = load_admin_settings(session)
    assert default_settings.browser_audio_conversion_enabled is True

    saved = save_admin_settings(
        session,
        AdminSettings(browser_audio_conversion_enabled=False),
    )
    assert saved.browser_audio_conversion_enabled is False

    reloaded = load_admin_settings(session)
    assert reloaded.browser_audio_conversion_enabled is False


def test_public_config_includes_browser_flag(client, session):
    save_admin_settings(
        session,
        AdminSettings(max_upload_mb=5000, browser_audio_conversion_enabled=False),
    )

    resp = client.get("/api/public/config")
    assert resp.status_code == 200
    data = resp.json()

    assert data["browser_audio_conversion_enabled"] is False
    assert data["max_upload_mb"] == 2048
