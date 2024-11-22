# BaseApp Wagtail - Django

Use this package to load the Wagtail CMS initial Setup. You can also follow its internal code as a reference of how to implement features inside of the Wagtail CMS

[Wagtail documentation](https://docs.wagtail.org/en/stable/)

## Installation

### Install the package

Install in your environment:

```bash
pip install baseapp-wagtail
```



## Usage

### Package Setup

The following steps are already applied in the [baseapp-backend-template](https://bitbucket.org/silverlogic/baseapp-backend-template). If you want to remove the Wagtail package settings from your project, please follow this guide: [Remove the Wagtail package from your project](#remove-the-wagtail-package-from-your-project).

#### Import and configure the package settings

Because Wagtail requires a series of settings to work, the package defines the necessary ones. To import and configure these settings, follow the steps below in your project settings file (settings.py or settings/base.py):

1. Import the package settings.
    ```python
    # ...
    from baseapp_wagtail.settings import *  # noqa
    ```

2. The `INSTALLED_APPS` and `MIDDLEWARE` entries required for Wagtail to work properly are not configured automatically by the import above. You need to import and add them manually to `INSTALLED_APPS` and `MIDDLEWARE`.

    - Import the settings that need manual configuration:
    ```python
    from baseapp_wagtail.settings import (
        WAGTAIL_INSTALLED_APPS,
        WAGTAIL_INSTALLED_INTERNAL_APPS,
        WAGTAIL_MIDDLEWARE,
    )
    ```

    - Append the `INSTALLED_APPS` settings to the `INSTALLED_APPS` variable:
    ```python
    INSTALLED_APPS = [
        # ...
    ]

    # Wagtail INSTALLED_APPS
    INSTALLED_APPS += [
        # baseapp_wagtail
        "testproject.base",
        *WAGTAIL_INSTALLED_INTERNAL_APPS,
        *WAGTAIL_INSTALLED_APPS,
    ]
    ```

    - Append the `WAGTAIL_MIDDLEWARE` setting to the `MIDDLEWARE` variable:
    ```python
    MIDDLEWARE = [
        # ...
    ]

    # Wagtail MIDDLEWARE
    MIDDLEWARE += WAGTAIL_MIDDLEWARE
    ```

3. Add the `WAGTAIL_SITE_NAME` variable to the settings:
    ```python
    WAGTAIL_SITE_NAME = "Baseapp CMS"
    ```

4. Ensure you have the following environment variables (ENV vars) registered. For more details, see [baseapp_wagtail/settings.py](./baseapp_wagtail/settings.py):
    - `URL`
    - `WAGTAIL_FRONT_URL_PATH`
    - `WAGTAIL_FRONT_PAGE_PREVIEW_URL_PATH`

#### Register the Wagtail URLs

Inside the `urls.py` of your project, register the Wagtail URLs as follows:
```python
import baseapp_wagtail.urls as baseapp_wagtail_urls

# ...
urlpatterns = [
    # ...
    re_path(r"", include(baseapp_wagtail_urls)),
]
```

#### Register the Page Model

Wagtail doesn’t add any page models by default, and the package doesn’t either. This is because once a page model is registered, it cannot be unregistered. However, the package provides an abstract page model that’s ready to use; you just need to extend it in the `models.py` file of any app in your project. Here’s an example:

```python
from baseapp_wagtail.models import BaseStandardPage


class StandardPage(BaseStandardPage):
    pass
```

After that, create the migrations and migrate it.


### Customize Wagtail

This package has two main purposes:

1. Provide a plug-and-play Wagtail instance with helpful and valuable custom features.
2. Create a framework for working with Wagtail.

This section covers the second purpose: a framework to extend and scale Wagtail.

#### Architecture to Extend Wagtail Features in the Baseapp Templates

The package defines an internal architecture that should ideally be followed by final projects when adding new custom features. This makes customizations portable, allowing valuable features to be easily transferred to the package, enabling its evolution with minimal effort.

The architecture is straightforward and follows these main folders:

```
api/
base/
├── blocks/
│   ├── basic_blocks/
│   └── custom_blocks/
├── stream_fields/
medias/
```

- **api/**: Contains headless API endpoints.
- **base/**: Stores all page customizations, including available blocks and stream fields.
- **medias/**: Stores custom images or document configurations.  

Everything else follows the standard Wagtail or Django architecture.

#### Customizing Blocks

The main customizations in Wagtail will be within the block list. Everything in headless Wagtail is block-oriented, so any custom content within pages is likely handled through blocks.

Follow the pattern of existing blocks to create new ones. Here’s a quick guide on where and how to create them:

1. Determine if it’s a basic or a custom block. Basic blocks are extensions of Wagtail blocks (e.g., `RichTextBlock`). Custom blocks are entirely new blocks.
2. In the `base/blocks/basic_blocks/` or `base/blocks/custom_blocks/` folder, create a folder for your block, naming it in snake_case.
3. Inside this folder, create an `__init__.py` file that imports the block from a `block.py` file.
4. Define the block within `block.py`.
5. Create a `tests/` folder inside this block folder and add unit tests for the block there. Follow the patterns of other blocks to test your new one (any new block has to be added in the `PageForTests` model inside of `tests/model.py` in the root of the project).
6. After creating the block, add its import within `base/blocks/__init__.py`.
7. Add your block inside the desired `base/stream_field/` class. Each page type can use multiple stream fields.

In general, always refer to the package as a guide for customizing Wagtail.

#### Adding New API Endpoints

To add new API endpoints, review the file `baseapp-wagtail/baseapp_wagtail/api/router.py`. You'll need to import it into your project and add the new endpoints.

Afterward, override the `path("api/v2/", api_router.urls)` entry in your project’s `urls.py` with the updated router. Simply import the modified `api_router` in `urls.py` and add the path `path("api/v2/", api_router.urls)` after where you registered the Wagtail URLs ([Register the Wagtail URLs](#register-the-wagtail-urls)).


## Uninstallation

### Remove the Wagtail Package from Your Project

To remove the Wagtail package from your project (ideally using the baseapp-frontend-template as a boilerplate), follow these steps:

1. Remove the page model and Wagtail app.
    * Revert the page model migration (assuming the page model is under the `wagtail/base` app).
        ```shell
        ./manage.py migrate base zero
        ```
    * Delete the `wagtail/` folder (`rm -rf wagtail/`).

2. Revert the Wagtail package migrations.
    ```shell
    ./manage.py wagtail_revert_package_migrations
    ```
    This command might be unstable, as it requires updates when new features are added to the package. If the script crashes or if Wagtail tables still exist in the database, proceed to the next steps, then drop and recreate the database schema to prevent the Wagtail migrations from being applied.

3. Remove the URLs added in `urls.py` ([Register the Wagtail URLs](#register-the-wagtail-urls)).

4. Remove all Wagtail references added in `base.py` (or `settings.py`) of your project ([Import and configure the package settings](#import-and-configure-the-package-settings)).



## Testing

Install the requirements from `test/requirements.txt` and run `pytest`.

### Adding New Tests

Each app has its own `tests/` folder, and the blocks also have their own `tests/` folder. Be sure to add your new tests in the appropriate location.

### The Root `tests/` Folder

The package also includes a `tests/` folder at the root level. This folder stores general fixtures, helpers, and test mixins that are particularly useful when testing Wagtail features. Please review its contents before adding new tests.

This folder also has an unusual setup, containing its own `migrations/` folder and a `models.py` file. Testing Wagtail requires page models that map blocks, so for this package, the root `tests/` folder functions as an app loaded only when running `pytest`. If you modify any existing block or add a new one, you'll need to update the models in `tests/models.py` and regenerate its migrations.

#### Regenerating Migrations for `tests/models.py`

This app doesn’t require migration history; it only needs to regenerate migration 0001 whenever changes are made to models or blocks within these models. Follow these steps to regenerate it:

1. Ensure the package’s Docker instance is running.
2. Confirm you’re outside the Docker container and in the package folder (`baseapp-wagtail/`).
3. Run the command `./setup_test_migrations.sh`.

That’s all. If it fails, check the `.sh` file for details and try reproducing its steps in your terminal.
