import os
import sys
import time
import socket
import logging
import tempfile
import urllib2
import urlparse
import datetime
import cookielib
import robotparser

try:
    import json
except ImportError:
    import simplejson as json

try:
    import httplib2
    USE_HTTPLIB2 = True
except ImportError:
    USE_HTTPLIB2 = False

__version__ = '0.5.7'
_user_agent = 'scrapelib %s' % __version__


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

    def __init__(self, response, body):
        message = '%s while retrieving %s' % (response.code, response.url)
        super(HTTPError, self).__init__(message)
        self.response = response
        self.body = body


class ErrorManager(object):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type and self._scraper.save_errors:
            self._scraper._save_error(self.response.url, self)
        return False


class ResultStr(str, ErrorManager):
    """
    Wrapper for non-unicode responses.  Can treat identically to a ``str``
    o get body of response, additional headers, etc. available via ``response``
    attribute (instance of :class:`Response`).
    """
    def __new__(cls, scraper, response, str):
        self = str.__new__(cls, str)
        self._scraper = scraper
        self.response = response
        return self


class ResultUnicode(unicode, ErrorManager):
    """
    Wrapper for unicode responses.  Can treat identically to a ``unicode``
    string to get body of response, additional headers, etc. available via
    ``response`` attribute (instance of :class:`Response`).
    """
    def __new__(cls, scraper, response, str):
        self = unicode.__new__(cls, str)
        self._scraper = scraper
        self.response = response
        return self


class Headers(dict):
    """
    Dictionary-like object for storing response headers in a
    case-insensitive way (keeping with the HTTP spec).

    Accessed as the ``headers`` attribute of :class:`Response`.
    """
    def __init__(self, d={}):
        super(Headers, self).__init__()
        for k, v in d.items():
            self[k] = v

    def __getitem__(self, key):
        return super(Headers, self).__getitem__(key.lower())

    def __setitem__(self, key, value):
        super(Headers, self).__setitem__(key.lower(), value)

    def __delitem__(self, key):
        return super(Headers, self).__delitem__(key.lower())

    def __contains__(self, key):
        return super(Headers, self).__contains__(key.lower())

    def __eq__(self, other):
        if len(self) != len(other):
            return False

        for k, v in other.items():
            if self[k] != v:
                return False

        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def getallmatchingheaders(self, name):
        try:
            header = self[name]
            return [name + ": " + header]
        except KeyError:
            return []

    def getheaders(self, name):
        try:
            return [self[name]]
        except KeyError:
            return []


class Response(object):
    """
    Details about a server response.

    Has the following attributes:

    :attr:`url`
        actual URL of the response (after redirects)
    :attr:`requested_url`
        original URL requested
    :attr:`code`
        HTTP response code (not set for FTP requests)
    :attr:`protocol`
        protocol used: http, https, or ftp
    :attr:`fromcache`
        True iff responsse was retrieved from local cache
    :attr:`headers`
        :class:`Headers` instance containing response headers
    """

    def __init__(self, url, requested_url, protocol='http', code=None,
                 fromcache=False, headers={}):
        """
        :param url: the actual URL of the response (after following any
          redirects)
        :param requested_url: the original URL requested
        :param code: response code (if HTTP)
        :param fromcache: response was retrieved from local cache
        """
        self.url = url
        self.requested_url = requested_url
        self.protocol = protocol
        self.code = code
        self.fromcache = fromcache
        self.headers = Headers(headers)

    def info(self):
        return self.headers


