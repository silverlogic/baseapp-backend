from unittest.mock import Mock

import pytest

from baseapp_profiles.tests.factories import ProfileFactory
from baseapp_reports.graphql.mutations import get_target_author_profile_id

pytestmark = pytest.mark.django_db


class TestGetTargetAuthorProfileId:
    def test_reportable_target_default_returns_none(self):
        """ReportableModel.get_author_profile() returns None by default."""
        profile = ProfileFactory()
        assert get_target_author_profile_id(profile) is None

    def test_reportable_target_with_author_override(self):
        """Subclass overriding get_author_profile returns the author's pk."""
        author = ProfileFactory()
        target = ProfileFactory()
        target.get_author_profile = lambda: author
        assert get_target_author_profile_id(target) == author.pk

    def test_reportable_author_override_returning_none(self):
        """Override that returns None is respected."""
        target = ProfileFactory()
        target.get_author_profile = lambda: None
        assert get_target_author_profile_id(target) is None

    def test_non_reportable_target_with_profile_id(self):
        """Falls back to profile_id FK for non-ReportableModel targets."""
        author = ProfileFactory()
        target = Mock(spec=["profile_id"])
        target.profile_id = author.pk
        assert get_target_author_profile_id(target) == author.pk

    def test_non_reportable_target_without_profile_semantics(self):
        """Returns None when target has no author concept."""
        target = Mock(spec=[])
        assert get_target_author_profile_id(target) is None
