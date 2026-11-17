import json
import os

from core.pipeline import redact

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "samples", "test.txt")
EXPECTED = os.path.join(os.path.dirname(__file__), "..", "samples", "test.expected.json")


def test_end_to_end_text_level1(tmp_path):
    result = redact(SAMPLE, level=1, out_dir=str(tmp_path))
    out = open(result.out_path, encoding="utf-8").read()
    expected = json.load(open(EXPECTED))
    # Everything the stub detector is supposed to find must be gone.
    for item in expected["must_find"]:
        if item["type"] in expected["stub_can_find_now"]:
            assert item["text"] not in out, f"{item['text']} leaked"
    assert result.log["verified_clean"] is True


def test_log_never_contains_original_text(tmp_path):
    result = redact(SAMPLE, level=1, out_dir=str(tmp_path))
    log_text = json.dumps(result.log)
    for item in json.load(open(EXPECTED))["must_find"]:
        assert item["text"] not in log_text, "log leaked an original value"
