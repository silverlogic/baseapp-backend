from django.db import connection
from django.test import TestCase

from baseapp_core.models import (
    CaseInsensitiveCharField,
    CaseInsensitiveEmailField,
    CaseInsensitiveTextField,
)


class TestCaseInsensitiveFields(TestCase):

    def test_case_insensitive_char_field_db_type(self):
        field = CaseInsensitiveCharField()
        db_type = field.db_type(connection)
        assert db_type == "citext", f"Expected 'citext', but got {db_type}"

    def test_case_insensitive_text_field_db_type(self):
        field = CaseInsensitiveTextField()
        db_type = field.db_type(connection)
        assert db_type == "citext", f"Expected 'citext', but got {db_type}"

    def test_case_insensitive_email_field_db_type(self):
        field = CaseInsensitiveEmailField()
        db_type = field.db_type(connection)
        assert db_type == "citext", f"Expected 'citext', but got {db_type}"
