from baseapp_core.settings.env import env


class TestEnv:

    def test_return_default(self):
        assert env("TEST", default="default") == "default"
        assert env("TEST", "default") == "default"

    def test_return_falsy_default(self):
        assert env("TEST", default=None) is None
        assert env("TEST", None) is None

    def test_not_required_with_falsy_default(self):
        assert env("TEST", required=False) is None
        assert env("TEST", False, True) is False
