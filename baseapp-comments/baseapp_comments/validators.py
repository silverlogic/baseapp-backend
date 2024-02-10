from constance import config
from django.core.exceptions import ValidationError


def blocked_words_validator(value):
    try:
        blocked_list = config.BLOCKLISTED_WORDS
    except AttributeError:
        blocked_list = ""

    blocked_words = [word.strip().lower() for word in blocked_list.split(",") if word.strip()]
    blocked_words_set = set(blocked_words)
    lower_value = value.lower()

    for word in blocked_words_set:
        if word in lower_value:
            raise ValidationError(
                "Please be advised that the use of inappropriate language is not permitted."
            )
