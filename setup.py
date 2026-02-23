#!/usr/bin/env python3
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="inbox-py",
    version="1.0.0",
    author="moosermail",
    description="Terminal email client for Resend inbound mail",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/moosermail/moosermail",
    py_modules=["inbox"],
    python_requires=">=3.7",
    entry_points={
        "console_scripts": [
            "inbox=inbox:main",
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
