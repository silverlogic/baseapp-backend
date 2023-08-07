from django.urls import re_path
from trench.views.jwt import MFAFirstStepJWTView, MFASecondStepJWTView

urlpatterns = (
    re_path(r"/login", MFAFirstStepJWTView.as_view(), name="generate-code-jwt"),
    re_path(r"/login/code", MFASecondStepJWTView.as_view(), name="generate-token-jwt"),
)
