from setuptools import find_packages, setup

setup(
    name="baseapp_auth",
    version="1.0",
    packages=find_packages(),
    entry_points={
        "baseapp.plugins": [
            "baseapp_auth = baseapp_auth.plugin:AuthPlugin",
        ],
    },
    zip_safe=False,
)
