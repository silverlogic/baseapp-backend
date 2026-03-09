import base64
import binascii
import logging
import typing

from cryptography.hazmat.primitives.ciphers.aead import AESSIV
from django.conf import ImproperlyConfigured, settings
from django.db import models
from django.utils.crypto import get_random_string

from baseapp_auth.querysets import BaseAPIKeyQuerySet

logger = logging.getLogger(__name__)


class BaseAPIKeyManager(models.Manager):
    api_key_prefix: str

    def __init__(
        self,
        *args,
        api_key_prefix: str,
        QuerySetClass: typing.Type[models.QuerySet] = BaseAPIKeyQuerySet,
        **kwargs,
    ):
        self.api_key_prefix = api_key_prefix
        super().__init__(*args, **kwargs)
        self._queryset_class = QuerySetClass

    def generate_encryption_key(self) -> str:
        """
        Generate an encryption key suitable to be used for django.conf.settings.BA_API_KEY_ENCRYPTION_KEY
        """
        key = AESSIV.generate_key(bit_length=512)
        encoded_key = base64.urlsafe_b64encode(key).decode()
        return encoded_key

    def generate_unencrypted_api_key(self) -> str:
        """
        Generates a new unencrypted API key string.

        The API key follows the format: {prefix}-{random_string} where:
        - prefix is the api_key_prefix set on the manager instance
        - random_string is a 64 character random string

        Returns:
            str: The generated API key string
        """
        api_key = f"{self.api_key_prefix}-{get_random_string(length=64)}"
        return api_key

    def encrypt(self, unencrypted_value: str | bytes, encryption_key: str | None = None) -> bytes:
        """
        Encrypts a value using AES-SIV encryption.

        Args:
            unencrypted_value: The value to encrypt, either as a string or bytes.
            encryption_key: Optional encryption key. Defaults to settings.BA_API_KEY_ENCRYPTION_KEY.

        Returns:
            bytes: The encrypted value as bytes.
        """
        unencrypted_data: bytes
        if isinstance(unencrypted_value, bytes):
            unencrypted_data = unencrypted_value
        elif isinstance(unencrypted_value, str):
            unencrypted_data = unencrypted_value.encode()
        else:
            raise TypeError("unencrypted_value must be str or bytes")

        encryption_key = self._get_encryption_key(encryption_key)
        aessiv = AESSIV(base64.urlsafe_b64decode(encryption_key))
        associated_data = []

        encrypted_data = binascii.b2a_hex(aessiv.encrypt(unencrypted_data, associated_data))
        return encrypted_data

    def decrypt(self, encrypted_value: bytes, encryption_key: str | None = None) -> str:
        """
        Decrypts a value using AES-SIV encryption.

        Args:
            encrypted_value: The encrypted value, as bytes.
            encryption_key: Optional encryption key. Defaults to settings.BA_API_KEY_ENCRYPTION_KEY.

        Returns:
            bytes: The decrypted value as str.
        """
        encryption_key = self._get_encryption_key(encryption_key)
        aessiv = AESSIV(base64.urlsafe_b64decode(encryption_key))
        associated_data = []

        decrypted_data = aessiv.decrypt(binascii.a2b_hex(encrypted_value), associated_data)
        return decrypted_data.decode()

    def rotate_encryption_key(self, encryption_key_old: str, encryption_key_new: str):
        """
        Rotates the encryption key used for API keys by decrypting with the old key and re-encrypting with the new key.

        Args:
            encryption_key_old: The old encryption key used to decrypt existing API keys
            encryption_key_new: The new encryption key to use for re-encrypting API keys
        """

        for api_key in self.all():
            logger.info(f"Rotating encrypted_api_key for {api_key}")
            unencrypted_api_key = self.decrypt(
                encrypted_value=api_key.encrypted_api_key, encryption_key=encryption_key_old
            )
            api_key.encrypted_api_key = self.encrypt(
                unencrypted_value=unencrypted_api_key, encryption_key=encryption_key_new
            )
            api_key.save(update_fields=["encrypted_api_key"])
            logger.info(f"Rotated encrypted_api_key for {api_key}")

    def get_queryset(self, *args, **kwargs) -> models.QuerySet:
        return super().get_queryset(*args, **kwargs).add_is_expired()

    def _get_encryption_key(self, encryption_key: str | None = None) -> str:
        if not isinstance(encryption_key, str):
            if not settings.BA_API_KEY_ENCRYPTION_KEY:
                raise ImproperlyConfigured("BA_API_KEY_ENCRYPTION_KEY is not set")
            encryption_key = settings.BA_API_KEY_ENCRYPTION_KEY
        return encryption_key
