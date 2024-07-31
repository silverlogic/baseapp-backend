import swapper


def get_apps_model(apps, app_label, model):
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
