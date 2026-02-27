"""safe_js_inject — XSS-safe markdown injection via json.dumps()."""
import json
import logging

logger = logging.getLogger(__name__)


def safe_js_inject(sb, content_selector: str, markdown_text: str) -> bool:
    """
    json.dumps()로 인코딩하여 XSS/이스케이프 위험 없이 본문 주입.
    f-string 직접 삽입 금지 (보안 취약점).
    """
    try:
        encoded = json.dumps(markdown_text)
        script = f"""
        var editor = document.querySelector({json.dumps(content_selector)});
        if (editor && editor.CodeMirror) {{
            editor.CodeMirror.setValue({encoded});
            return true;
        }}
        return false;
        """
        result = sb.execute_script(script)
        if not result:
            logger.warning("CodeMirror 주입 실패 — fallback 시도")
        return bool(result)
    except Exception as e:
        logger.error(f"JS 주입 실패: {e}")
        return False
