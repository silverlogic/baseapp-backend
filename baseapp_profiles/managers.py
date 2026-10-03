import swapper
from django.contrib.auth.models import AbstractBaseUser, AnonymousUser
from django.db import models


class ProfileManager(models.Manager):
    def _active_membership_subquery(self, user: AbstractBaseUser | AnonymousUser) -> models.Exists:
        """
        `Exists()` subquery matching profiles `user` is an ACTIVE member of.

        An `Exists()` subquery is used rather than a `members__user` join so that the
        resulting queryset neither duplicates rows nor needs `.distinct()`.
        """
        ProfileUserRole = swapper.load_model("baseapp_profiles", "ProfileUserRole")
        return models.Exists(
            ProfileUserRole.objects.filter(
                profile_id=models.OuterRef("pk"),
                user_id=user.id,
                status=ProfileUserRole.ProfileRoleStatus.ACTIVE,
            )
        )

    def filter_user_profiles(self, user: AbstractBaseUser | AnonymousUser) -> models.QuerySet:
        """Profiles `user` owns or is an ACTIVE member of."""
        return self.filter(models.Q(owner=user) | models.Q(self._active_membership_subquery(user)))

    def get_if_member(
        self, user: AbstractBaseUser | AnonymousUser, **kwargs
    ) -> models.Model | None:
        """The profile matching `kwargs` when `user` owns it or is an ACTIVE member of it."""
        if user.is_superuser:
            return self.get(**kwargs)
        return self.filter(
            models.Q(owner=user) | models.Q(self._active_membership_subquery(user)), **kwargs
        ).first()
