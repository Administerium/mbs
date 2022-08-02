from setuptools import setup, find_packages

setup(
    name='mbs',
    version='0.1.0',
    packages=find_packages(),
    include_package_data=True,
    install_requires=[
        'requests==2.*',
        'click==8.1.*',
        'click-log==0.4.*',
        'platformdirs==2.5.*',
        'jinja2==3.1.*'
    ],
    entry_points={
        'console_scripts': [
            'mbs = mbs.__main__:cli',
        ],
    },
)