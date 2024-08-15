import re
from io import BytesIO

import requests
from django.core.files.images import ImageFile


class EmailAlreadyExistsError(Exception):
    pass


class EmailNotProvidedError(Exception):
    pass


def get_username(strategy, details, response, user=None, *args, **kwargs):
    storage = strategy.storage

    if not user:
        if details.get("email"):
            username = details["email"]
        elif strategy.request.data.get("email"):
            username = strategy.request.data["email"]
        else:
            raise EmailNotProvidedError()

        if storage.user.user_exists(username=username):
            raise EmailAlreadyExistsError()
    else:
        username = storage.user.get_username(user)
    return {"username": username}


def set_avatar(is_new, backend, user, response, *args, **kwargs):
    if not is_new:
        return

    image_url = None
    image_params = {}

    if backend.name == "facebook":
        image_url = "https://graph.facebook.com/v12.0/me/picture"
        image_params = {
            "type": "large",
            "access_token": response["access_token"],
        }
    elif backend.name == "twitter":
        image_url = response.get("profile_image_url", None)
        if image_url:
            if re.search(r"default_profile_images", image_url):
                # don't want those silly default egg images.
                image_url = None
            else:
                # get a larger image the the default response one.
                image_url = re.sub(
                    r"_bigger\.(?P<extension>\w+)$",
                    r"_400x400.\g<extension>",
                    image_url,
                )
    elif backend.name.startswith("linkedin"):
        pictures = response.get("pictureUrls", None)
        if pictures:
            image_url = pictures["values"][0]

    if image_url:
        response = requests.get(image_url, params=image_params)
        image = BytesIO(response.content)

        user.profile.image = ImageFile(image, name="pic.jpg")
        user.profile.save()


def set_is_new(is_new, user, *args, **kwargs):
    user.is_new = is_new
