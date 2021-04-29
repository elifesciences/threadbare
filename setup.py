from setuptools import setup

setup(
    name='threadbare',
    version='2.0.1',
    description='A Fabric and Paramiko replacement library',
    long_description="A partial replacement of the Fabric/Paramiko library utilising ParallelSSH.",
    long_description_content_type="text/markdown",
    url="https://github.com/elifesciences/threadbare",
    maintainer="Luke",
    maintainer_email="lsh-0@users.noreply.github.com",
    install_requires=["parallel-ssh>=1.9.1"],
    packages=["threadbare"],
    classifiers=[
        "Intended Audience :: System Administrators",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    ],
    license="GPLv3"
)
