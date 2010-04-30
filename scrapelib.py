import os
import sys
import time
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

try:
    import lxml.html
    USE_LXML = True
except ImportError:
    USE_LXML = False


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


class FakeResponse(object):
    """
    Adapts httplib2 response objects for use with cookielib.CookieJar
    """

    def __init__(self, response):
        self._response = response

    def info(self):
        return self

    def getallmatchingheaders(self, name):
        header = self._response.get(name.lower(), None)
        if header:
            return [name + ": " + header]
        return []

    def getheaders(self, name):
        header = self._response.get(name.lower(), None)
        if header:
            return [header]
        return []


class Scraper(object):

    def __init__(self, user_agent='scrapelib 0.1',
                 cache_dir=None, headers={},
                 requests_per_minute=60,
                 follow_robots=True,
                 error_dir=None,
                 accept_cookies=True,
                 disable_compression=False):
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
            print "httplib2 not available, HTTP caching and compression" \
                "will be disabled."

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
            print "sleeping for %fs" % diff
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

                if self.accept_cookies:
                    fake_resp = FakeResponse(resp)
                    fake_req = urllib2.Request(url, headers=headers)
                    self._cookie_jar.extract_cookies(fake_resp, fake_req)

                return content

        if method not in ['GET', 'POST']:
            raise ScrapeError("urllib2 does not support '%s' method" %
                              method)

        req = urllib2.Request(url, data=body, headers=headers)
        if self.allow_cookies:
            self._cookie_jar.add_cookie_header(req)
        resp = urllib2.urlopen(req)
        if self.allow_cookies:
            self._cookie_jar.extract_cookies(resp, req)
        return resp.read()

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
            json.dump(out, fp)

    @contextlib.contextmanager
    def urlopen_context(self, url):
        body = None

        try:
            body = self.urlopen(url)
            yield body
        except:
            if self.save_errors:
                self._save_error(url, body)
            raise

    @contextlib.contextmanager
    def lxml_context(self, url):
        """
        Like :method:`urlopen_context`, except returns an lxml parsed
        document.
        """
        if not USE_LXML:
            raise Exception("lxml does not seem to be installed.")

        body = None
        try:
            body = self.urlopen(url)
            elem = lxml.html.fromstring(body)
            yield elem
        except:
            if self.save_errors:
                self._save_error(url, body)
            raise
