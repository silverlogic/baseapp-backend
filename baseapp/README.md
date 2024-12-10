# BaseApp

BaseApp is a Django project template that provides a set of tools and best practices for building web applications.

## Requirements:

Run `pip install baseapp-backend`
And make sure to add the frozen version to your `requirements/base.txt` file

If you want to develop, [install using this other guide](#how-to-develop).

## How to use

Then enable the desired apps in your Django project's `INSTALLED_APPS` setting:

```python
INSTALLED_APPS = [
    ...
    'baseapp.activity_log',
    ...
]
```

## Features

## How to develop

Clone the project inside your project's backend dir:

```
git clone git@github.com:silverlogic/baseapp-backend.git
```

And manually install the package:

```
pip install -e baseapp-backend/baseapp
```

The `-e` flag will make it like any change you make in the cloned repo files will effect into the project.
