from collections import OrderedDict

from django.shortcuts import get_object_or_404
from graphene.types import InputField
from graphene.types.mutation import MutationOptions
from graphene.types.objecttype import yank_fields_from_attrs
from graphene.utils.str_converters import to_snake_case
from graphene_django.rest_framework.serializer_converter import convert_serializer_field
from graphene_django.types import ErrorType
from rest_framework import serializers
from rest_framework.exceptions import ErrorDetail

from .mutations import RelayMutation


class SerializerMutationOptions(MutationOptions):
    lookup_field = None
    model_class = None
    model_operations = ["create", "update"]
    serializer_class = None


def fields_for_serializer(
    input_class,
    serializer,
    only_fields,
    exclude_fields,
    is_input=False,
    convert_choices_to_enum=True,
    lookup_field=None,
):
    fields = OrderedDict()
    for name, field in serializer.fields.items():
        is_not_in_only = only_fields and name not in only_fields
        is_excluded = any(
            [
                name in exclude_fields,
                field.write_only and not is_input,  # don't show write_only fields in Query
                field.read_only
                and is_input
                and lookup_field != name,  # don't show read_only fields in Input
            ]
        )
        is_field_in_input_class = input_class and hasattr(input_class, name)

        if is_not_in_only or is_excluded or is_field_in_input_class:
            continue

        fields[name] = convert_serializer_field(
            field, is_input=is_input, convert_choices_to_enum=convert_choices_to_enum
        )
    return fields


class SerializerMutation(RelayMutation):
    class Meta:
        abstract = True

    @classmethod
    def __init_subclass_with_meta__(
        cls,
        lookup_field=None,
        serializer_class=None,
        model_class=None,
        model_operations=("create", "update"),
        only_fields=(),
        exclude_fields=(),
        convert_choices_to_enum=True,
        _meta=None,
        **options,
    ):
        if not serializer_class:
            raise Exception("serializer_class is required for the SerializerMutation")

        if "update" not in model_operations and "create" not in model_operations:
            raise Exception('model_operations must contain "create" and/or "update"')

        serializer = serializer_class()
        if model_class is None:
            serializer_meta = getattr(serializer_class, "Meta", None)
            if serializer_meta:
                model_class = getattr(serializer_meta, "model", None)

        if lookup_field is None and model_class:
            lookup_field = model_class._meta.pk.name

        input_class = getattr(cls, "Input", None)

        input_fields = fields_for_serializer(
            input_class,
            serializer,
            only_fields,
            exclude_fields,
            is_input=True,
            convert_choices_to_enum=convert_choices_to_enum,
            lookup_field=lookup_field,
        )

        if not _meta:
            _meta = SerializerMutationOptions(cls)
        _meta.lookup_field = lookup_field
        _meta.model_operations = model_operations
        _meta.serializer_class = serializer_class
        _meta.model_class = model_class
        # _meta.fields = yank_fields_from_attrs(output_fields, _as=Field)

        input_fields = yank_fields_from_attrs(input_fields, _as=InputField)
        super().__init_subclass_with_meta__(_meta=_meta, input_fields=input_fields, **options)

    @classmethod
    def get_serializer_kwargs(cls, root, info, **input):
        lookup_field = cls._meta.lookup_field
        model_class = cls._meta.model_class

        for file_field_name, file_field_values in info.context.FILES.lists():
            if len(file_field_values) == 1:
                input[to_snake_case(file_field_name)] = file_field_values[0]
            else:
                input[to_snake_case(file_field_name)] = file_field_values

        if model_class:
            if "update" in cls._meta.model_operations and lookup_field in input:
                instance = get_object_or_404(model_class, **{lookup_field: input[lookup_field]})
                partial = True
            elif "create" in cls._meta.model_operations:
                instance = None
                partial = False
            else:
                raise Exception(
                    'Invalid update operation. Input parameter "{}" required.'.format(lookup_field)
                )

            return {
                "instance": instance,
                "data": input,
                "context": {"request": info.context},
                "partial": partial,
            }

        return {"data": input, "context": {"request": info.context}}

    @classmethod
    def mutate_and_get_payload(cls, root, info, **input):
        kwargs = cls.get_serializer_kwargs(root, info, **input)
        serializer = cls._meta.serializer_class(**kwargs)

        if serializer.is_valid():
            return cls.perform_mutate(serializer, info)
        else:
            errors = {}
            for field_name, messages in serializer.errors.items():
                index = 0
                for message in messages:
                    if isinstance(message, ErrorDetail):
                        if field_name not in errors:
                            errors[field_name] = []
                        errors[field_name].append(message)
                    else:
                        for field, msg in message.items():
                            name = f"{field_name}.{index}.{field}"
                            if name not in errors:
                                errors[name] = []
                            errors[name].append(msg[0].title())
                        index += 1
            errors = ErrorType.from_errors(errors)

            return cls(errors=errors)

    @classmethod
    def perform_mutate(cls, serializer, info):
        obj = serializer.save()

        kwargs = {}
        for f, field in serializer.fields.items():
            if not field.write_only:
                if isinstance(field, serializers.SerializerMethodField):
                    kwargs[f] = field.to_representation(obj)
                else:
                    kwargs[f] = field.get_attribute(obj)

        return cls(errors=None, **kwargs)
