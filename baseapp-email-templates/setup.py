from setuptools import setup

VERSION = "1.3"


with open("README.md", "r") as f:
    long_description = f.read()


setup(
    name="baseapp-email-templates",
    description="baseapp-email-templates is now baseapp-message-templates",
    long_description=long_description,
    long_description_content_type="text/markdown",
    version=VERSION,
    install_requires=["baseapp-message-templates"],
    classifiers=["Development Status :: 7 - Inactive"],
)
