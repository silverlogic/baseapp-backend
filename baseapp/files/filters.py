import django_filters
import swapper

File = swapper.load_model("baseapp_files", "File")


class FileFilter(django_filters.FilterSet):
    no_parent = django_filters.BooleanFilter(field_name="parent", lookup_expr="isnull")

    class Meta:
        model = File
        fields = ["no_parent"]
