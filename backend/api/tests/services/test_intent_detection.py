from api.services.intent_detection import analyze_intents


def _words(*tokens):
    return [{"word": t} for t in tokens]


def test_analyze_intents_counts_and_matches():
    words = _words(
        "Hello",
        "Intern",
        "please",
        "rim",
        "shot",
        "flubber",
        "applause",
        "intern",
    )

    commands_cfg = {
        "flubber": {"trigger_keyword": "Flubber"},
        "intern": {"trigger_keyword": "intern"},
        "rim_shot": {"action": "sfx", "trigger_keyword": "rim shot"},
    }

    extra_sfx = [
        {"phrase": "applause", "label": "Applause", "source": "media:test"},
    ]

    result = analyze_intents(words, commands_cfg, extra_sfx)

    assert result["flubber"]["count"] == 1
    assert result["intern"]["count"] == 2

    sfx = result["sfx"]
    assert sfx["count"] == 2
    labels = sorted(match["label"] for match in sfx["matches"])
    assert labels == ["Applause", "rim_shot"]


def test_analyze_intents_respects_aliases_and_lists():
    words = _words("redo", "redo", "FLUBBER", "siren")
    commands_cfg = {
        "flubber": {"trigger_keyword": "redo|flubber"},
        "siren": {"action": "sfx", "aliases": ["siren"], "trigger_keyword": "air horn"},
    }

    result = analyze_intents(words, commands_cfg, None)
    assert result["flubber"]["count"] == 3
    assert result["sfx"]["count"] == 1
