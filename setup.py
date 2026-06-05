#!/usr/bin/env python3
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="moosermail",
    version="1.1.0",
    author="moosermail",
    author_email="cloud@creayodev.com",
    description="Terminal email client for Moosermail and Resend inbound mail",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://mooser.email",
    project_urls={
        "Repository": "https://github.com/moosermail/moosermail",
    },
    py_modules=["inbox"],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "mooser=inbox:main",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Environment :: Console",
        "Topic :: Communications :: Email",
    ],
)
