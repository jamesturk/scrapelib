scrapelib |release|
===================

Overview
--------
scrapelib is a library for making requests to websites, particularly those
that may be less-than-reliable.

scrapelib originated as part of the `Open States <http://openstates.org/`_
project to scrape the websites of all 50 state legislatures and as a result
was therefore designed with features desirable when dealing with sites that
have intermittent errors or require rate-limiting.

As of version 0.7 scrapelib has been retooled to take advantage of the superb
`requests <http://python-requests.org>`_ library.

Advantages of using scrapelib over alternatives like httplib2 simply using
requests as-is:

* All of the power of the suberb `requests <http://python-requests.org>`_ library.
* HTTP(S) and FTP requests via an identical API
* support for simple caching with pluggable cache backends
* request throtting
* configurable retries for non-permanent site failures

Contents
--------

.. toctree::
   :maxdepth: 2

   scrapelib
   scrapeshell
   changelog

Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
