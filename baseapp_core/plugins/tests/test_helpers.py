import pytest

from baseapp_core.plugins.helpers import apply_if_installed


class TestApplyIfInstalled:
    def test_returns_response_when_app_is_installed(self, monkeypatch):
        monkeypatch.setattr("baseapp_core.plugins.helpers.apps.is_installed", lambda _: True)

        assert apply_if_installed("baseapp_profiles", ["profile"]) == ["profile"]

    def test_executes_response_callable_when_app_is_installed(self, monkeypatch):
        monkeypatch.setattr("baseapp_core.plugins.helpers.apps.is_installed", lambda _: True)

        result = apply_if_installed(
            "baseapp_profiles",
            lambda prefix, *, suffix: f"{prefix}-{suffix}",
            execute_callable=True,
            callable_args=["profiles"],
            callable_kwargs={"suffix": "enabled"},
        )

        assert result == "profiles-enabled"

    def test_returns_callable_without_executing_when_flag_is_false(self, monkeypatch):
        monkeypatch.setattr("baseapp_core.plugins.helpers.apps.is_installed", lambda _: True)

        response = lambda: "profiles-enabled"  # noqa: E731

        assert apply_if_installed("baseapp_profiles", response) is response

    @pytest.mark.parametrize(
        ("response", "expected"),
        [
            ([], []),
            ({}, {}),
            ("profile", ""),
            (True, False),
            (1, None),
            ({1, 2}, set()),
            (frozenset({1, 2}), frozenset()),
            ((1, 2), ()),
        ],
    )
    def test_returns_type_matched_fallback_when_app_is_not_installed(
        self,
        monkeypatch,
        response,
        expected,
    ):
        monkeypatch.setattr("baseapp_core.plugins.helpers.apps.is_installed", lambda _: False)

        assert apply_if_installed("baseapp_profiles", response) == expected

    def test_returns_explicit_fallback_when_type_matching_is_disabled(self, monkeypatch):
        monkeypatch.setattr("baseapp_core.plugins.helpers.apps.is_installed", lambda _: False)

        assert apply_if_installed(
            "baseapp_profiles",
            ["profile"],
            fallback_response=["user"],
            fallback_match_response_type=False,
        ) == ["user"]

    def test_executes_fallback_callable_when_app_is_not_installed(self, monkeypatch):
        monkeypatch.setattr("baseapp_core.plugins.helpers.apps.is_installed", lambda _: False)

        result = apply_if_installed(
            "baseapp_profiles",
            ["profile"],
            fallback_response=lambda prefix, *, suffix: f"{prefix}-{suffix}",
            fallback_match_response_type=False,
            execute_callable=True,
            callable_args=["profiles"],
            callable_kwargs={"suffix": "disabled"},
        )

        assert result == "profiles-disabled"
