from baseapp_e2e.utils import load_script
from rest_framework import serializers


class LoadDataSerializer(serializers.Serializer):
    objects = serializers.JSONField(required=True)


class LoadScriptSerializer(serializers.Serializer):
    scripts = serializers.ListField(child=serializers.CharField())

    def save(self):
        for script in self.validated_data["scripts"]:
            load_script(script)
