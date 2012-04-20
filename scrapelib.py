import os
import sys
import time
import socket
import logging
import tempfile
import datetime
import json

import requests
Headers = requests.structures.CaseInsensitiveDict

if sys.version_info[0] < 3:         # pragma: no cover
    from urllib2 import Request as urllib_Request
    from urllib2 import urlopen as urllib_urlopen
    from urllib2 import URLError as urllib_URLError
    import urlparse
    import robotparser
    _str_type = unicode
else:                               # pragma: no cover
    PY3K = True
    from urllib.request import Request as urllib_Request
    from urllib.request import urlopen as urllib_urlopen
    from urllib.error import URLError as urllib_URLError
    from urllib import parse as urlparse
    from urllib import robotparser
    _str_type = str

__version__ = '0.6.2'
_user_agent = 'scrapelib {0}'.format( __version__)


class NullHandler(logging.Handler):
    def emit(self, record):
        pass

_log = logging.getLogger('scrapelib')
_log.addHandler(NullHandler())


class ScrapeError(Exception):
    pass


class RobotExclusionError(ScrapeError):
    """
    Raised when an attempt is made to access a page denied by
    the host's robots.txt file.
    """

    def __init__(self, message, url, user_agent):
        super(RobotExclusionError, self).__init__(message)
        self.url = url
        self.user_agent = user_agent


class HTTPMethodUnavailableError(ScrapeError):
    """
    Raised when the supplied HTTP method is invalid or not supported
    by the HTTP backend.
    """

    def __init__(self, message, method):
        super(HTTPMethodUnavailableError, self).__init__(message)
        self.method = method


class HTTPError(ScrapeError):
    """
    Raised when urlopen encounters a 4xx or 5xx error code and the
    raise_errors option is true.
    """

    def __init__(self, response, body=None):
        message = '%s while retrieving %s' % (response.status_code,
                                              response.url)
        super(HTTPError, self).__init__(message)
        self.response = response
        self.body = body or self.response.text


class ErrorManager(object):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type and self._scraper.save_errors:
            self._scraper._save_error(self.response.url, self)
        return False


class ResultStr(_str_type, ErrorManager):
    """
    Wrapper for responses.  Can treat identically to a ``str``
    to get body of response, additional headers, etc. available via
    ``response`` attribute.
    """
    def __new__(cls, scraper, response, requested_url, fromcache=False):
        self = _str_type.__new__(cls, response.text)
        self._scraper = scraper
        self.bytes = response.content
        self.encoding = response.encoding
        self.response = response
        # augment self.response
        #   manually set: requested_url, fromcache
        #   aliases: code -> status_code
        self.response.requested_url = requested_url
        self.response.fromcache = fromcache
        self.response.code = self.response.status_code
        return self
ResultUnicode = ResultStr


