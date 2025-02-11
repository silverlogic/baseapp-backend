import json

from django.core.management.color import no_style
from django.core.management.sql import sql_flush
from django.core.serializers import deserialize, serialize
from django.db import DEFAULT_DB_ALIAS, connections
from rest_framework import response, viewsets
from rest_framework.parsers import JSONParser

from baseapp_core.rest_framework.decorators import action
from baseapp_e2e.rest_framework.permissions import E2eEnabled

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
        connection = connections[DEFAULT_DB_ALIAS]
        style = no_style()
        sql_statements = sql_flush(style, connection)

        # Changing the constraints to IMMEDIATE to avoid issues with circular foreign keys like users<->profiles
        sql_statements = ["SET CONSTRAINTS ALL IMMEDIATE;"] + sql_statements

        connection.ops.execute_sql_flush(sql_statements)
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
