'''
isort:skip_file
'''

from .routers import DefaultRouter

router = DefaultRouter(trailing_slash=False)

# Login / Register
from .login.views import LoginViewSet  # noqa
from .register.views import RegisterViewSet  # noqa
from .social_auth.views import SocialAuthViewSet  # noqa

router.register(r'login', LoginViewSet, base_name='login')
router.register(r'register', RegisterViewSet, base_name='register')
router.register(r'social-auth', SocialAuthViewSet, base_name='social-auth')

# Users
from .users.views import UsersViewSet  # noqa

router.register(r'users', UsersViewSet, base_name='users')

# Forgot Password
from .forgot_password.views import ForgotPasswordViewSet, ResetPasswordViewSet  # noqa

router.register(r'forgot-password', ForgotPasswordViewSet, base_name='forgot-password')
router.register(r'forgot-password/reset', ResetPasswordViewSet, base_name='reset-password')

# Change Email
from .change_email.views import ChangeEmailViewSet  # noqa

router.register(r'change-email', ChangeEmailViewSet, base_name='change-email')
