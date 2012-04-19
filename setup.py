#!/usr/bin/env python
import sys
from setuptools import setup

long_description = open('README.rst').read()

required = ['httplib2>=0.7.0']
if sys.version_info[0] > 2:
    required.append('chardet2')
else:
    required.append('chardet')

setup(name="scrapelib",
      version='0.6.0',
      py_modules=['scrapelib'],
      author="James Turk",
      author_email='jturk@sunlightfoundation.com',
      license="BSD",
      url="http://github.com/sunlightlabs/scrapelib",
      long_description=long_description,
      description="a library for scraping things",
      platforms=["any"],
      classifiers=["Development Status :: 4 - Beta",
                   "Intended Audience :: Developers",
                   "License :: OSI Approved :: BSD License",
                   "Natural Language :: English",
                   "Operating System :: OS Independent",
                   "Programming Language :: Python",
                   ("Topic :: Software Development :: Libraries :: "
                    "Python Modules"),
                   ],
      install_requires=required,
      entry_points="""
[console_scripts]
scrapeshell = scrapelib:scrapeshell
"""
      )
