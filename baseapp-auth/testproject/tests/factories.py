import factory


class UserFactory(factory.DjangoModelFactory):
    email = factory.Faker('email')
    password = factory.PostGenerationMethodCall('set_password', 'default')

    class Meta:
        model = 'users.User'
