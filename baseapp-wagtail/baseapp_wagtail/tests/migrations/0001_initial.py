# Generated by Django 5.1.1 on 2024-10-29 19:58

import django.db.models.deletion
from django.db import migrations, models

import baseapp_wagtail.base.models
import baseapp_wagtail.base.stream_fields.featured_image_stream_field
import baseapp_wagtail.base.stream_fields.page_body_stream_field
import wagtail.fields


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("wagtailcore", "0094_alter_page_locale"),
    ]

    operations = [
        migrations.CreateModel(
            name="PageForTests",
            fields=[
                (
                    "page_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="wagtailcore.page",
                    ),
                ),
                (
                    "featured_image",
                    baseapp_wagtail.base.stream_fields.featured_image_stream_field.FeaturedImageStreamField(
                        [("featured_image", 2)],
                        blank=True,
                        block_lookup={
                            0: (
                                "baseapp_wagtail.base.blocks.basic_blocks.custom_image_chooser_block.block.CustomImageChooserBlock",
                                (),
                                {"image_sizes": None, "required": False},
                            ),
                            1: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {
                                    "help_text": 'If this is a <a href="https://www.w3.org/WAI/tutorials/images/decorative/" target="_blank">decorative image</a>, please leave this field blank.',
                                    "required": False,
                                },
                            ),
                            2: (
                                "wagtail.blocks.StructBlock",
                                [[("image", 0), ("alt_text", 1)]],
                                {},
                            ),
                        },
                        null=True,
                        verbose_name="Featured Image",
                    ),
                ),
                (
                    "body",
                    wagtail.fields.StreamField(
                        [
                            ("custom_image_chooser_block", 0),
                            ("custom_image_block", 3),
                            ("custom_rich_text_block", 4),
                            ("banner_block", 10),
                        ],
                        blank=True,
                        block_lookup={
                            0: (
                                "baseapp_wagtail.base.blocks.basic_blocks.custom_image_chooser_block.block.CustomImageChooserBlock",
                                (),
                                {},
                            ),
                            1: (
                                "baseapp_wagtail.base.blocks.basic_blocks.custom_image_chooser_block.block.CustomImageChooserBlock",
                                (),
                                {"image_sizes": None, "required": False},
                            ),
                            2: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {
                                    "help_text": 'If this is a <a href="https://www.w3.org/WAI/tutorials/images/decorative/" target="_blank">decorative image</a>, please leave this field blank.',
                                    "required": False,
                                },
                            ),
                            3: (
                                "wagtail.blocks.StructBlock",
                                [[("image", 1), ("alt_text", 2)]],
                                {},
                            ),
                            4: (
                                "baseapp_wagtail.base.blocks.basic_blocks.custom_rich_text_block.block.CustomRichTextBlock",
                                (),
                                {},
                            ),
                            5: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {"max_length": 50, "required": True, "use_json_field": True},
                            ),
                            6: (
                                "baseapp_wagtail.base.blocks.basic_blocks.custom_rich_text_block.block.CustomRichTextBlock",
                                (),
                                {
                                    "features": ["bold", "italic", "link", "ul", "hr"],
                                    "icon": "pilcrow",
                                    "max_length": 255,
                                    "required": False,
                                },
                            ),
                            7: (
                                "wagtail.blocks.static_block.StaticBlock",
                                (),
                                {"admin_text": "<hr />", "label": " "},
                            ),
                            8: (
                                "baseapp_wagtail.base.blocks.basic_blocks.custom_image_chooser_block.block.CustomImageChooserBlock",
                                (),
                                {"label": " ", "required": False},
                            ),
                            9: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {
                                    "blank": True,
                                    "choices": [("left", "Left"), ("right", "Right")],
                                    "help_text": "This indicates the position of the image in the desktop view.",
                                    "label": "Image Position",
                                },
                            ),
                            10: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("title", 5),
                                        ("description", 6),
                                        ("hr", 7),
                                        ("featured_image", 8),
                                        ("image_position", 9),
                                    ]
                                ],
                                {},
                            ),
                        },
                        verbose_name="Page body",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=(baseapp_wagtail.base.models.HeadlessPageMixin, "wagtailcore.page"),
        ),
        migrations.CreateModel(
            name="StandardPage",
            fields=[
                (
                    "page_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="wagtailcore.page",
                    ),
                ),
                (
                    "featured_image",
                    baseapp_wagtail.base.stream_fields.featured_image_stream_field.FeaturedImageStreamField(
                        [("featured_image", 2)],
                        blank=True,
                        block_lookup={
                            0: (
                                "baseapp_wagtail.base.blocks.basic_blocks.custom_image_chooser_block.block.CustomImageChooserBlock",
                                (),
                                {"image_sizes": None, "required": False},
                            ),
                            1: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {
                                    "help_text": 'If this is a <a href="https://www.w3.org/WAI/tutorials/images/decorative/" target="_blank">decorative image</a>, please leave this field blank.',
                                    "required": False,
                                },
                            ),
                            2: (
                                "wagtail.blocks.StructBlock",
                                [[("image", 0), ("alt_text", 1)]],
                                {},
                            ),
                        },
                        null=True,
                        verbose_name="Featured Image",
                    ),
                ),
                (
                    "body",
                    baseapp_wagtail.base.stream_fields.page_body_stream_field.PageBodyStreamField(
                        [("section_stream_block", 7)],
                        blank=True,
                        block_lookup={
                            0: (
                                "baseapp_wagtail.base.blocks.basic_blocks.custom_rich_text_block.block.CustomRichTextBlock",
                                (),
                                {"icon": "pilcrow"},
                            ),
                            1: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {"max_length": 50, "required": True, "use_json_field": True},
                            ),
                            2: (
                                "baseapp_wagtail.base.blocks.basic_blocks.custom_rich_text_block.block.CustomRichTextBlock",
                                (),
                                {
                                    "features": ["bold", "italic", "link", "ul", "hr"],
                                    "icon": "pilcrow",
                                    "max_length": 255,
                                    "required": False,
                                },
                            ),
                            3: (
                                "wagtail.blocks.static_block.StaticBlock",
                                (),
                                {"admin_text": "<hr />", "label": " "},
                            ),
                            4: (
                                "baseapp_wagtail.base.blocks.basic_blocks.custom_image_chooser_block.block.CustomImageChooserBlock",
                                (),
                                {"label": " ", "required": False},
                            ),
                            5: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {
                                    "blank": True,
                                    "choices": [("left", "Left"), ("right", "Right")],
                                    "help_text": "This indicates the position of the image in the desktop view.",
                                    "label": "Image Position",
                                },
                            ),
                            6: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("title", 1),
                                        ("description", 2),
                                        ("hr", 3),
                                        ("featured_image", 4),
                                        ("image_position", 5),
                                    ]
                                ],
                                {},
                            ),
                            7: (
                                "wagtail.blocks.StreamBlock",
                                [[("rich_text_block", 0), ("banner_block", 6)]],
                                {"required": False},
                            ),
                        },
                        verbose_name="Page body",
                    ),
                ),
            ],
            options={
                "abstract": False,
                "default_related_name": "tests_standard_pages",
            },
            bases=(baseapp_wagtail.base.models.HeadlessPageMixin, "wagtailcore.page"),
        ),
    ]
