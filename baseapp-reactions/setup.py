from setuptools import setup

setup(
    name="baseapp-reactions",  # How you named your package folder (MyLib)
    packages=["baseapp-reactions"],  # Chose the same as "name"
    version="0.7",  # Start with a small number and increase it with every change you make

    install_requires=[  # I get to this in a second
        "validators",
        "beautifulsoup4",
    ],
)
