from io import BytesIO

from django.core.files.images import ImageFile

import requests
from avatar.models import Avatar


class EmailAlreadyExistsError(Exception):
    pass


class EmailNotProvidedError(Exception):
    pass


def get_username(strategy, details, user=None, *args, **kwargs):
    storage = strategy.storage

    if not user:
        if details.get('email'):
            username = details['email']
        elif strategy.request.data.get('email'):
            username = strategy.request.data['email']
        else:
            raise EmailNotProvidedError()

        if storage.user.user_exists(username=username):
            raise EmailAlreadyExistsError()
    else:
        username = storage.user.get_username(user)
    return {'username': username}


def set_avatar(is_new, backend, user, response, *args, **kwargs):
    if not is_new:
        return

    image_url = None

    if backend.name == 'facebook':
        picture_url = 'https://graph.facebook.com/v2.7/me/picture'
        picture_params = {'type': 'large', 'access_token': response['access_token']}
        response = requests.get(picture_url, params=picture_params)
        data = response.json()
        image_url = data['data']['url']
    elif backend.name == 'twitter':
        image_url = response.get('profile_image_url', None)

    if image_url:
        response = requests.get(image_url)
        image = BytesIO(response.content)
        Avatar.objects.create(user=user, primary=True, avatar=ImageFile(image, name='pic.jpg'))
