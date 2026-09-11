from baseapp_core.tests.factories import UserFactory


def load() -> None:
    UserFactory.create_batch(size=5)
