from baseapp_core.rest_framework.routers import DefaultRouter

from .memberships.views import ProfileInvitationsViewSet, ProfileMembersViewSet

# Not mounted by the plugin: a project opts in by including `profiles_router.urls` in its
# v1 URL patterns (see the README).
profiles_router = DefaultRouter(trailing_slash=False)

profiles_router.register(r"profile-members", ProfileMembersViewSet, basename="profile-members")
profiles_router.register(
    r"profile-invitations", ProfileInvitationsViewSet, basename="profile-invitations"
)
