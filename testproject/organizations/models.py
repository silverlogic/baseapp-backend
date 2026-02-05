from baseapp_organizations.models import AbstractOrganization


class Organization(AbstractOrganization):

    class Meta(AbstractOrganization.Meta):
        pass

    def __str__(self):
        return self.name or ""
