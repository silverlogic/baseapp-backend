import swapper
from django.contrib.auth.backends import BaseBackend

Page = swapper.load_model("baseapp_pages", "Page")


class PagesPermissionsBackend(BaseBackend):
    def has_perm(self, user_obj, perm, obj=None):
        if perm == "baseapp_pages.view_page":
            if not obj:
                # Anyone can view a page
                return True
            elif isinstance(obj, Page):
                if obj.status == Page.PageStatus.PUBLISHED:
                    return True
                else:
                    # Only users who has change permission can view unpublished pages
                    return user_obj.has_perm("baseapp_pages.change_page", obj)

        if perm in ["baseapp_pages.change_page", "baseapp_pages.delete_page"]:
            if user_obj.is_authenticated and isinstance(obj, Page):
                # Owner can change and delete their own pages
                if obj.user_id == user_obj.id:
                    return True

                # Anyone with permission can change and delete any page
                return user_obj.has_perm(perm)
