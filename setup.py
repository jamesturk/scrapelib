#!/usr/bin/env python
from setuptools import setup
from scrapelib import __version__

long_description = open('README.rst').read()

setup(name="scrapelib",
      version=__version__,
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
      install_requires=["httplib2 >= 0.7.0"],
      entry_points="""
[console_scripts]
scrapeshell = scrapelib:scrapeshell
"""
      )
