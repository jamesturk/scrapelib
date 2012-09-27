import datetime
import json
import logging
import os
import sys
import tempfile
import time
import warnings

import requests
from .cache import CachingSession, FileCache

# for backwards-compatibility w/ scrapelib <= 0.6
Headers = requests.structures.CaseInsensitiveDict
ScrapeError = requests.RequestException

if sys.version_info[0] < 3:         # pragma: no cover
    from urllib2 import urlopen as urllib_urlopen
    from urllib2 import URLError as urllib_URLError
    import urlparse
    import robotparser
    _str_type = unicode
else:                               # pragma: no cover
    PY3K = True
    from urllib.request import urlopen as urllib_urlopen
    from urllib.error import URLError as urllib_URLError
    from urllib import parse as urlparse
    from urllib import robotparser
    _str_type = str

__version__ = '0.7.4-dev'
_user_agent = 'scrapelib {0}'.format(__version__)


class NullHandler(logging.Handler):
    def emit(self, record):
        pass

_log = logging.getLogger('scrapelib')
_log.addHandler(NullHandler())


class RobotExclusionError(requests.RequestException):
    """
    Raised when an attempt is made to access a page denied by
    the host's robots.txt file.
    """

    def __init__(self, message, url, user_agent):
        super(RobotExclusionError, self).__init__(message)
        self.url = url
        self.user_agent = user_agent


class HTTPMethodUnavailableError(requests.RequestException):
    """
    Raised when the supplied HTTP method is invalid or not supported
    by the HTTP backend.
    """

    def __init__(self, message, method):
        super(HTTPMethodUnavailableError, self).__init__(message)
        self.method = method


class HTTPError(requests.HTTPError):
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


class FTPError(requests.HTTPError):
    def __init__(self, url):
        message = 'error while retrieving %s' % url
        super(FTPError, self).__init__(message)


class ErrorManager(object):     # pragma: no cover
    def __enter__(self):
        warnings.warn('with urlopen(): support is deprecated as of '
                      'scrapelib 0.7', DeprecationWarning)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False


class ResultStr(_str_type, ErrorManager):
    """
    Wrapper for responses.  Can treat identically to a ``str``
    to get body of response, additional headers, etc. available via
    ``response`` attribute.
    """
    def __new__(cls, scraper, response, requested_url):
        try:
            self = _str_type.__new__(cls, response.text)
        except TypeError:
            # use UTF8 as a default encoding if one couldn't be guessed
            response.encoding = 'utf8'
            self = _str_type.__new__(cls, response.text)
        self._scraper = scraper
        self.bytes = response.content
        self.encoding = response.encoding
        self.response = response
        # augment self.response
        #   manually set: requested_url
        #   aliases: code -> status_code
        self.response.requested_url = requested_url
        self.response.code = self.response.status_code
        return self


class ThrottledSession(requests.Session):
    def _throttle(self):
        now = time.time()
        diff = self._request_frequency - (now - self._last_request)
        if diff > 0:
            _log.debug("sleeping for %fs" % diff)
            time.sleep(diff)
            self._last_request = time.time()
        else:
            self._last_request = now

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

    def request(self, method, url, **kwargs):
        if self._throttled:
            self._throttle()
        return super(ThrottledSession, self).request(method, url, **kwargs)


class RobotsTxtSession(requests.Session):

    def __init__(self, *args, **kwargs):
        super(RobotsTxtSession, self).__init__(*args, **kwargs)
        self._robot_parsers = {}

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

    def request(self, method, url, **kwargs):
        parsed_url = urlparse.urlparse(url)
        user_agent = (kwargs.get('headers', {}).get('user-agent') or
                      self.headers.get('user-agent'))
        # robots.txt is http-only
        if (parsed_url.scheme in ('http', 'https') and
            self.config.get('obey_robots_txt', False) and
            not self._robot_allowed(user_agent, parsed_url)):
            raise RobotExclusionError(
                "User-Agent '%s' not allowed at '%s'" % (
                    user_agent, url), url, user_agent)

        return super(RobotsTxtSession, self).request(method, url, **kwargs)


