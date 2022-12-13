# Django Backend

## Requirements

* Python 3.9.7

## Getting Started

1. Review and follow the README in the sibling ansible repo.
2. Read the contributing guidelines found in CONTRIBUTING.md

## Django Code

### Code Style

* Activate pre-commit hook to automatically format and lint staged python code upon every commit:

        $ pre-commit install        

* Use flake8 (found in requirements/dev.txt) to lint code.
* Use isort (found in requirements/dev.txt) to automatically sort your imports before commiting. (`isort **/*.py`)
* Use black (found in requirements/dev.txt) to automatically format your code before comitting. (`black .`)
* SonarQube: `cp sonar-project.properties.example sonar-project.properties`

### Tests

Tests are written and run using [pytest](http://doc.pytest.org/en/latest/).  All tests can be found
under the `tests` directory at the root of the repository.

With the exception of changes to the Django Admin, all code must be accompanied by tests.

#### Definitions

* Unit test - Any test that can be performed without touching the database or any network resources.
* Integration test - Any test that does require the use of the database or a network resource.
* Functional test - Currently not in use.

#### Test Running Primer

For the full details on all of the available options when running tests refer to the pytest documentation.

Run all the tests

```
py.test
```

Run all the tests in a specific file.

```
py.test tests/path/to/file.py
```

Run tests whose class name and/or function name match a string

```
py.test -k some_string
```

Reuse the database structure between tests (speeds things up)

```
py.test --reuse-db
```

## API Documentation

**All changes to the Django API should be reflected in the API documentation automatically**

The API documentation is built using [drf-yasg](https://drf-yasg.readthedocs.io/en/stable/index.html) and can be found at `/docs` or path mentioned in **SWAGGER_DOC_PATH** in `settings/base.py`

To override the default doc generated, can do:
```python
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
```
and add swagger_auto_schema with the endpoints in viewsets like:
```python

@swagger_auto_schema(
    operation_description="operation description",
    operation_summary="operation summary or name",
    manual_parameters=[ # list of openapi.Parameter objects
        openapi.Parameter(
            "name of param",
            openapi.IN_QUERY, # options are [IN_BODY, IN_PATH, IN_QUERY, IN_FORM, IN_HEADER]
            description="description",
            type=openapi.TYPE_BOOLEAN, # options are [TYPE_OBJECT, TYPE_STRING, TYPE_NUMBER, 
                                       # TYPE_INTEGER, TYPE_BOOLEAN, TYPE_ARRAY, TYPE_FILE]
        )
    ],
    responses={
            200: openapi.Response("response description", SomeSerializer), # SomeSerializer is optional
            404: openapi.Response("response description"),
        },
)
def something(self, request, *args, **kwargs):
    ...
```

## TSL Pluggable Django applications

TSL develops a set of external Python packages that can be plugged into BasApp through Django application registry.

* [payments](https://bitbucket.org/silverlogic/baseapp-payments-django/src/master/) - integration of Stripe with BaseApp and dj-stripe
* [django-trench](https://github.com/silverlogic/django-trench/) - a set of REST API endpoints to supplement `django-rest-framework` with multi-factor authentication (MFA, 2FA).


## UML Generation

Examples

```
./manage.py generate_uml
./manage.py generate_uml --library pydot --format pdf
./manage.py generate_uml --library pydot --apps users --format svg
./manage.py generate_uml --library pydot --apps users --models User --format png
./manage.py generate_uml --library pydot --apps users --models User UserReferral --format dot
```

To see available options run

```
./manage.py generate_uml --help
```

Recommend using [GraphvizOnline](https://dreampuf.github.io/GraphvizOnline) with output of .dot file for editing

## Generate routes info

Run one of these commands.

```
./manage.py routes_info
./manage.py routes_info -npc
./manage.py routes_info --no-permission-classes
```

It should list all actions of each viewset (or only the empty ones if you add `--no-permission-classes`)

## Local SonarQube Setup

You'll need SonarQube and `sonar-scanner`
* [SonarQube Docker instructions](https://www.sonarqube.org/features/deployment/) - free version is fine
* Once you have SonarQube running, create a project for local analysis and take note of the project key and project token.
* Follow the instructions in SonarQube to run `sonar-scanner`
