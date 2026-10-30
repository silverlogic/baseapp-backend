import typing

from rest_framework.renderers import BaseRenderer, JSONRenderer


class PDFRenderer(BaseRenderer):
    """
    Lets a view answer `Accept: application/pdf` (or `?format=pdf`) with PDF bytes.

    The view returns the PDF as `Response(pdf_bytes)`; those bytes pass through untouched.
    Anything else, such as the error payload of a failed request, is rendered as JSON and
    the response's content type is switched to `application/json` to match.
    """

    media_type = "application/pdf"
    format = "pdf"
    charset = None
    render_style = "binary"

    def render(
        self,
        data: typing.Any,
        accepted_media_type: str | None = None,
        renderer_context: dict | None = None,
    ) -> bytes:
        if isinstance(data, (bytes, bytearray, memoryview)):
            return bytes(data)

        renderer_context = renderer_context or {}
        response = renderer_context.get("response")
        json_renderer = JSONRenderer()
        if response is not None:
            response["Content-Type"] = json_renderer.media_type
        return json_renderer.render(data, json_renderer.media_type, renderer_context)
