import testproject.factories as f


def load():
    f.UserFactory.create_batch(size=10)
