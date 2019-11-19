from setuptools import setup

def requirements():
    return open('requirements.txt', 'r').readlines()

setup(
    name='threadbare',
    version='0.1.0',
    install_requires=requirements()
)
