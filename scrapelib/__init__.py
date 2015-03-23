import logging
import os
import sys
import tempfile
import time

import requests
from .cache import CachingSession, FileCache    # noqa

if sys.version_info[0] < 3:         # pragma: no cover
    from urllib2 import urlopen as urllib_urlopen
    from urllib2 import URLError as urllib_URLError
    _str_type = unicode
else:                               # pragma: no cover
    from urllib.request import urlopen as urllib_urlopen
    from urllib.error import URLError as urllib_URLError
    _str_type = str

__version__ = '1.0.0'
_user_agent = ' '.join(('scrapelib', __version__, requests.utils.default_user_agent()))


class NullHandler(logging.Handler):
    def emit(self, record):
        pass

_log = logging.getLogger('scrapelib')
_log.addHandler(NullHandler())


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
        message = '%s while retrieving %s' % (response.status_code, response.url)
        super(HTTPError, self).__init__(message)
        self.response = response
        self.body = body or self.response.text


class FTPError(requests.HTTPError):
    def __init__(self, url):
        message = 'error while retrieving %s' % url
        super(FTPError, self).__init__(message)


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


# this object exists because Requests assumes it can call
# resp.raw._original_response.msg.getheaders() and we need to cope with that
class DummyObject(object):
    def getheaders(self, name):
        return ''

    def get_all(self, name, default):
        return default

_dummy = DummyObject()
_dummy._original_response = DummyObject()
_dummy._original_response.msg = DummyObject()


class FTPAdapter(requests.adapters.BaseAdapter):

    def send(self, request, stream=False, timeout=None, verify=False, cert=None, proxies=None):
        if request.method != 'GET':
            raise HTTPMethodUnavailableError("FTP requests do not support method '%s'" %
                                             request.method, request.method)
        try:
            real_resp = urllib_urlopen(request.url, timeout=timeout)
            # we're going to fake a requests.Response with this
            resp = requests.Response()
            resp.status_code = 200
            resp.url = request.url
            resp.headers = {}
            resp._content = real_resp.read()
            resp.raw = _dummy
            return resp
        except urllib_URLError:
            raise FTPError(request.url)


class RetrySession(requests.Session):

    def __init__(self):
        super(RetrySession, self).__init__()
        self._retry_attempts = 0
        self.retry_wait_seconds = 10

    # retry_attempts is a property so that it can't go negative
    @property
    def retry_attempts(self):
        return self._retry_attempts

    @retry_attempts.setter
    def retry_attempts(self, value):
        self._retry_attempts = max(value, 0)

    def accept_response(self, response, **kwargs):
        return response.status_code < 400

    def request(self, method, url, retry_on_404=False, **kwargs):
        # the retry loop
        tries = 0
        exception_raised = None

        while tries <= self.retry_attempts:
            exception_raised = None

            try:
                resp = super(RetrySession, self).request(method, url, **kwargs)
                # break from loop on an accepted response
                if self.accept_response(resp) or (resp.status_code == 404 and not retry_on_404):
                    break

            except (requests.HTTPError, requests.ConnectionError, requests.Timeout) as e:
                if isinstance(e, requests.exceptions.SSLError):
                    raise
                exception_raised = e

            # if we're going to retry, sleep first
            tries += 1
            if tries <= self.retry_attempts:
                # twice as long each time
                wait = (self.retry_wait_seconds * (2 ** (tries - 1)))
                _log.debug('sleeping for %s seconds before retry' % wait)
                time.sleep(wait)

        # out of the loop, either an exception was raised or we had a success
        if exception_raised:
            raise exception_raised
        else:
            return resp


