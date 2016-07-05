'''
isort:skip_file
'''

from rest_framework.routers import DefaultRouter

router = DefaultRouter(trailing_slash=False)

# Login / Register
from .login.views import LoginViewSet  # noqa
from .register.views import RegisterViewSet  # noqa

router.register(r'login', LoginViewSet, base_name='login')
router.register(r'register', RegisterViewSet, base_name='register')

# Users
from .users.views import UsersViewSet  # noqa

router.register(r'users', UsersViewSet, base_name='users')
