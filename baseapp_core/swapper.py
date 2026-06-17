from typing import TYPE_CHECKING, Type

import swapper
from django.db.models import Model

if TYPE_CHECKING:
    from django.apps.registry import Apps


def init_swapped_models(models: list[tuple[str, str]]) -> list[Type[Model]] | Type[Model]:
    """
    Initialize swapped models from a list of app_label and model_name tuples.
    This initilization was made to be used inside models.py files, when the app ready methods are not called yet.
    """
    swapped_models = []
    for app_label, model_name in models:
        swapped_models.append(
            swapper.load_model(app_label, model_name, required=True, require_ready=False)
        )
    if len(swapped_models) == 1:
        return swapped_models[0]
    return swapped_models


def get_apps_model(apps: "Apps", app_label: str, model: str) -> Type[Model]:
    """
    Useful specially during migrations when you want to get a model that might be swapped out.

    Since the app_label and model changes when you swap a model, you can't just use apps.get_model
    and when using swapper.load_model, it will fail on ForeignKey and other fields where the model
    class is checked if that instance is of correct model class.
    """
    swapped = swapper.is_swapped(app_label, model)
    if swapped:
        return apps.get_model(*swapper.split(swapped))
    return apps.get_model(app_label, model)
