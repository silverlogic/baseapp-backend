import importlib
import json
from urllib.parse import urljoin, urlparse

from django.conf import settings
from django.http import Http404, HttpResponse
from django.utils.decorators import method_decorator
from django.utils.encoding import iri_to_uri
from django.views.decorators.cache import never_cache
from requests import HTTPError
from rest_framework import serializers, status, viewsets
from rest_framework.response import Response
from rest_social_auth.views import (
    DOMAIN_FROM_ORIGIN,
    SocialTokenOnlyAuthView,
    decorate_request,
)
from social_core.exceptions import AuthException
from social_core.utils import parse_qs, user_is_authenticated

from .cache.models import SocialAuthAccessTokenCache
from .serializers import SocialAuthOAuth1Serializer, SocialAuthOAuth2Serializer


class SocialAuthViewSet(SocialTokenOnlyAuthView, viewsets.GenericViewSet):
    oauth1_serializer_class_in = SocialAuthOAuth1Serializer
    oauth2_serializer_class_in = SocialAuthOAuth2Serializer

    def create(self, request, *args, **kwargs):
        pipeline_module = importlib.import_module(settings.SOCIAL_AUTH_PIPELINE_MODULE)
        try:
            return self.do(request, *args, **kwargs)
        except Http404:
            raise serializers.ValidationError({"provider": ["Invalid provider"]})
        except pipeline_module.EmailNotProvidedError:
            raise serializers.ValidationError({"email": "no_email_provided"})
        except pipeline_module.EmailAlreadyExistsError:
            raise serializers.ValidationError({"email": "email_already_in_use"})

    @method_decorator(never_cache)
    def do(self, request, *args, **kwargs):
        input_data = self.get_serializer_in_data()
        provider_name = self.get_provider_name(input_data)
        if not provider_name:
            return self.respond_error("Provider is not specified")
        self.set_input_data(request, input_data)
        decorate_request(request, provider_name)
        serializer_in = self.get_serializer_in(data=input_data)
        if self.oauth_v1() and request.backend.OAUTH_TOKEN_PARAMETER_NAME not in input_data:
            # oauth1 first stage (1st is get request_token, 2nd is get access_token)
            manual_redirect_uri = input_data.get("redirect_uri", None)
            if manual_redirect_uri:
                self.request.backend.redirect_uri = manual_redirect_uri
            request_token = parse_qs(request.backend.set_unauthorized_token())
            return Response(request_token)
        serializer_in.is_valid(raise_exception=True)
        try:
            user = self.get_object()
        except (AuthException, HTTPError) as e:
            return self.respond_error(e)
        if isinstance(
            user, HttpResponse
        ):  # An error happened and pipeline returned HttpResponse instead of user
            return user
        resp_data = self.get_serializer(instance=user)
        self.do_login(request.backend, user)
        data = resp_data.data
        data["is_new"] = user.is_new
        return Response(data)

    def get_object(self):
        user = self.request.user
        manual_redirect_uri = self.request.auth_data.pop("redirect_uri", None)
        manual_redirect_uri = self.get_redirect_uri(manual_redirect_uri)
        if manual_redirect_uri:
            self.request.backend.redirect_uri = manual_redirect_uri
        elif DOMAIN_FROM_ORIGIN:
            origin = self.request.strategy.request.META.get("HTTP_ORIGIN")
            if origin:
                relative_path = urlparse(self.request.backend.redirect_uri).path
                url = urlparse(origin)
                origin_scheme_host = "%s://%s" % (url.scheme, url.netloc)
                location = urljoin(origin_scheme_host, relative_path)
                self.request.backend.redirect_uri = iri_to_uri(location)
        is_authenticated = user_is_authenticated(user)
        user = is_authenticated and user or None
        # skip checking state by setting following params to False
        # it is responsibility of front-end to check state
        # TODO: maybe create an additional resource, where front-end will
        # store the state before making a call to oauth provider
        # so server can save it in session and consequently check it before
        # sending request to acquire access token.
        # In case of token authentication we need a way to store an anonymous
        # session to do it.
        self.request.backend.REDIRECT_STATE = False
        self.request.backend.STATE_PARAMETER = False

        # Deal with cached access token.
        access_token = None
        oauth_token = self.request.data.get("oauth_token")
        oauth_verifier = self.request.data.get("oauth_verifier")
        code = self.request.data.get("code")
        if oauth_token and oauth_verifier:
            try:
                c = SocialAuthAccessTokenCache.objects.get(
                    oauth_token=oauth_token, oauth_verifier=oauth_verifier
                )
                access_token = c.access_token
            except SocialAuthAccessTokenCache.DoesNotExist:
                pass
        elif code:
            try:
                c = SocialAuthAccessTokenCache.objects.get(code=code)
                access_token = c.access_token
            except SocialAuthAccessTokenCache.DoesNotExist:
                pass

        if access_token:
            try:
                access_token = json.loads(access_token)
            except:  # noqa
                pass
            user = self.request.backend.do_auth(access_token)
        else:
            user = self.request.backend.complete(user=user)

        return user

    def respond_error(self, error):
        if isinstance(error, (AuthException, HTTPError)):
            raise serializers.ValidationError({"non_field_errors": "invalid_credentials"})
        return Response(status=status.HTTP_400_BAD_REQUEST)
