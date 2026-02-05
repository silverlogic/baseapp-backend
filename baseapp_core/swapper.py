import swapper
from django.db.models import Model
from typing import Type


def init_swapped_models(models: list[tuple[str, str]]) -> list[Type[Model]]:
    swapped_models = []
    for app_label, model_name in models:
        swapped_models.append(
            swapper.load_model(app_label, model_name, required=True, require_ready=False)
        )
    return swapped_models
