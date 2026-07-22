from pathlib import Path
import re


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_frontend_enables_normal_and_keeps_hard_disabled() -> None:
    html = (PROJECT_ROOT / "frontend" / "index.html").read_text()
    normal_tag = re.search(r'<button id="difficulty-normal-button"[^>]*>', html)
    hard_tag = re.search(r'<button id="difficulty-hard-button"[^>]*>', html)
    assert normal_tag is not None and "disabled" not in normal_tag.group(0)
    assert hard_tag is not None and "disabled" in hard_tag.group(0)


def test_frontend_posts_selected_difficulty() -> None:
    javascript = (PROJECT_ROOT / "frontend" / "main.js").read_text()
    assert 'requestJson("/api/difficulty"' in javascript
    assert 'changeDifficulty("normal")' in javascript


def test_frontend_exposes_ai_debug_export_controls() -> None:
    html = (PROJECT_ROOT / "frontend" / "index.html").read_text()
    javascript = (PROJECT_ROOT / "frontend" / "main.js").read_text()
    assert 'id="ai-debug-panel"' in html
    assert 'id="copy-debug-button"' in html
    assert 'id="download-debug-button"' in html
    assert 'requestJson("/api/debug-position")' in javascript
