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


def test_frontend_uses_per_tab_session_and_exposes_human_color_controls() -> None:
    html = (PROJECT_ROOT / "frontend" / "index.html").read_text()
    javascript = (PROJECT_ROOT / "frontend" / "main.js").read_text()

    assert "sessionStorage.getItem(LOCAL_SESSION_STORAGE_KEY)" in javascript
    assert "localStorage.getItem(LOCAL_SESSION_STORAGE_KEY)" not in javascript
    assert 'id="color-black-button"' in html
    assert 'id="color-white-button"' in html
    assert 'id="color-random-button"' in html
    assert 'requestJson("/api/ai-color"' in javascript


def test_frontend_confirms_destructive_setting_changes_and_shows_candidates() -> None:
    html = (PROJECT_ROOT / "frontend" / "index.html").read_text()
    javascript = (PROJECT_ROOT / "frontend" / "main.js").read_text()

    assert "confirmStateReset" in javascript
    assert 'id="ai-debug-candidates"' in html
    assert "decision?.candidates" in javascript
    assert "普通 AI 思考中…" not in javascript
