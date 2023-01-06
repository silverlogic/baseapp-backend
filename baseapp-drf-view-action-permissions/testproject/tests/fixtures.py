from rest_framework.test import APIClient


class Client(APIClient):
    def force_authenticate(self, user):
        self.user = user
        super().force_authenticate(user)
