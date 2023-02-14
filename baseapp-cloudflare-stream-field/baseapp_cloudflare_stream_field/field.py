import json

from django.db.models import JSONField
from django.db.models.fields.json import KeyTransform
from django.db.models.query_utils import DeferredAttribute

from cloudflare_stream_field.stream import StreamClient
from cloudflare_stream_field.widgets import CloudflareStreamAdminWidget


class CloudflareStream(dict):
    def __init__(self, value, instance=None, field=None, **kwargs):
        self.instance = instance
        self.field = field
        if value:
            kwargs.update(value)
        super().__init__(**kwargs)

    def create(self, **kwargs):
        stream_client = StreamClient()
        result = stream_client.create_live_input(**kwargs)
        self.update(result)
        return self

    def __getattr__(self, name):
        try:
            return self[name]
        except (KeyError, TypeError):
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")


class CloudflareStreamDeferredAttribute(DeferredAttribute):
    def __get__(self, instance, cls=None):
        if instance is None:
            return self

        value = super().__get__(instance, cls)

        # If this value is a string (instance.file = "path/to/file") or None
        # then we simply wrap it with the appropriate attribute class according
        # to the file field. [This is FieldFile for FileFields and
        # ImageFieldFile for ImageFields; it's also conceivable that user
        # subclasses might also want to subclass the attribute class]. This
        # object understands how to convert a path to a file, and also how to
        # handle None.
        if isinstance(value, str) or value is None:
            try:
                data = json.loads(value)
            except (json.decoder.JSONDecodeError, TypeError):
                data = None
            attr = self.field.attr_class(data, instance=instance, field=self.field)
            instance.__dict__[self.field.attname] = attr
        elif isinstance(value, dict):
            attr = self.field.attr_class(value, instance=instance, field=self.field)
            instance.__dict__[self.field.attname] = attr

        elif isinstance(value, self.field.attr_class):
            instance.__dict__[self.field.attname] = value

        # Other types of files may be assigned as well, but they need to have
        # the FieldFile interface added to them. Thus, we wrap any other type of
        # File inside a FieldFile (well, the field's attr_class, which is
        # usually FieldFile).
        #  elif isinstance(file, File) and not isinstance(file, FieldFile):
        #      file_copy = self.field.attr_class(instance, self.field, file.name, None)
        #      file_copy.file = file
        #      file_copy._committed = False
        #      instance.__dict__[self.field.attname] = file_copy

        # Finally, because of the (some would say boneheaded) way pickle works,
        # the underlying FieldFile might not actually itself have an associated
        # file. So we need to reset the details of the FieldFile in those cases.
        #  elif isinstance(file, FieldFile) and not hasattr(file, "field"):
        #      file.instance = instance
        #      file.field = self.field
        #      file.storage = self.field.storage

        # Make sure that the instance is correct.
        #  elif isinstance(file, FieldFile) and instance is not file.instance:
        #      file.instance = instance

        # That was fun, wasn't it?
        return instance.__dict__[self.field.attname]

    def __set__(self, instance, value):
        instance.__dict__[self.field.attname] = value


class CloudflareStreamField(JSONField):
    attr_class = CloudflareStream
    descriptor_class = CloudflareStreamDeferredAttribute

    def from_db_value(self, value, expression, connection):
        if value is None:
            return value
        # Some backends (SQLite at least) extract non-string values in their
        # SQL datatypes.
        if isinstance(expression, KeyTransform) and not isinstance(value, str):
            return value
        try:
            return json.loads(value, cls=self.decoder)
        except json.JSONDecodeError:
            return value

    def get_prep_value(self, value):
        if value is None or isinstance(value, str):
            return value
        if not isinstance(value, str):
            value = json.dumps(value, cls=self.encoder)
        return super().get_prep_value(value)

    #  def save_form_data(self, instance, data):
    #      # Important: None means "no change", other false value means "clear"
    #      # This subtle distinction (rather than a more explicit marker) is
    #      # needed because we need to consume values that are also sane for a
    #      # regular (non Model-) Form to find in its cleaned_data dictionary.
    #      if data is not None:
    #          # This value will be converted to str and stored in the
    #          # database, so leaving False as-is is not acceptable.
    #          setattr(instance, self.name, data or "")

    def formfield(self, *args, **kwargs):
        #  if self.async_upload:
        kwargs.update(
            {
                #  "form_class": FormCloudflareStreamFileField,
                "max_length": self.max_length,
                "widget": CloudflareStreamAdminWidget,
            }
        )
        return super().formfield(*args, **kwargs)
