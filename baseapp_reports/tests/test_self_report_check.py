from unittest.mock import Mock

from baseapp_reports.graphql.mutations import get_target_author_profile_id


class TestGetTargetAuthorProfileId:
    def test_target_with_get_author_profile_method(self):
        mock_profile = Mock(pk=42)
        target = Mock(spec=[])
        target.get_author_profile = Mock(return_value=mock_profile)
        assert get_target_author_profile_id(target) == 42

    def test_target_with_get_author_profile_returning_none(self):
        target = Mock(spec=[])
        target.get_author_profile = Mock(return_value=None)
        assert get_target_author_profile_id(target) is None

    def test_target_with_profile_id_fk(self):
        target = Mock(spec=["profile_id"])
        target.profile_id = 7
        assert get_target_author_profile_id(target) == 7

    def test_target_without_profile_semantics(self):
        target = Mock(spec=[])
        assert get_target_author_profile_id(target) is None

    def test_profile_id_takes_precedence_after_get_author_profile(self):
        """get_author_profile is checked first, then profile_id."""
        mock_profile = Mock(pk=99)
        target = Mock(spec=["profile_id"])
        target.get_author_profile = Mock(return_value=mock_profile)
        target.profile_id = 7
        assert get_target_author_profile_id(target) == 99
