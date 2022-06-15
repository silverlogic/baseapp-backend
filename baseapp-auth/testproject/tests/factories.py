import factory


class UserFactory(factory.DjangoModelFactory):
    email = factory.Faker("email")
    password = factory.PostGenerationMethodCall("set_password", "default")

    class Meta:
        model = "users.User"

    @factory.post_generation
    def permission_groups(self, create, extracted, **kwargs):
        if create and extracted:
            self.permission_groups.add(*extracted)


class PasswordValidationFactory(factory.DjangoModelFactory):
    name = "apps.users.password_validators.MustContainSpecialCharacterValidator"

    class Meta:
        model = "users.PasswordValidation"


class TokenFactory(factory.DjangoModelFactory):
    user = factory.SubFactory(UserFactory)

    class Meta:
        model = "authtoken.Token"


class PermissionFactory(factory.DjangoModelFactory):
    name = factory.Faker("bs")

    class Meta:
        model = "permissions.Permission"


class PermissionGroupFactory(factory.DjangoModelFactory):
    name = factory.Faker("company")

    class Meta:
        model = "permissions.PermissionGroup"

    @factory.post_generation
    def permissions(self, create, extracted, **kwargs):
        if create and extracted:
            self.permissions.add(*extracted)


class RoleFactory(factory.DjangoModelFactory):
    name = factory.Faker("job")

    class Meta:
        model = "permissions.Role"

    @factory.post_generation
    def permissions(self, create, extracted, **kwargs):
        if create and extracted:
            self.permissions.add(*extracted)

    @factory.post_generation
    def permission_groups(self, create, extracted, **kwargs):
        if create and extracted:
            self.permission_groups.add(*extracted)

    @factory.post_generation
    def exclude_permissions(self, create, extracted, **kwargs):
        if create and extracted:
            self.exclude_permissions.add(*extracted)
