=========
scrapelib
=========

.. image:: https://travis-ci.org/sunlightlabs/scrapelib.svg?branch=master
    :target: https://travis-ci.org/sunlightlabs/scrapelib

.. image:: https://coveralls.io/repos/sunlightlabs/scrapelib/badge.png?branch=master
    :target: https://coveralls.io/r/sunlightlabs/scrapelib

.. image:: https://pypip.in/version/scrapelib/badge.svg
    :target: https://pypi.python.org/pypi/scrapelib

.. image:: https://pypip.in/format/scrapelib/badge.svg
    :target: https://pypi.python.org/pypi/scrapelib

    <p style="height:22px">
    <a href="https://coveralls.io/r/sunlightlabs/scrapelib">
      <img src="https://coveralls.io/repos/sunlightlabs/scrapelib.png"/>
    </a>
    </p>


scrapelib is a library for making requests to less-than-reliable websites, it is implemented
(as of 0.7) as a wrapper around `requests <http://python-requests.org>`_.

scrapelib originated as part of the `Open States <http://openstates.org/>`_
project to scrape the websites of all 50 state legislatures and as a result
was therefore designed with features desirable when dealing with sites that
have intermittent errors or require rate-limiting.

Advantages of using scrapelib over alternatives like httplib2 simply using
requests as-is:

* All of the power of the suberb `requests <http://python-requests.org>`_ library.
* HTTP, HTTPS, and FTP requests via an identical API
* support for simple caching with pluggable cache backends
* request throttling
* configurable retries for non-permanent site failures

scrapelib is a project of Sunlight Labs released under a BSD-style license, see LICENSE for details.

Written by James Turk <jturk@sunlightfoundation.com>

Contributors:
    * Michael Stephens - initial urllib2/httplib2 version
    * Joe Germuska - fix for IPython embedding
    * Alex Chiang - fix to test suite


Requirements
============

* python 2.7, 3.3, 3.4
* requests >= 1.0

Installation
============

scrapelib is available on PyPI and can be installed via ``pip install scrapelib``

PyPI package: http://pypi.python.org/pypi/scrapelib

Source: http://github.com/sunlightlabs/scrapelib

Documentation: http://scrapelib.readthedocs.org/en/latest/

Example Usage
=============

::

  import scrapelib
  s = scrapelib.Scraper(requests_per_minute=10)

  # Grab Google front page
  s.urlopen('http://google.com')

  # Will be throttled to 10 HTTP requests per minute
  while True:
      s.urlopen('http://example.com')
