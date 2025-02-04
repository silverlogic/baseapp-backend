# TODO Get the router from the settings or something like that
from apps.api.v1.router import router as v1_router
from django.core.management.base import BaseCommand

from baseapp_core.constants import DEFAULT_ACTIONS


class Command(BaseCommand):
    help = "List routes with extra information"

    def add_arguments(self, parser):
        parser.add_argument(
            "-npc",
            "--no-permission-classes",
            action="store_true",
            help="List only routes without permission_classes",
        )

    def get_actions(self, viewset, debug):
        actions = []
        has_empty_permission_classes = False
        default_permissions = [permission.__class__ for permission in viewset().get_permissions()]

        for rest_action in DEFAULT_ACTIONS:
            if hasattr(viewset, rest_action):
                actions.append([rest_action, default_permissions])
                if not default_permissions:
                    has_empty_permission_classes = True

        for action in viewset.get_extra_actions():
            permission_classes = action.kwargs.get("permission_classes", [])
            actions.append([action.url_name, permission_classes])
            if not permission_classes:
                has_empty_permission_classes = True

        return actions, has_empty_permission_classes

    def handle(self, *args, **kwargs):
        registry = v1_router.registry
        write_always = not kwargs["no_permission_classes"]
        paths = []

        self.stdout.write("Showing info about v1_router (apps.api.v1.router.router)")
        self.stdout.write("")

        for _, viewset, _ in registry:
            actions, has_empty_permission_classes = self.get_actions(viewset, False)

            if write_always or has_empty_permission_classes:
                self.stdout.write(f"Listing views for {viewset.__module__}.{viewset.__name__}")
                for action in actions:
                    if write_always or not (action[1]):
                        paths.append(str(action[1]))
                        self.stdout.write(f"{action[0]}: {action[1]}")
                self.stdout.write("")  # blank line separator
