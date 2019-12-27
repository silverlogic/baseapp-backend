# Django Backend

## Requirements

* Python 3.6

## Getting Started

1. Review and follow the README in the sibling ansible repo.
2. Read the contributing guidelines found in CONTRIBUTING.md

## Django Code

### Code Style

* Use flake8 (found in requirements/dev.txt) to lint code.
* Use isort (found in requirements/dev.txt) to automatically sort your imports before commiting. (`isort **/*.py`)
* Use black (found in requirements/dev.txt) to automatically format your code before comitting. (`black .`)

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

**All changes to the Django API must be reflected in the API documentation.**

The API documentation is built using [middleman](https://middlemanapp.com/) and is
located under the apidocs directory.  All documentation is written in
[asciidoctor](http://asciidoctor.org/) format.

See apidocs/README.md for more info.
