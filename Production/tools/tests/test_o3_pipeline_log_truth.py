from pathlib import Path
PIPELINE = Path(__file__).resolve().parent.parent / "kling_o3_element_beat_pipeline.py"

def test_o3_submit_log_does_not_hardcode_char_ref_aligned_true():
    text = PIPELINE.read_text(encoding="utf-8")
    block = text.split('"phase": "o3_submit"', 1)[1].split("}), flush=True)", 1)[0]
    assert '"char_ref_aligned": True' not in block
    assert "char_ref_gate_detail" in block