class FTPSession(requests.Session):
    # HACK: add FTP to allowed schemas
    requests.defaults.SCHEMAS.append('ftp')

    def request(self, method, url, **kwargs):
        if url.startswith('ftp://'):
            if method.lower() != 'get':
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
                return resp
            except urllib_URLError:
                raise FTPError(url)
        else:
            return super(FTPSession, self).request(method, url, **kwargs)


class RetrySession(requests.Session):

    def accept_response(self, response, **kwargs):
        return response.status_code < 400

    def request(self, method, url, retry_on_404=False, **kwargs):
        # the retry loop
        tries = 0
        exception_raised = None

        while tries <= self.config.get('retry_attempts', 0):
            exception_raised = None

            try:
                resp = super(RetrySession, self).request(method, url, **kwargs)
                # break from loop on an accepted response
                if self.accept_response(resp) or (resp.status_code == 404
                                                  and not retry_on_404):
                    break

            except (requests.HTTPError, requests.ConnectionError,
                    requests.Timeout) as e:
                exception_raised = e

            # if we're going to retry, sleep first
            tries += 1
            if tries <= self.config.get('retry_attempts', 0):
                # twice as long each time
                wait = (self.config.get('retry_wait_seconds', 10) *
                        (2 ** (tries - 1)))
                _log.debug('sleeping for %s seconds before retry' % wait)
                time.sleep(wait)

        # out of the loop, either an exception was raised or we had a success
        if exception_raised:
            raise exception_raised
        else:
            return resp


