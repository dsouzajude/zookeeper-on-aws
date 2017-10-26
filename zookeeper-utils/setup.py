#!/usr/bin/env python

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

setup(
    name='zkutils',
    description='A utility library for Zookeeper',
    version='0.0.1',
    packages=['zkutils'],
    include_package_data=True,
    scripts = [
        'scripts/zk-bootstrap',
        'scripts/zk-recovery',
        'scripts/zk-remove-terminated'
    ],
    install_requires=[
        'boto',
        'botocore',
        'boto3',
        'requests',
        'nose',
        'mock',
        'argparse'
    ],
    author="Jude D'Souza",
    author_email='dsouza_jude@hotmail.com',
    maintainer="Jude D'Souza",
    maintainer_email='dsouza_jude@hotmail.com',
    url='http://github.com/dsouzajude/zookeeper-on-aws',
    zip_safe=False,
    keywords=[
        'zookeeper',
        'aws'
    ],
    classifiers=(
        'Intended Audience :: Developers',
        'Operating System :: OS Independent',
        'Environment :: Console',
        'Programming Language :: Python',
        'Programming Language :: Python :: 2.7',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
    )
)
