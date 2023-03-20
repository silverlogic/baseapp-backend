from django.utils.translation import ugettext_lazy as _

import graphene


class Error(graphene.ObjectType):
    code = graphene.String()
    location = graphene.String()
    message = graphene.String(required=True)


def Errors():
    return graphene.List(Error)


def LoginRequiredError():
    return Error(
        code="login_required",
        message=_("You should be logged in to perform this action"),
    )