# compose sessions, order matters (cache then throttle then retry)
class Scraper(CachingSession, ThrottledSession, RetrySession):
    """
    Scraper is the most important class provided by scrapelib (and generally
    the only one to be instantiated directly).  It provides a large number
    of options allowing for customization.

    Usage is generally just creating an instance with the desired options and
    then using the :meth:`urlopen` & :meth:`urlretrieve` methods of that
    instance.

    :param raise_errors: set to True to raise a :class:`HTTPError`
        on 4xx or 5xx response
    :param requests_per_minute: maximum requests per minute (0 for
        unlimited, defaults to 60)
    :param retry_attempts: number of times to retry if timeout occurs or
        page returns a (non-404) error
    :param retry_wait_seconds: number of seconds to retry after first failure,
        subsequent retries will double this wait
    """
    def __init__(self, raise_errors=True, requests_per_minute=60, retry_attempts=0,
                 retry_wait_seconds=5, header_func=None):

        super(Scraper, self).__init__()
        self.mount('ftp://', FTPAdapter())

        # added by this class
        self.raise_errors = raise_errors

        # added by ThrottledSession
        self.requests_per_minute = requests_per_minute

        # added by RetrySession
        self.retry_attempts = retry_attempts
        self.retry_wait_seconds = retry_wait_seconds

        # added by this class
        self._header_func = header_func

        # added by CachingSession
        self.cache_storage = None
        self.cache_write_only = True

        # non-parameter options
        self.timeout = None
        self.user_agent = _user_agent

        # statistics structure
        self.reset_stats()

    def reset_stats(self):
        self.stats = {}
        self.stats['total_requests'] = 0
        self.stats['total_time'] = 0
        self.stats['average_time'] = None

    @property
    def user_agent(self):
        return self.headers['User-Agent']

    @user_agent.setter
    def user_agent(self, value):
        self.headers['User-Agent'] = value

    @property
    def disable_compression(self):
        return self.headers['Accept-Encoding'] == 'text/*'

    @disable_compression.setter
    def disable_compression(self, value):
        # disabled: set encoding to text/*
        if value:
            self.headers['Accept-Encoding'] = 'text/*'
        # enabled: if set to text/* pop, otherwise leave unmodified
        elif self.headers.get('Accept-Encoding') == 'text/*':
            self.headers['Accept-Encoding'] = 'gzip, deflate, compress'

    def request(self, method, url, **kwargs):
        _log.info("{0} - {1}".format(method.upper(), url))

        # apply global timeout
        timeout = kwargs.pop('timeout', self.timeout)

        if self._header_func:
            headers = requests.structures.CaseInsensitiveDict(self._header_func(url))
        else:
            headers = {}

        kwarg_headers = kwargs.pop('headers', {})
        headers = requests.sessions.merge_setting(
            headers, self.headers,
            dict_class=requests.structures.CaseInsensitiveDict)
        headers = requests.sessions.merge_setting(
            kwarg_headers, headers,
            dict_class=requests.structures.CaseInsensitiveDict)

        _start_time = time.time()

        resp = super(Scraper, self).request(method, url, timeout=timeout, headers=headers,
                                            **kwargs)
        self.stats['total_requests'] += 1
        self.stats['total_time'] += (time.time() - _start_time)
        self.stats['average_time'] = self.stats['total_time'] / self.stats['total_requests']

        if self.raise_errors and not self.accept_response(resp):
            raise HTTPError(resp)
        return resp

    def urlretrieve(self, url, filename=None, method='GET', body=None, dir=None, **kwargs):
        """
        Save result of a request to a file, similarly to
        :func:`urllib.urlretrieve`.

        If an error is encountered may raise any of the scrapelib
        `exceptions`_.

        A filename may be provided or :meth:`urlretrieve` will safely create a
        temporary file. If a directory is provided, a file will be given a random
        name within the specified directory. Either way, it is the responsibility
        of the caller to ensure that the temporary file is deleted when it is no
        longer needed.

        :param url: URL for request
        :param filename: optional name for file
        :param method: any valid HTTP method, but generally GET or POST
        :param body: optional body for request, to turn parameters into
            an appropriate string use :func:`urllib.urlencode()`
        :param dir: optional directory to place file in
        :returns filename, response: tuple with filename for saved
            response (will be same as given filename if one was given,
            otherwise will be a temp file in the OS temp directory) and
            a :class:`Response` object that can be used to inspect the
            response headers.
        """
        result = self.request(method, url, data=body, **kwargs)
        result.code = result.status_code    # backwards compat

        if not filename:
            fd, filename = tempfile.mkstemp(dir=dir)
            f = os.fdopen(fd, 'wb')
        else:
            f = open(filename, 'wb')

        f.write(result.content)
        f.close()

        return filename, result


_default_scraper = Scraper(requests_per_minute=0)


def urlopen(url, method='GET', body=None, **kwargs):  # pragma: no cover
    return _default_scraper.urlopen(url, method, body, **kwargs)
