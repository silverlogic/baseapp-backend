from django.contrib.auth import get_user_model
from rest_framework import serializers

from baseapp_e2e.utils import load_script

User = get_user_model()


class LoadDataSerializer(serializers.Serializer):
    objects = serializers.JSONField(required=True)


class LoadScriptSerializer(serializers.Serializer):
    scripts = serializers.ListField(child=serializers.CharField())

    def save(self):
        for script in self.validated_data["scripts"]:
            load_script(script)


class SetUserPasswordSerializer(serializers.Serializer):
    user = serializers.IntegerField(required=True)
    password = serializers.CharField(required=True)

    def save(self):
        user = User.objects.get(pk=self.validated_data["user"])
        user.set_password(self.validated_data["password"])
        user.save()
