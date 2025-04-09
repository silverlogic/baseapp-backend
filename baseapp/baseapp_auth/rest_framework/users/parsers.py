from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser


class SafeJSONParser(JSONParser):
    """
    Safely parse json by returning an empty dictionary in the event of a ParseError
    """

    def parse(self, *args, **kwargs):
        try:
            return super().parse(*args, **kwargs)
        except ParseError:
            return {}
