# BaseApp Reports

Reusable app to enable User's reports any model, customizable for project's needs.

## How to install:

Add dependencies to your `requirements/base.txt` file:

```
baseapp-core @ git+https://github.com/silverlogic/baseapp-backend.git@v0.1#subdirectory=baseapp-core
baseapp-reports @ git+https://github.com/silverlogic/baseapp-backend.git@v0.1#subdirectory=baseapp-reports
```

And run provision or manually `pip install -r requirements/base.ext`

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Add `baseapp_reports` to your project's `INSTALLED_APPS`

Now make sure all models you'd like to get reports also inherits `ReactableModel`, like:

```python
from baseapp_reports.models import ReactableModel

class Comment(models.Model, ReactableModel):
    body = models.Textfield()
```

Also make sure your GraphQL object types extends `ReportsInterface` interface:

```python
from baseapp_reports.graphql.object_types import ReportsInterface

class UserNode(DjangoObjectType):
    class Meta:
        interfaces = (relay.Node, ReportsInterface)
```

Expose `ReportsMutations` and `ReportsQuery` in your GraphQL/graphene endpoint, like:

```python
from baseapp_reports.graphql.mutations import ReportsMutations
from baseapp_reports.graphql.queries import ReportsQuery

class Query(graphene.ObjectType, ReportsQuery):
    pass

class Mutation(graphene.ObjectType, ReportsMutations):
    pass

schema = graphene.Schema(query=Query, mutation=Mutation)
```

This will expose `reportCreate` mutation and add fields and connections to all your GraphqlQL Object Types using interface `ReportsInterface`.

Example:

```graphql
{
    ...
}
```

## How to to customize the Report model

<!-- In some cases you may need to extend Report model, and we can do it following the next steps:

Start by creating a barebones django app:

```
mkdir my_project/reports
touch my_project/reports/__init__.py
touch my_project/reports/models.py
``` -->

Your `models.py` will look something like this:

```python
from django.db import models
from django.utils.translation import gettext_lazy as _

from baseapp_reports.models import AbstractBaseReport

class Report(AbstractBaseReport):
    custom_field = models.CharField(null=True)

    class ReportTypes(models.IntegerChoices):
        LIKE = 1, _("like")
        DISLIKE = -1, _("dislike")

        @property
        def description(self):
            return self.label
```

Now make your to add your new app to your `INSTALLED_APPS` and run `makemigrations` and `migrate` like any normal django app.

Now in your `settings/base.py` make sure to tell baseapp-reports what is your custom model for Report:

```python
BASEAPP_REPORTS_REPORT_MODEL = 'reports.Report'
```

## Writing test cases in your project

There is a `AbstractReportFactory` which helps you write other factories:

```
import factory
from baseapp_reports.tests.factories import AbstractReportFactory

class CommentFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = "comments.Comment"


class CommentReportFactory(AbstractReportFactory):
    target = factory.SubFactory(CommentFactory)

    class Meta:
        model = "baseapp_reports.Report"
        # OR if you have a custom model, point to it:
        model = "reports.Report"
```

In the above example we have a easy way to make reports to any comment into the database for testing proporses using `CommentReportFactory`.

## How to develop

Clone the project inside your project's backend dir:

```
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```
pip install -e baseapp-backend/baseapp-reports
```

The `-e` flag will make it like any change you make in the cloned repo files will effect into the project.