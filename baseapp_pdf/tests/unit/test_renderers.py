import json

from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory
from rest_framework.views import APIView

from baseapp_pdf.rest_framework.renderers import PDFRenderer

PDF = b"%PDF-1.7 not really"


class InvoiceView(APIView):
    authentication_classes = []
    permission_classes = []
    renderer_classes = [PDFRenderer]

    def get(self, request, *args, **kwargs) -> Response:
        if request.query_params.get("fail"):
            raise ValidationError({"invoice": ["Not ready yet."]})
        return Response(PDF)


def get(path: str, **headers) -> Response:
    response = InvoiceView.as_view()(APIRequestFactory().get(path, **headers))
    response.render()
    return response


class TestPDFRenderer:
    def test_attributes(self) -> None:
        assert PDFRenderer.media_type == "application/pdf"
        assert PDFRenderer.format == "pdf"

    def test_bytes_pass_through(self) -> None:
        response = get("/invoice", HTTP_ACCEPT="application/pdf")

        assert response["Content-Type"] == "application/pdf"
        assert response.content == PDF

    def test_format_query_parameter(self) -> None:
        assert get("/invoice?format=pdf").content == PDF

    def test_errors_are_rendered_as_json(self) -> None:
        response = get("/invoice?fail=1", HTTP_ACCEPT="application/pdf")

        assert response.status_code == 400
        assert response["Content-Type"] == "application/json"
        assert json.loads(response.content) == {"invoice": ["Not ready yet."]}

    def test_render_without_a_response(self) -> None:
        renderer = PDFRenderer()

        assert renderer.render(bytearray(b"%PDF")) == b"%PDF"
        assert renderer.render(memoryview(b"%PDF")) == b"%PDF"
        assert json.loads(renderer.render({"detail": "x"})) == {"detail": "x"}
        assert renderer.render(None) == b""
