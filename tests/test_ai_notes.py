import importlib


def test_notes_parsing_and_nonempty_description(monkeypatch):
    mod = importlib.import_module('api.services.ai_content.generators.notes')

    # Return a simple formatted response
    def fake_generate(prompt, max_tokens=None, system_instruction=None):
        return (
            "Description: This episode dives into testing AI notes.\n\n"
            "Bullets:\n"
            "- First point\n"
            "- Second point\n"
        )

    monkeypatch.setattr(mod, 'generate', fake_generate)

    Inp = importlib.import_module('api.services.ai_content.schemas').SuggestNotesIn
    out = mod.suggest_notes(Inp(episode_id='11111111-1111-1111-1111-111111111111', podcast_id='22222222-2222-2222-2222-222222222222', transcript_path=None, extra_instructions=None, base_prompt=None, history_count=3))

    assert isinstance(out.description, str) and len(out.description.strip()) > 0
    assert isinstance(out.bullets, list)
    assert all(isinstance(b, str) for b in out.bullets)
