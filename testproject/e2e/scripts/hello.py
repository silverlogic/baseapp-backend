from baseapp_core.tests.factories import UserFactory


def load():
    UserFactory.create_batch(size=5)
