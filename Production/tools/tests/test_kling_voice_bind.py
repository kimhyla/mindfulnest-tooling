def test_setup_character_voice_requires_confirm_when_active(monkeypatch):
    from kling_element_voice import setup_character_voice

    cfg = {
        "status": "active",
        "element_id": "111",
        "kling_voice_id": "222",
        "frontal_image": "Lorelai/poses/x.png",
        "refer_images": ["Lorelai/poses/x.png"],
    }
    try:
        setup_character_voice("Lorelai", cfg, "ws-key", force=True, confirm_voice_overwrite=False)
        assert False, "expected RuntimeError"
    except RuntimeError as exc:
        assert "confirm-voice-overwrite" in str(exc).lower() or "confirm" in str(exc).lower()
