import factory


class LocaleFactory(factory.django.DjangoModelFactory):
    language_code = "en"

    class Meta:
        model = "wagtailcore.Locale"


class GroupFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("word")

    class Meta:
        model = "auth.Group"


class PageFactory(factory.django.DjangoModelFactory):
    title = factory.Faker("word")
    slug = factory.Faker("slug")
    depth = 1

    class Meta:
        model = "wagtailcore.Page"


class GroupApprovalTaskFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("word")

    class Meta:
        model = "wagtailcore.GroupApprovalTask"

    @factory.post_generation
    def groups(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            self.groups.set(extracted)
        else:
            self.groups.set([GroupFactory()])


class GroupPagePermissionFactory(factory.django.DjangoModelFactory):
    group = factory.SubFactory("tests.factories.GroupFactory")
    page = factory.SubFactory("tests.factories.PageFactory")
    permission_type = "publish"

    class Meta:
        model = "wagtailcore.GroupPagePermission"


class TaskFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("word")

    class Meta:
        model = "wagtailcore.Task"


class WorkflowFactory(factory.django.DjangoModelFactory):
    name = factory.Faker("word")

    class Meta:
        model = "wagtailcore.Workflow"


class WorkflowTaskFactory(factory.django.DjangoModelFactory):
    workflow = factory.SubFactory("tests.factories.WorkflowFactory")
    task = factory.SubFactory("tests.factories.TaskFactory")

    class Meta:
        model = "wagtailcore.WorkflowTask"


class WorkflowPageFactory(factory.django.DjangoModelFactory):
    workflow = factory.SubFactory("tests.factories.WorkflowFactory")
    page = factory.SubFactory("tests.factories.PageFactory")

    class Meta:
        model = "wagtailcore.WorkflowPage"


class WorkflowContentTypeFactory(factory.django.DjangoModelFactory):
    workflow = factory.SubFactory("tests.factories.WorkflowFactory")
    content_type = factory.SubFactory("tests.factories.ContentTypeFactory")

    class Meta:
        model = "wagtailcore.WorkflowContentType"


class ContentTypeFactory(factory.django.DjangoModelFactory):
    app_label = "base"
    model = "standardpage"

    class Meta:
        model = "contenttypes.ContentType"
