import json

from baseapp_core.rest_framework.decorators import action
from baseapp_e2e.rest_framework.permissions import E2eEnabled
from django.core import management
from django.core.management.commands import flush
from django.core.serializers import deserialize, serialize
from rest_framework import response, viewsets
from rest_framework.parsers import JSONParser

from .serializers import (
    LoadDataSerializer,
    LoadScriptSerializer,
    SetUserPasswordSerializer,
)


class E2EViewSet(viewsets.ViewSet):
    permission_classes = [E2eEnabled]
    parser_classes = [JSONParser]

    @action(detail=False, methods=["POST"])
    def load_data(self, request):
        serializer = LoadDataSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        objects = []
        for obj in deserialize("json", (json.dumps(serializer.validated_data["objects"]))):
            obj.save()
            objects.append(obj.object)
        return response.Response({"objects": json.loads(serialize("json", objects))})

    @action(detail=False, methods=["POST"])
    def flush_data(self, request):
        management.call_command(flush.Command(), verbosity=0, interactive=False)
        return response.Response({"detail": "success"})

    @action(detail=False, methods=["POST"])
    def load_script(self, request):
        serializer = LoadScriptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response({"detail": "success"})

    @action(detail=False, methods=["POST"])
    def set_password(self, request):
        serializer = SetUserPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return response.Response({"detail": "success"})
