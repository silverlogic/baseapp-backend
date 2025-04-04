import swapper
from django.contrib import admin

Block = swapper.load_model("baseapp_blocks", "Block")


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ("id", "actor", "target", "created")
    list_filter = ("created",)
    raw_id_fields = ("actor", "target", "user")