class Scraper(object):
    """
    Scraper is the most important class provided by scrapelib (and generally
    the only one to be instantiated directly).  It provides a large number
    of options allowing for customization.

    Usage is generally just creating an instance with the desired options and
    then using the :meth:`urlopen` & :meth:`urlretrieve` methods of that
    instance.

    :param user_agent: the value to send as a User-Agent header on
        HTTP requests (default is "scrapelib |release|")
    :param cache_dir: if not None, http caching will be enabled with
        cached pages stored under the supplied path
    :param requests_per_minute: maximum requests per minute (0 for
        unlimited, defaults to 60)
    :param follow_robots: respect robots.txt files (default: True)
    :param error_dir: if not None, store scraped documents for which
        an error was encountered.  (TODO: document with blocks)
    :param disable_compression: set to True to not accept compressed content
    :param use_cache_first: set to True to always make an attempt to use cached
        data, before even making a HEAD request to check if content is stale
    :param raise_errors: set to True to raise a :class:`HTTPError`
        on 4xx or 5xx response
    :param timeout: socket timeout in seconds (default: None)
    :param retry_attempts: number of times to retry if timeout occurs or
        page returns a (non-404) error
    :param retry_wait_seconds: number of seconds to retry after first failure,
        subsequent retries will double this wait
    """
    def __init__(self,
                 user_agent=_user_agent,
                 headers=None,
                 requests_per_minute=60,
                 follow_robots=True,
                 error_dir=None,
                 disable_compression=False,
                 use_cache_first=False,
                 raise_errors=True,
                 timeout=None,
                 retry_attempts=0,
                 retry_wait_seconds=5,
                 # deprecated options
                 accept_cookies=None,
                 follow_redirects=None,
                 cache_obj=None,
                 cache_dir=None,
                ):
        self.headers = headers or {}
        # make timeout of 0 mean timeout of None
        if timeout == 0:
            timeout = None
        self.timeout = timeout

        self.follow_robots = follow_robots
        self._robot_parsers = {}

        self.requests_per_minute = requests_per_minute

        self.error_dir = error_dir
        if self.error_dir:
            try:
                os.makedirs(error_dir)
            except OSError as e:
                if e.errno != 17:
                    raise
            self.save_errors = True
        else:
            self.save_errors = False

        if accept_cookies:
            warnings.warn('accept_cookies is deprecated', DeprecationWarning)
        if follow_redirects:
            warnings.warn('follow_redirects is deprecated', DeprecationWarning)
        if cache_obj:
            warnings.warn('cache_obj is deprecated', DeprecationWarning)
        if cache_dir:
            warnings.warn('cache_obj is deprecated', DeprecationWarning)

        self.disable_compression = disable_compression

        self.use_cache_first = use_cache_first
        self.raise_errors = raise_errors

        self._cache_obj = cache_dir
        if cache_obj:
            self._cache_obj = cache_obj
        self._session = requests.Session(timeout=timeout)

        self.follow_redirects = follow_redirects
        self.user_agent = user_agent

        self.retry_attempts = max(retry_attempts, 0)
        self.retry_wait_seconds = retry_wait_seconds

    def _throttle(self):
        now = time.time()
        diff = self._request_frequency - (now - self._last_request)
        if diff > 0:
            _log.debug("sleeping for %fs" % diff)
            time.sleep(diff)
            self._last_request = time.time()
        else:
            self._last_request = now

    def _robot_allowed(self, user_agent, parsed_url):
        _log.info("checking robots permission for %s" % parsed_url.geturl())
        robots_url = urlparse.urljoin(parsed_url.scheme + "://" +
                                      parsed_url.netloc, "robots.txt")

        try:
            parser = self._robot_parsers[robots_url]
            _log.info("using cached copy of %s" % robots_url)
        except KeyError:
            _log.info("grabbing %s" % robots_url)
            parser = robotparser.RobotFileParser()
            parser.set_url(robots_url)
            parser.read()
            self._robot_parsers[robots_url] = parser

        return parser.can_fetch(user_agent, parsed_url.geturl())

    def _make_headers(self, url):
        if callable(self.headers):
            headers = self.headers(url)
        else:
            headers = self.headers

        headers = Headers(headers)

        if 'user-agent' not in headers:
            headers['user-agent'] = self.user_agent

        if self.disable_compression and 'accept-encoding' not in headers:
            headers['accept-encoding'] = 'text/*'

        return headers

    @property
    def follow_redirects(self):
        return self._session.allow_redirects

    @follow_redirects.setter
    def follow_redirects(self, value):
        self._session.allow_redirects = value

    @property
    def requests_per_minute(self):
        return self._requests_per_minute

    @requests_per_minute.setter
    def requests_per_minute(self, value):
        if value > 0:
            self._throttled = True
            self._requests_per_minute = value
            self._request_frequency = 60.0 / value
            self._last_request = 0
        else:
            self._throttled = False
            self._requests_per_minute = 0
            self._request_frequency = 0.0
            self._last_request = 0

    def urlopen(self, url, method='GET', body=None, retry_on_404=False,
                use_cache_first=None):
        """
            Make an HTTP request and return a :class:`ResultStr` object.

            If an error is encountered may raise any of the scrapelib
            `exceptions`_.

            :param url: URL for request
            :param method: any valid HTTP method, but generally GET or POST
            :param body: optional body for request, to turn parameters into
                an appropriate string use :func:`urllib.urlencode()`
            :param retry_on_404: if retries are enabled, retry if a 404 is
                encountered, this should only be used on pages known to exist
                if retries are not enabled this parameter does nothing
                (default: False)
            :param use_cache_first: set to True to make an attempt to use
                cached data, before even making a HEAD request to check if
                content is stale (overrides self.use_cache_first)

        """
        # allow overriding self.use_cache_first
        if use_cache_first is None:
            use_cache_first = self.use_cache_first

        # don't throttle use_cache_first requests
        if self._throttled and not use_cache_first:
            self._throttle()

        method = method.upper()

        # Default to HTTP requests
        if not "://" in url:
            _log.warning("no URL scheme provided, assuming HTTP")
            url = "http://" + url

        headers = self._make_headers(url)
        user_agent = headers['User-Agent']

        _log.info("{0} - {1}".format(method, url))

        # robots.txt is http-only
        parsed_url = urlparse.urlparse(url)
        if parsed_url.scheme in ('http', 'https'):
            if self.follow_robots and not self._robot_allowed(user_agent,
                                                              parsed_url):
                raise RobotExclusionError(
                    "User-Agent '%s' not allowed at '%s'" % (
                        user_agent, url), url, user_agent)

        # the retry loop
        tries = 0
        exception_raised = None

        while tries <= self.retry_attempts:
            exception_raised = None

            if url.startswith('http'):
                try:
                    resp = self._session.request(method, url, data=body,
                                                 headers=headers)
                    result = ResultStr(self, resp, url)
                    # break from loop on a success/redirect/404
                    if resp.status_code < 400 or (resp.status_code == 404
                                                  and not retry_on_404):
                        break
                except requests.Timeout as e:
                    exception_raised = e
            else:  # FTP using urllib2
                if method != 'GET':
                    raise HTTPMethodUnavailableError(
                        "non-HTTP(S) requests do not support method '%s'" %
                        method, method)
                try:
                    real_resp = urllib_urlopen(url, timeout=self.timeout)
                    # we're going to fake a requests.Response with this
                    resp = requests.Response()
                    resp.status_code = 200
                    resp.url = url
                    resp.headers = {}
                    resp._content = real_resp.read()
                    result = ResultStr(self, resp, url)
                    break
                except urllib_URLError as e:
                    exception_raised = e
                    # FTP 550 ~ HTTP 404
                    if '550' in str(e) and not retry_on_404:
                        raise e

            # if we're going to retry, sleep first
            tries += 1
            if tries <= self.retry_attempts:
                # twice as long each time
                wait = self.retry_wait_seconds * (2 ** (tries - 1))
                _log.debug('sleeping for %s seconds before retry' % wait)
                time.sleep(wait)

        # out of the loop, either an exception was raised or we had a success
        if exception_raised:
            raise exception_raised
        elif self.raise_errors and resp.status_code >= 400:
            raise HTTPError(resp)
        else:
            return result

    def urlretrieve(self, url, filename=None, method='GET', body=None):
        """
        Save result of a request to a file, similarly to
        :func:`urllib.urlretrieve`.

        If an error is encountered may raise any of the scrapelib
        `exceptions`_.

        A filename may be provided or :meth:`urlretrieve` will safely create a
        temporary file.  Either way it is the responsibility of the caller
        to ensure that the temporary file is deleted when it is no longer
        needed.

        :param url: URL for request
        :param filename: optional name for file
        :param method: any valid HTTP method, but generally GET or POST
        :param body: optional body for request, to turn parameters into
            an appropriate string use :func:`urllib.urlencode()`
        :returns filename, response: tuple with filename for saved
            response (will be same as given filename if one was given,
            otherwise will be a temp file in the OS temp directory) and
            a :class:`Response` object that can be used to inspect the
            response headers.
        """
        result = self.urlopen(url, method, body)

        if not filename:
            fd, filename = tempfile.mkstemp()
            f = os.fdopen(fd, 'wb')
        else:
            f = open(filename, 'wb')

        f.write(result.bytes)
        f.close()

        return filename, result.response

    def _save_error(self, url, body):
        exception = sys.exc_info()[1]

        out = {'exception': repr(exception),
               'url': url,
               'body': body.bytes,
               'when': str(datetime.datetime.now())}

        base_path = os.path.join(self.error_dir, url.replace('/', ','))
        path = base_path

        n = 0
        while os.path.exists(path):
            n += 1
            path = base_path + "-%d" % n

        with open(path, 'wb') as fp:
            json.dump(out, fp, ensure_ascii=False)

