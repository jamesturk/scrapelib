scrapelib changelog
===================

0.5.0
-----
**10 March 2011**
    * sphinx documentation
    * addition of scrapeshell
    * small bugfix to exception handling

0.4.3
-----
**11 February 2011**
    * fix retry on certain httplib2 errors
    * add a top-level urlopen function

0.4.2
-----
**8 February 2011**
    * fix retry on socket errors
    * close temporary file handle

0.4.1
-----
**7 December 2010**
    * support retry of requests that produce socket timeouts
    * increased test coverage

0.4.0
-----
**8 November 2010**
    * bugfix: tests require unittest2 or python 2.7
    * configurable retry handling for random failures

0.3.0
-----
**5 October 2010**
    * bugfixes for cookie handling
    * better test suite
    * follow redirects even after a POST
    * change several configuration variables into properties
    * request timeout argument

0.2.0
-----
**9 July 2010**
    * use_cache_first option to avoid extra HTTP HEAD requests
    * raise_errors option to treat HTTP errors as exceptions
    * addition of urlretrieve
