import os
from setuptools import setup, find_packages
import pathlib


package_name = "gcardvault"
cli_name = package_name

dirname = os.path.dirname(__file__)
version_file_path = os.path.join(dirname, "src", "VERSION.txt")
readme_file_path = os.path.join(dirname, "README.md")


setup(
    name="gcardvault",
    version=pathlib.Path(version_file_path).read_text().strip(),
    description="Command-line utility which exports all of a user's Google Contacts in vCard/VCF format for backup (or portability)",
    keywords=["Google Contacts", "gmail", "contacts", "backup", "export", "vCard", "VCF", "CardDav"],
    url=f"http://github.com/rtomac/{package_name}",
    long_description=pathlib.Path(readme_file_path).read_text(),
    long_description_content_type="text/markdown",
    author="Ryan Tomac",
    author_email="rtomac@gmail.com",
    license="MIT",
    packages=[package_name],
    package_dir={package_name: "src"},
    package_data={package_name: ["*.txt"]},
    include_package_data=True,
    scripts=[f"bin/{cli_name}"],
    python_requires=">=3.6",
    install_requires=[
        "google-api-python-client==2.7.*",
        "google-auth-httplib2==0.1.*",
        "google-auth-oauthlib==0.4.*",
        "requests==2.25.*",
        "GitPython==3.1.*",
    ],
    extras_require={
        "dev": [
            "pycodestyle",
        ],
        "test": [
            "pytest==6.*",
            "Jinja2==3.*",
        ],
        "release": [
            "twine",
        ],
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Environment :: Console",
        "Intended Audience :: End Users/Desktop",
        "Natural Language :: English",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.6",
        "Topic :: System :: Archiving :: Backup",
    ],
)
