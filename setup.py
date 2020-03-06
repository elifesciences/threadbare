from setuptools import setup

setup(
    name='threadbare',
    version='1.1.1',
    description='A Fabric and Paramiko replacement library',
    long_description="A partial replacement of the Fabric/Paramiko library utilising ParallelSSH.",
    url="https://github.com/elifesciences/threadbare",
    maintainer="Luke (lsh)",
    install_requires=["parallel-ssh==1.9.1"],
    classifiers=[
        "Intended Audience :: System Administrators",
        "Programming Language :: Python :: 2.7",
        "Programming Language :: Python :: 3",
        "Operating System :: POSIX",
        "License :: OSI Approved :: GNU General Public License v3 (GPLv3)",
    ],
    license="GPLv3"
)
