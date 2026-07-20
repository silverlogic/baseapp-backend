def make_text_into_quill(text) -> str:
    return '{"delta": [], "html": "' + text + '", "ops": []}'
