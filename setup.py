#!/usr/bin/env python
import sys
from setuptools import setup, find_packages

long_description = open('README.rst').read()

setup(name="scrapelib",
      version='0.7.4-dev',
      py_modules=['scrapelib'],
      author="James Turk",
      author_email='jturk@sunlightfoundation.com',
      license="BSD",
      url="http://github.com/sunlightlabs/scrapelib",
      long_description=long_description,
      packages=find_packages(),
      description="a library for scraping things",
      platforms=["any"],
      classifiers=["Development Status :: 4 - Beta",
                   "Intended Audience :: Developers",
                   "License :: OSI Approved :: BSD License",
                   "Natural Language :: English",
                   "Operating System :: OS Independent",
                   "Programming Language :: Python :: 2.6",
                   "Programming Language :: Python :: 2.7",
                   "Programming Language :: Python :: 3.2",
                   ("Topic :: Software Development :: Libraries :: "
                    "Python Modules"),
                   ],
      install_requires=['requests'],
      entry_points="""
[console_scripts]
scrapeshell = scrapelib:scrapeshell
"""
      )
