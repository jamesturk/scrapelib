=========
scrapelib
=========

.. image:: https://github.com/jamesturk/scrapelib/workflows/Test/badge.svg
    :target: https://github.com/jamesturk/scrapelib/actions

.. image:: https://coveralls.io/repos/jamesturk/scrapelib/badge.png?branch=master
    :target: https://coveralls.io/r/jamesturk/scrapelib

.. image:: https://img.shields.io/pypi/v/scrapelib.svg
    :target: https://pypi.python.org/pypi/scrapelib

.. image:: https://readthedocs.org/projects/scrapelib/badge/?version=latest
    :target: https://readthedocs.org/projects/scrapelib/?badge=latest
    :alt: Documentation Status

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

Written by James Turk <dev@jamesturk.net>, thanks to Michael Stephens for
initial urllib2/httplib2 version

See https://github.com/jamesturk/scrapelib/graphs/contributors for contributors.

Requirements
============

* python >=3.7
* requests >= 2.0


Example Usage
=============

Documentation: http://scrapelib.readthedocs.org/en/latest/

::

  import scrapelib
  s = scrapelib.Scraper(requests_per_minute=10)

  # Grab Google front page
  s.get('http://google.com')

  # Will be throttled to 10 HTTP requests per minute
  while True:
      s.get('http://example.com')