class MongoCache(object):
    """
    Implements the httplib2 cache protocol using MongoDB
    (especially useful with capped collection)
    """

    def __init__(self, collection):
        """
        :param collection: a pymongo collection obj to store the cache in
        """
        self.collection = collection

    def get(self, key):
        ret = self.collection.find_one({'_id': key})
        if ret:
            ret = ret['value']
        return ret

    def set(self, key, value):
        self.collection.save({'_id': key, 'value': value})

    def delete(self, key):
        self.collection.remove({'_id': key})


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
    :param accept_cookies: set to False to disable HTTP cookie support
    :param disable_compression: set to True to not accept compressed content
    :param use_cache_first: set to True to always make an attempt to use cached
        data, before even making a HEAD request to check if content is stale
    :param raise_errors: set to True to raise a :class:`HTTPError`
        on 4xx or 5xx response
    :param follow_redirects: set to False to disable redirect following
    :param timeout: socket timeout in seconds (default: None)
    :param retry_attempts: number of times to retry if timeout occurs or
        page returns a (non-404) error
    :param retry_wait_seconds: number of seconds to retry after first failure,
        subsequent retries will double this wait
    :param cache_obj: object to use for non-file based cache.  scrapelib
        provides :class:`MongoCache` for this purpose
    """
    def __init__(self, user_agent=_user_agent,
                 cache_dir=None,
                 headers={},
                 requests_per_minute=60,
                 follow_robots=True,
                 error_dir=None,
                 accept_cookies=True,
                 disable_compression=False,
                 use_cache_first=False,
                 raise_errors=True,
                 follow_redirects=True,
                 timeout=None,
                 retry_attempts=0,
                 retry_wait_seconds=5,
                 cache_obj=None,
                 **kwargs):
        self.user_agent = user_agent
        self.headers = headers
        # weird quirk between 0/None for timeout, accept either
        if timeout == 0:
            timeout = None
        self.timeout = timeout

        self.follow_robots = follow_robots
        self._robot_parsers = {}

        self.requests_per_minute = requests_per_minute

        if cache_dir and not USE_HTTPLIB2:
            _log.warning("httplib2 not available, HTTP caching "
                         "and compression will be disabled.")

        self.error_dir = error_dir
        if self.error_dir:
            try:
                os.makedirs(error_dir)
            except OSError, e:
                if e.errno != 17:
                    raise
            self.save_errors = True
        else:
            self.save_errors = False

        self.accept_cookies = accept_cookies
        self._cookie_jar = cookielib.CookieJar()

        self.disable_compression = disable_compression

        self.use_cache_first = use_cache_first
        self.raise_errors = raise_errors

        if USE_HTTPLIB2:
            self._cache_obj = cache_dir
            if cache_obj:
                self._cache_obj = cache_obj
            self._http = httplib2.Http(self._cache_obj, timeout=timeout)
        else:
            self._http = None

        self.follow_redirects = follow_redirects

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

        if self.accept_cookies:
            # CookieJar expects a urllib2.Request-like object
            req = urllib2.Request(url, headers=headers)
            self._cookie_jar.add_cookie_header(req)
            headers = req.headers
            headers.update(req.unredirected_hdrs)

        headers = Headers(headers)

        if 'User-Agent' not in headers:
            headers['User-Agent'] = self.user_agent

        if self.disable_compression and 'Accept-Encoding' not in headers:
            headers['Accept-Encoding'] = 'text/*'

        return headers

    def _wrap_result(self, response, body):
        if self.raise_errors and response.code >= 400:
            raise HTTPError(response, body)

        if isinstance(body, unicode):
            return ResultUnicode(self, response, body)

        if isinstance(body, str):
            return ResultStr(self, response, body)

        raise ValueError('expected body string')

    @property
    def follow_redirects(self):
        if self._http:
            return self._http.follow_redirects
        return False

    @follow_redirects.setter
    def follow_redirects(self, value):
        if self._http:
            self._http.follow_redirects = value

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

    def _do_request(self, url, method, body, headers, use_httplib2,
                    retry_on_404=False):

        # initialization for this request
        if not use_httplib2:
            req = urllib2.Request(url, data=body, headers=headers)
            if self.accept_cookies:
                self._cookie_jar.add_cookie_header(req)

        # the retry loop
        tries = 0
        exception_raised = None

        while tries <= self.retry_attempts:
            exception_raised = None

            if use_httplib2:
                try:
                    resp, content = self._http.request(url, method, body=body,
                                                       headers=headers)
                    # return on a success/redirect/404
                    if resp.status < 400 or (resp.status == 404
                                             and not retry_on_404):
                        return resp, content
                except socket.error, e:
                    exception_raised = e
                except AttributeError, e:
                    if (str(e) ==
                        "'NoneType' object has no attribute 'makefile'"):
                        # when this error occurs, re-establish the connection
                        self._http = httplib2.Http(self._cache_obj,
                                                   timeout=self.timeout)
                        exception_raised = e
                    else:
                        raise
            else:
                try:
                    _log.info("%sing %s using urllib2" % (method, url))
                    resp = urllib2.urlopen(req, timeout=self.timeout)
                    if self.accept_cookies:
                        self._cookie_jar.extract_cookies(resp, req)

                    return resp
                except urllib2.URLError, e:
                    exception_raised = e
                    if getattr(e, 'code', None) == 404 and not retry_on_404:
                        raise e
                    # also count a 550 from an FTP as a 404
                    elif (url.startswith('ftp://') and '550' in str(e)
                          and not retry_on_404):
                        raise e

            # if we're going to retry, sleep first
            tries += 1
            if tries <= self.retry_attempts:
                # twice as long each time
                wait = self.retry_wait_seconds * (2 ** (tries - 1))
                _log.debug('sleeping for %s seconds before retry' % wait)
                time.sleep(wait)

        if exception_raised:
            raise exception_raised
        else:
            return resp, content

    def urlopen(self, url, method='GET', body=None, retry_on_404=False,
                use_cache_first=None):
        """
            Make an HTTP request and return a
            :class:`ResultStr` or :class:`ResultUnicode` object.

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
        if method == 'POST' and body is None:
            body = ''

        # Default to HTTP requests
        if not "://" in url:
            _log.warning("no URL scheme provided, assuming HTTP")
            url = "http://" + url

        parsed_url = urlparse.urlparse(url)

        headers = self._make_headers(url)
        user_agent = headers['User-Agent']

        if parsed_url.scheme in ['http', 'https']:
            if self.follow_robots and not self._robot_allowed(user_agent,
                                                              parsed_url):
                raise RobotExclusionError(
                    "User-Agent '%s' not allowed at '%s'" % (
                        user_agent, url), url, user_agent)

            if USE_HTTPLIB2:
                _log.info("%sing %s using HTTPLIB2" % (method, url))

                # make sure POSTs have x-www-form-urlencoded content type
                if method == 'POST' and 'Content-Type' not in headers:
                    headers['Content-Type'] = ('application/'
                                               'x-www-form-urlencoded')

                # optionally try a dummy request to cache only
                if use_cache_first and 'Cache-Control' not in headers:
                    headers['cache-control'] = 'only-if-cached'

                    resp, content = self._http.request(url, method,
                                                       body=body,
                                                       headers=headers)
                    if resp.status == 504:
                        headers.pop('cache-control')
                        resp = content = None
                else:
                    resp = content = None

                # do request if there's no copy in local cache
                if not resp:
                    resp, content = self._do_request(url, method, body,
                                                     headers,
                                                     use_httplib2=True,
                                                     retry_on_404=retry_on_404)

                our_resp = Response(resp.get('content-location') or url,
                                    url,
                                    code=resp.status,
                                    fromcache=resp.fromcache,
                                    protocol=parsed_url.scheme,
                                    headers=resp)

                # important to accept cookies before redirect handling
                if self.accept_cookies:
                    fake_req = urllib2.Request(url, headers=headers)
                    self._cookie_jar.extract_cookies(our_resp, fake_req)

                # needed because httplib2 follows the HTTP spec a bit *too*
                # closely and won't issue a GET following a POST (incorrect
                # but expected and often seen behavior)
                if (resp.status in (301, 302, 303, 307) and
                    self.follow_redirects):

                    if resp['location'].startswith('http'):
                        redirect = resp['location']
                    else:
                        redirect = urlparse.urljoin(parsed_url.scheme +
                                                    "://" +
                                                    parsed_url.netloc +
                                                    parsed_url.path,
                                                    resp['location'])
                    _log.debug('redirecting to %s' % redirect)
                    resp = self.urlopen(redirect)
                    resp.response.requested_url = url
                    return resp

                return self._wrap_result(our_resp, content)
        else:
            # not an HTTP(S) request
            if method != 'GET':
                raise HTTPMethodUnavailableError(
                    "non-HTTP(S) requests do not support method '%s'" %
                    method, method)

        if method not in ['GET', 'POST']:
            raise HTTPMethodUnavailableError(
                "urllib2 does not support '%s' method" % method, method)

        resp = self._do_request(url, method, body, headers,
                                use_httplib2=False, retry_on_404=retry_on_404)

        our_resp = Response(resp.geturl(), url, code=resp.code,
                            fromcache=False, protocol=parsed_url.scheme,
                            headers=resp.headers)

        return self._wrap_result(our_resp, resp.read())

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
            f = os.fdopen(fd, 'w')
        else:
            f = open(filename, 'w')

        f.write(result)
        f.close()

        return filename, result.response

    def _save_error(self, url, body):
        exception = sys.exc_info()[1]

        out = {'exception': repr(exception),
               'url': url,
               'body': body,
               'when': str(datetime.datetime.now())}

        base_path = os.path.join(self.error_dir, url.replace('/', ','))
        path = base_path

        n = 0
        while os.path.exists(path):
            n += 1
            path = base_path + "-%d" % n

        with open(path, 'w') as fp:
            json.dump(out, fp, ensure_ascii=False)

_default_scraper = Scraper(follow_robots=False, requests_per_minute=0)


def urlopen(url, method='GET', body=None):
    return _default_scraper.urlopen(url, method, body)


def scrapeshell():
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
            print 'scrapeshell requires ipython'
            return
    try:
        import argparse
    except ImportError:
        print 'scrapeshell requires argparse'
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

    print 'local variables'
    print '---------------'
    print 'url: %s' % url
    print 'html: `scrapelib.ResultStr` instance'
    if USE_LXML:
        print 'doc: `lxml HTML element`'
    embed()
