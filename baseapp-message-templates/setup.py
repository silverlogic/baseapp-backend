from setuptools import find_packages, setup

with open("README.md", "r") as f:
    long_description = f.read()

setup(
    name="baseapp-message-templates",
    packages=find_packages(),
    version="0.1",
    long_description=long_description,
    long_description_content_type="text/markdown",
)
