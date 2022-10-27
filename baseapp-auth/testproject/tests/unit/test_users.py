from apps.users.models import User


def test_user_str():
    user = User(email="john@gmail.com")
    assert str(user) == "john@gmail.com"


def test_user_get_short_name():
    user = User(email="john@gmail.com")
    assert user.get_short_name() == "john@gmail.com"


def test_user_get_full_name():
    user = User(first_name="John", last_name="Doe", email="john@gmail.com")
    assert user.get_full_name() == "John Doe"


def test_user_get_full_name_as_email():
    """
    User instance without name returns email, so names in django returns e-mail
    (which is required) in order to debug.
    """
    user = User(email="john@gmail.com")
    assert user.get_full_name() == "john@gmail.com"
