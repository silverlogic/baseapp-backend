import pytest
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType


@pytest.fixture
def permission_factory(db):
    def create(model, codename, name):
        ct = ContentType.objects.get_for_model(model)
        return Permission.objects.create(
            content_type=ct,
            codename=codename,
            name=name,
        )

    return create
