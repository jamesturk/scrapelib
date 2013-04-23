scrapelib changelog
===================

0.9.0
-----
    * replace FTPSession with FTPAdapter
    * 

0.8.0
-----
**18 March 2013**
    * requests 1.0 compatibility
        * removal of requests pass-throughs
        * deprecation of setting parameters via constructor

0.7.4
-----
**20 December 2012**
    * bugfix for status_code coming from a cache
    * bugfix for setting user-agent from headers
    * fix requests version at <1.0

0.7.3
-----
**21 June 2012**
    * fix for combination of FTP and caching
    * drop unnecessary ScrapelibSession
    * bytes fix for scrapeshell
    * use UTF8 if encoding guess fails

0.7.2
-----
**9 May 2012**
    * bugfix for user-agent check
    * bugfix for cached content with \r characters
    * bugfix for requests >= 0.12
    * cache_dir deprecation is total

0.7.1
-----
**27 April 2012**
    * breaking change: no longer accept URLs without a scheme
    * deprecation of error_dir & context-manager mode
    * addition of overridable accept_response hook
    * bugfix: retry on more requests errors
    * bugfix: unicode cached content no longer incorrectly encoded
    * implement various requests enhancements separately for ease of reuse
    * convert more Scraper parameters to properties

0.7.0
-----
**23 April 2012**
    * rewritten internals to use requests, dropping httplib2
    * as a result of rewrite, caching behavior no longer attempts to be
      compliant with the HTTP specification but is much more configurable
    * added cache_write_only option
    * deprecation of accept_cookies, use_cache_first, cache_dir parameter
    * improved tests
    * improved Python 3 support

0.6.2
-----
**20 April 2012**
    * bugfix for POST-redirects
    * drastically improved test coverage
    * add encoding to ResultStr

0.6.1
-----
**19 April 2012**
    * add .bytes attribute to ResultStr
    * bugfix related to bytes in urlretrieve

0.6.0
-----
**19 April 2012**
    * remove urllib2 fallback for HTTP
    * rework entire test suite to not rely on Flask
    * Unicode & Str unification
    * experimental Python 3.2 support

0.5.8
-----
**15 February 2012**
    * fix to test suite from Alex Chiang

0.5.7
-----
**2 February 2012**
    * -p, --postdata parameter
    * argv fix for IPython <= 0.10 from Joe Germuska
    * treat FTP 550 errors as HTTP 404s
    * use_cache_first improvements

0.5.6
-----
**9 November 2011**
    * scrapeshell fix for IPython >= 0.11
    * scrapelib.urlopen can take method/body params too

0.5.5
-----
**27 September 2011**
    * use None for no timeout, never create non-blocking socket
    * documentation and owernship changes

0.5.4
-----
**7 June 2011**
    * actually fix reinstantiation of Http object

0.5.3
-----
**7 June 2011**
    * bugfix for reinstantiation of Http object

0.5.2
-----
**16 May 2011**
    * support timeout for urllib2 requests

0.5.1
-----
**6 April 2011**
    * bugfix for exception handling on retry
    * fix a deprecation warning for Python 2.6+

0.5.0
-----
**18 March 2011**
    * sphinx documentation
    * addition of scrapeshell
    * addition of retry_on_404 parameter to urlopen
    * bugfix to exception handling scope issue
    * bugfix within tests to avoid false negative

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
