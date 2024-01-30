from setuptools import setup

setup(
    name='threadbare',
    version='4.1.0',
    description='A Fabric and Paramiko replacement library',
    long_description="A partial replacement of the Fabric and Paramiko libraries using ParallelSSH.",
    long_description_content_type="text/markdown",
    url="https://github.com/elifesciences/threadbare",
    maintainer="Luke",
    maintainer_email="lsh-0@users.noreply.github.com",
    install_requires=["parallel-ssh>=2.12.0"],
    packages=["threadbare"],
    classifiers=[
        "Intended Audience :: System Administrators",
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX",
        "License :: OSI Approved :: GNU Affero General Public License v3",
    ],
    license="AGPLv3"
)
