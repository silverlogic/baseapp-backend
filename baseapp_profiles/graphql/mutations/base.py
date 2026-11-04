from typing import Any

import graphene

from baseapp_core.graphql import RelayMutation


class ExtensibleMutation(RelayMutation):
    """
    A `RelayMutation` a project can subclass to accept more input, then register under the
    same field name.

    Graphene replaces a mutation's `Input` with a generated input type, and a subclass of
    that cannot be built. The input as declared stays available as `BaseInput`, so a
    project extends it from there::

        class ProjectSendInvitation(ProfileSendInvitation):
            class Input(ProfileSendInvitation.BaseInput):
                title = graphene.String()

            class Meta:
                keep_type_names = True

            @classmethod
            def extra_fields_from_input(cls, info, input) -> dict:
                return {"title": input.get("title") or ""}

    A subclass that declares no `Input` inherits `BaseInput` as is.

    A subclass gets graphene's usual type names, from its own class name
    (`ProjectSendInvitationInput`, `ProjectSendInvitationPayload`). `Meta.keep_type_names`
    gives it the names of the mutation it extends instead, so it can replace that mutation
    without changing what clients send: register one or the other, never both, since
    graphene keeps only the first type of a name.
    """

    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(
        cls, name: str | None = None, keep_type_names: bool = False, **options
    ) -> None:
        declared = cls.__dict__.get("Input", getattr(cls, "BaseInput", None))
        if declared is not None:
            cls.BaseInput = declared
            cls.Input = declared
        if keep_type_names and name is None:
            # Take the type names of the mutation being extended.
            parent = next(
                (base for base in cls.__mro__[1:] if base.__dict__.get("_meta") is not None),
                None,
            )
            if parent is not None and issubclass(parent, ExtensibleMutation):
                name = parent._meta.name
        super().__init_subclass_with_meta__(name=name, **options)

    @classmethod
    def extra_fields_from_input(cls, info: graphene.ResolveInfo, input: dict) -> dict[str, Any]:
        """
        Values for the project's own `ProfileUserRole` columns, read from the extra input a
        subclass declares (field name -> value). None by default.
        """
        return {}
