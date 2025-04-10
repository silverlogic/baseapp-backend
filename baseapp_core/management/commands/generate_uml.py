import json
import re

from django.apps import apps as django_apps
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command, get_commands, load_command_class
from django.core.management.base import BaseCommand
from django.utils import timezone

# TODO: Add these options
# [--disable-fields] [--disable-abstract-fields]
# [--group-models] [--all-applications]
# [--theme THEME] [--verbose-names]
# [--language LANGUAGE]
# [--exclude-columns EXCLUDE_COLUMNS]
# [--exclude-models EXCLUDE_MODELS]
# [--include-models INCLUDE_MODELS]
# [--inheritance] [--no-inheritance]
# [--hide-relations-from-fields]
# [--disable-sort-fields] [--hide-edge-labels]
# [--arrow-shape {box,crow,curve,icurve,diamond,dot,inv,none,normal,tee,vee}]


class Command(BaseCommand):
    help = "Generate UML"

    available_libraries = ["pydot", "pygraphviz", "dot", "json"]
    available_apps = []
    available_models = []
    available_file_formats = [
        "bmp",
        "canon",
        "cmap",
        "cmapx",
        "cmapx_np",
        "dot",
        "dia",
        "emf",
        "em",
        "fplus",
        "eps",
        "fig",
        "gd",
        "gd2",
        "gif",
        "gv",
        "imap",
        "imap_np",
        "ismap",
        "jpe",
        "jpeg",
        "jpg",
        "metafile",
        "pdf",
        "pic",
        "plain",
        "plain-ext",
        "png",
        "pov",
        "ps",
        "ps2",
        "svg",
        "svgz",
        "tif",
        "tiff",
        "tk",
        "vml",
        "vmlz",
        "vrml",
        "wbmp",
        "xdot",
    ]

    def __init__(self, *args, **kwargs):
        super(Command, self).__init__(*args, **kwargs)

        for app_config in django_apps.get_app_configs():
            if re.match(r"^(apps).(.+)$", app_config.name) is None:
                continue
            if len(app_config.models) <= 0:
                continue
            app_label = re.sub(r"^(apps).(.+)$", r"\2", app_config.name)
            self.available_apps.append(app_label)
            for ct in ContentType.objects.filter(app_label=app_label):
                Model = ct.model_class()
                if Model is not None:
                    self.available_models.append(ct.model_class().__name__)

    def add_arguments(self, parser):
        parser.add_argument(
            "--library",
            type=str,
            default=self.available_libraries[0],
            help=f"""
            Library used to generate UML.
            default: {self.available_libraries[0]}
            options: {json.dumps(self.available_libraries)}
            """,
        )
        parser.add_argument(
            "--apps",
            nargs="+",
            type=str,
            default=self.available_apps,
            help=f"""
            Apps to include in UML.
            default: all
            options: {json.dumps(self.available_apps)}
            """,
        )
        parser.add_argument(
            "--models",
            nargs="+",
            type=str,
            default=self.available_models,
            help=f"""
            Model to include in UML.
            default: all
            options: {json.dumps(self.available_models)}
            """,
        )
        parser.add_argument(
            "--format",
            type=str,
            dest="output_format",
            default="dot",
            help=f"""
            Output file format.
            default: dot
            options: {json.dumps(self.available_file_formats)}
            """,
        )

    def handle(self, library, apps, models, output_format, **options):
        try:
            self._handle(library, apps, models, output_format, **options)
        except BaseException as e:
            self.stdout.write("\r\n")
            if isinstance(e, KeyboardInterrupt):
                return
            raise e

    def _handle(self, library, apps, models, output_format, **options):
        command_name = "graph_models"
        command_app = get_commands()[command_name]
        command_class = load_command_class(command_app, command_name)
        file_name = "uml-{date}.{ext}".format(
            date=timezone.now().strftime("%Y-%m-%d_%H-%M-%S"),
            ext=output_format,
        )

        call_command(
            command_class,
            f"--{library}",
            *[x for x in apps],
            "--include-models",
            ",".join([x for x in models]),
            "--arrow-shape=normal",
            "-g",
            "-o",
            file_name,
            stdout=self.stdout,
        )

        self.stdout.write(f"Generated {file_name}", self.style.SUCCESS)
