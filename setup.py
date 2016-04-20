#!/usr/bin/env python
# -*- coding: utf-8 -*-
try:
    from setuptools.core import setup, Extension
except ImportError:
    from distutils.core import setup, Extension

with open('README.md') as readme_file:
    readme = readme_file.read()

requirements = [
    'biopython',
    'matplotlib',
    'numpy',
    'pystache',
    'scipy<0.16',
    'pyfasta',
    'pysam',
]

test_requirements = [
    # TODO: put package test requirements here
]

covest_poisson = Extension(
    'covest_poisson',
    libraries=['m'],
    sources=['c_src/covest_poissonmodule.c'],
)

setup(
    name='covest',
    version='0.1.0',
    description="Covest estimates the coverage and genom size, "
    "just from k-mer abundance histogram computed from DNA sequences reads.",
    long_description=readme,
    author="Michal Hozza",
    author_email='mhozza@gmail.com',
    url='https://github.com/mhozza/covest',
    packages=[
        'covest',
    ],
    package_dir={
        'covest': 'covest'
    },
    include_package_data=True,
    package_data={
        'covest': ['templates/*.tpl'],
    },
    ext_modules=[covest_poisson],
    install_requires=requirements,
    entry_points={
        'console_scripts': ['covest=covest.covest:run'],
    },
    scripts=[
        'bin/gsest.py',
        'bin/generate_sequence.py',
        'bin/read_simulator.py',
        'bin/prepare_experiment.py',
        'bin/sam_to_fasta.py',
        'bin/experiment_table.py',
    ],
    license='ISCL',
    zip_safe=False,
    keywords='covest',
    classifiers=[
        'Development Status :: 2 - Pre-Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: ISC License (ISCL)',
        'Natural Language :: English',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.3',
        'Programming Language :: Python :: 3.4',
        'Programming Language :: Python :: 3.5',
    ],
    test_suite='tests',
    tests_require=test_requirements
)