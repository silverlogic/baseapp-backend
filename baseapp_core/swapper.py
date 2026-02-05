from typing import Type

import swapper
from django.db.models import Model


def init_swapped_models(models: list[tuple[str, str]]) -> list[Type[Model]]:
    """
    Initialize swapped models from a list of app_label and model_name tuples.
    This initilization was made to be used inside models.py files, when the app ready methods are not called yet.
    """
    swapped_models = []
    for app_label, model_name in models:
        swapped_models.append(
            swapper.load_model(app_label, model_name, required=True, require_ready=False)
        )
    return swapped_models
