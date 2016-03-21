'''
isort:skip_file
'''

from rest_framework.routers import DefaultRouter

router = DefaultRouter(trailing_slash=False)

# Register
from .register.views import RegisterViewSet  # noqa

router.register(r'register', RegisterViewSet, base_name='register')

# Users
from .users.views import UsersViewSet  # noqa

router.register(r'users', UsersViewSet, base_name='users')
