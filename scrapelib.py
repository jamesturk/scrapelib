import os
import sys
import time
import logging
import urllib2
import urlparse
import datetime
import functools
import cookielib
import contextlib
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

__version__ = '0.1'
_user_agent = 'scrapelib %s' % __version__

_log = logging.getLogger('scrapelib')
_stream_handler = logging.StreamHandler()
_stream_handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s"))
_log.addHandler(_stream_handler)


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


class ErrorManager(object):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type and self._scraper.save_errors:
            self._scraper._save_error(self.response.url, self)
        return False


class ResultStr(str, ErrorManager):
    def __new__(cls, scraper, response, str):
        self = str.__new__(cls, str)
        self._scraper = scraper
        self.response = response
        return self


class ResultUnicode(unicode, ErrorManager):
    def __new__(cls, scraper, response, str):
        self = unicode.__new__(cls, str)
        self._scraper = scraper
        self.response = response
        return self


def wrap_result(scraper, response, body):
    if isinstance(body, unicode):
        return ResultUnicode(scraper, response, body)

    if isinstance(body, str):
        return ResultStr(scraper, response, body)

    raise ValueError('expected body string')


class Headers(dict):
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
        for k, v in other.items():
            if self[k] != v:
                return False
        return True

    def getallmatchingheaders(self, name):
        header = self.get(name)
        if header:
            return [name + ": " + header]
        return []

    def getheaders(self, name):
        header = self.get(name)
        if header:
            return [header]
        return []


class Response(object):

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


class Scraper(object):

    def __init__(self, user_agent=_user_agent,
                 cache_dir=None, headers={},
                 requests_per_minute=60,
                 follow_robots=True,
                 error_dir=None,
                 accept_cookies=True,
                 disable_compression=False, **kwargs):
        """
        :param user_agent: the value to send as a User-Agent header on
          HTTP requests
        :param cache_dir: if not None, http caching will be enabled with
          cached pages stored under the supplied path
        :param requests_per_minute: maximum requests per minute (0 for
          unlimited)
        :param follow_robots: respect robots.txt files
        :param error_dir: if not None,
        :param accept_cookies: HTTP cookie support
        :param disable_compression: do not accept compressed content
        """
        self.user_agent = user_agent
        self.headers = headers

        self.follow_robots = follow_robots
        self._robot_parsers = {}

        if requests_per_minute > 0:
            self.throttled = True
            self.request_frequency = 60.0 / requests_per_minute
            self.last_request = 0
        else:
            self.throttled = False
            self.request_frequency = 0.0
            self.last_request = 0

        if cache_dir and not USE_HTTPLIB2:
            _log.warning("httplib2 not available, HTTP caching "
                         "and compression will be disabled.")

        self.error_dir = error_dir
        if self.error_dir:
            self.save_errors = True
        else:
            self.save_errors = False

        self.accept_cookies = accept_cookies
        self._cookie_jar = cookielib.CookieJar()

        self.disable_compression = disable_compression

        if USE_HTTPLIB2:
            self._http = httplib2.Http(cache_dir)

    def _throttle(self):
        now = time.time()
        diff = self.request_frequency - (now - self.last_request)
        if diff > 0:
            _log.info("sleeping for %fs" % diff)
            time.sleep(diff)
            self.last_request = time.time()
        else:
            self.last_request = now

    def _robot_allowed(self, user_agent, parsed_url):
        robots_url = urlparse.urljoin(parsed_url.scheme + "://" +
                                      parsed_url.netloc, "robots.txt")

        try:
            parser = self._robot_parsers[robots_url]
        except KeyError:
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

    def urlopen(self, url, method='GET', body=None):
        if self.throttled:
            self._throttle()

        if method == 'POST' and body is None:
            body = ''

        parsed_url = urlparse.urlparse(url)

        # Default to HTTP requests
        if not parsed_url.scheme:
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
                resp, content = self._http.request(url, method,
                                                   body=body,
                                                   headers=headers)

                our_resp = Response(resp.get('content-location'),
                                    url,
                                    code=resp.status,
                                    fromcache=resp.fromcache,
                                    protocol=parsed_url.scheme,
                                    headers=resp)

                if self.accept_cookies:
                    fake_req = urllib2.Request(url, headers=headers)
                    self._cookie_jar.extract_cookies(our_resp, fake_req)

                return wrap_result(self, our_resp, content)
        else:
            # not an HTTP(S) request
            if method != 'GET':
                raise HTTPMethodUnavailableError(
                    "non-HTTP(S) requests do not support method '%s'" %
                    method, method)

        if method not in ['GET', 'POST']:
            raise HTTPMethodUnavailableError(
                "urllib2 does not support '%s' method" % method, method)

        req = urllib2.Request(url, data=body, headers=headers)
        if self.accept_cookies:
            self._cookie_jar.add_cookie_header(req)
        resp = urllib2.urlopen(req)
        if self.accept_cookies:
            self._cookie_jar.extract_cookies(resp, req)

        our_resp = Response(resp.geturl(), url, code=resp.code,
                            fromcache=False, protocol=parsed_url.scheme,
                            headers=resp.headers)

        return wrap_result(self, our_resp, resp.read())

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
