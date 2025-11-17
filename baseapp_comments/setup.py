from setuptools import find_packages, setup

setup(
    name="baseapp_comments",
    version="1.0",
    packages=find_packages(),
    entry_points={
        "baseapp.plugins": [
            "baseapp_comments = baseapp_comments.plugin:CommentsPlugin",
        ],
        "baseapp.hooks": [
            "document_created.comments = baseapp_comments.hooks:handle_document_created",
        ],
        "baseapp.services": [
            "comments_count = baseapp_comments.services:CommentsCountService",
        ],
        "baseapp.interfaces": [
            "comments = baseapp_comments.graphql.interfaces:get_comments_interface",
        ],
    },
    zip_safe=False,
)
