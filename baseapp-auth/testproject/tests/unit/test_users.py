from apps.users.models import User


def test_user_str():
    user = User(email='john@gmail.com')
    assert str(user) == 'john@gmail.com'


def test_user_get_short_name():
    user = User(email='john@gmail.com')
    assert user.get_short_name() == 'john@gmail.com'


def test_user_get_full_name():
    user = User(email='john@gmail.com')
    assert user.get_full_name() == 'john@gmail.com'