_default_scraper = Scraper(follow_robots=False, requests_per_minute=0)


def urlopen(url, method='GET', body=None):
    return _default_scraper.urlopen(url, method, body)


def scrapeshell():                  # pragma: no cover
    # clear argv for IPython
    import sys
    orig_argv = sys.argv[1:]
    sys.argv = sys.argv[:1]

    try:
        from IPython import embed
    except ImportError:
        try:
            from IPython.Shell import IPShellEmbed
            embed = IPShellEmbed()
        except ImportError:
            print('scrapeshell requires ipython')
            return
    try:
        import argparse
    except ImportError:
        print('scrapeshell requires argparse')
        return
    try:
        import lxml.html
        USE_LXML = True
    except ImportError:
        USE_LXML = False

    parser = argparse.ArgumentParser(prog='scrapeshell',
                                     description='interactive python shell for'
                                     ' scraping')
    parser.add_argument('url', help="url to scrape")
    parser.add_argument('--ua', dest='user_agent', default=_user_agent,
                        help='user agent to make requests with')
    parser.add_argument('--robots', dest='robots', action='store_true',
                        default=False, help='obey robots.txt')
    parser.add_argument('--noredirect', dest='redirects', action='store_false',
                        default=True, help="don't follow redirects")
    parser.add_argument('-p', '--postdata', dest='postdata',
                        default=None,
                        help="POST data (will make a POST instead of GET)")
    args = parser.parse_args(orig_argv)

    scraper = Scraper(user_agent=args.user_agent,
                      follow_robots=args.robots,
                      follow_redirects=args.redirects)
    url = args.url
    if args.postdata:
        html = scraper.urlopen(args.url, 'POST', args.postdata)
    else:
        html = scraper.urlopen(args.url)

    if USE_LXML:
        doc = lxml.html.fromstring(html)

    print('local variables')
    print('---------------')
    print('url: %s' % url)
    print('html: `scrapelib.ResultStr` instance')
    if USE_LXML:
        print('doc: `lxml HTML element`')
    embed()
