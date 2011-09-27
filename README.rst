=========
scrapelib
=========

A Python library for scraping things.

Features include:

  * HTTP, HTTPS, FTP requests via an identical API
  * HTTP caching, compression and cookies
  * redirect following
  * request throttling
  * robots.txt compliance (optional)
  * robust error handling

scrapelib is a project of Sunlight Labs (c) 2010.
All code is released under a BSD-style license, see LICENSE for details.

Written by Michael Stephens <mstephens@sunlightfoundation.com> and James Turk
<jturk@sunlightfoundation.com>.

Source is available at http://github.com/sunlightlabs/scrapelib.

Requirements
============

python >= 2.6

httplib2 optional but highly recommended.

Installation
============

scrapelib is available on PyPI and thus can be downloaded installed via
``pip install scrapelib`` or ``easy_install scrapelib``.

To install from a source distribution run ``python setup.py install``.

Example Usage
=============

::

  import scrapelib
  s = scrapelib.Scraper(requests_per_minute=10, allow_cookies=True,
                        follow_robots=True)

  # Grab Google front page
  s.urlopen('http://google.com')

  # Will raise RobotExclusionError
  s.urlopen('http://google.com/search')

  # Will be throttled to 10 HTTP requests per minute
  while True:
      s.urlopen('http://example.com')