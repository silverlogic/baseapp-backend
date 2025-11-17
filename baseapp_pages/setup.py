from setuptools import find_packages, setup

setup(
    name="baseapp_pages",
    version="1.0",
    packages=find_packages(),
    entry_points={
        "baseapp.plugins": [
            "baseapp_pages = baseapp_pages.plugin:PagesPlugin",
        ],
        "baseapp.interfaces": [
            "pages = baseapp_pages.graphql.interfaces:get_pages_interface",
        ],
    },
    zip_safe=False,
)