# compose sessions, order matters
class Scraper(RobotsTxtSession,    # first, check robots.txt
              ThrottledSession,    # throttle requests
              CachingSession,      # cache responses
              RetrySession,        # do retries
              FTPSession           # do FTP & HTTP
              ):
    """
    Scraper is the most important class provided by scrapelib (and generally
    the only one to be instantiated directly).  It provides a large number
    of options allowing for customization.

    Usage is generally just creating an instance with the desired options and
    then using the :meth:`urlopen` & :meth:`urlretrieve` methods of that
    instance.

    :param user_agent: the value to send as a User-Agent header on
        HTTP requests (default is "scrapelib |release|")
    :param requests_per_minute: maximum requests per minute (0 for
        unlimited, defaults to 60)
    :param follow_robots: respect robots.txt files (default: True)
    :param disable_compression: set to True to not accept compressed content
    :param raise_errors: set to True to raise a :class:`HTTPError`
        on 4xx or 5xx response
    :param timeout: socket timeout in seconds (default: None)
    :param retry_attempts: number of times to retry if timeout occurs or
        page returns a (non-404) error
    :param retry_wait_seconds: number of seconds to retry after first failure,
        subsequent retries will double this wait
    :param cache_write_only: will write to cache but not read from it, useful
        for building up a cache but not relying on it
    """
    def __init__(self,
                 # requests.Session
                 headers=None,
                 cookies=None,
                 auth=None,
                 timeout=None,
                 proxies=None,
                 hooks=None,
                 params=None,
                 config=None,
                 prefetch=False,
                 verify=True,
                 cert=None,
                 # scrapelib-specific params
                 user_agent=_user_agent,
                 requests_per_minute=60,
                 follow_robots=True,
                 disable_compression=False,
                 raise_errors=True,
                 retry_attempts=0,
                 retry_wait_seconds=5,
                 follow_redirects=True,
                 cache_obj=None,
                 cache_write_only=True,
                 # deprecated options
                 error_dir=None,
                 use_cache_first=None,
                 accept_cookies=None,
                 cache_dir=None,
                ):

        # make timeout of 0 mean timeout of None
        if timeout == 0:
            timeout = None
        if callable(headers):
            self._header_func = headers
            headers = {}
        else:
            self._header_func = None

        super(Scraper, self).__init__(headers, cookies, auth, timeout, proxies,
                                      hooks, params, config, prefetch, verify,
                                      cert, cache_storage=cache_obj)

        # scrapelib-specific settings
        self.raise_errors = raise_errors
        self.follow_redirects = follow_redirects
        self.requests_per_minute = requests_per_minute
        # properties (pass through to config/headers)
        if user_agent != _user_agent or 'user-agent' not in self.headers:
            self.user_agent = user_agent
        self.follow_robots = follow_robots
        self.retry_attempts = retry_attempts
        self.retry_wait_seconds = retry_wait_seconds
        self.cache_write_only = cache_write_only
        self.disable_compression = disable_compression

        # deprecations from 0.7, remove in 0.8
        if accept_cookies:          # pragma: no cover
            warnings.warn('accept_cookies is a no-op as of scrapelib 0.7',
                          DeprecationWarning)
        if use_cache_first:         # pragma: no cover
            warnings.warn('use_cache_first is a no-op as of scrapelib 0.7',
                          DeprecationWarning)
        if error_dir:               # pragma: no cover
            warnings.warn('error_dir is a no-op as of scrapelib 0.7',
                          DeprecationWarning)
        if cache_dir:               # pragma: no cover
            warnings.warn('cache_dir is a no-op as of scrapelib 0.7',
                          DeprecationWarning)

    @property
    def user_agent(self):
        return self.headers['user-agent']

    @user_agent.setter
    def user_agent(self, value):
        self.headers['user-agent'] = value

    @property
    def follow_robots(self):
        return self.config.get('obey_robots_txt', False)

    @follow_robots.setter
    def follow_robots(self, value):
        self.config['obey_robots_txt'] = value

    @property
    def retry_attempts(self):
        return self.config.get('retry_attempts', 0)

    @retry_attempts.setter
    def retry_attempts(self, value):
        self.config['retry_attempts'] = max(value, 0)

    @property
    def retry_wait_seconds(self):
        return self.config.get('retry_wait_seconds', 0)

    @retry_wait_seconds.setter
    def retry_wait_seconds(self, value):
        self.config['retry_wait_seconds'] = value

    @property
    def cache_write_only(self):
        return self.config['cache_write_only']

    @cache_write_only.setter
    def cache_write_only(self, value):
        self.config['cache_write_only'] = value

    @property
    def disable_compression(self):
        return self.headers['accept-encoding'] == 'text/*'

    @disable_compression.setter
    def disable_compression(self, value):
        # disabled: set encoding to text/*
        if value:
            self.headers['accept-encoding'] = 'text/*'
        # enabled: if set to text/* pop, otherwise leave unmodified
        elif self.headers.get('accept-encoding') == 'text/*':
            self.headers.pop('accept-encoding', None)

    def urlopen(self, url, method='GET', body=None, retry_on_404=False):
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
        """
        if self._header_func:
            headers = Headers(self._header_func(url))
        else:
            headers = {}

        _log.info("{0} - {1}".format(method.upper(), url))

        resp = self.request(method, url,
                            data=body, headers=headers,
                            allow_redirects=self.follow_redirects,
                            retry_on_404=retry_on_404)

        if self.raise_errors and not self.accept_response(resp):
            raise HTTPError(resp)
        else:
            return ResultStr(self, resp, url)

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


_default_scraper = Scraper(follow_robots=False, requests_per_minute=0)


def urlopen(url, method='GET', body=None):  # pragma: no cover
    return _default_scraper.urlopen(url, method, body)


def scrapeshell():                  # pragma: no cover
    # clear argv for IPython
    import sys
    orig_argv = sys.argv[1:]
    sys.argv = sys.argv[:1]

    try:
        from IPython import embed
    except ImportError:
        print('scrapeshell requires ipython >= 0.11')
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
        doc = lxml.html.fromstring(html.bytes)

    print('local variables')
    print('---------------')
    print('url: %s' % url)
    print('html: `scrapelib.ResultStr` instance')
    if USE_LXML:
        print('doc: `lxml HTML element`')
    embed()
