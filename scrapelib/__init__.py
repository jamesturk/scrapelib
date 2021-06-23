import logging
import os
import tempfile
import time
from urllib.request import urlopen as urllib_urlopen
from urllib.error import URLError
from typing import (
    Any,
    Callable,
    Container,
    IO,
    Mapping,
    MutableMapping,
    Optional,
    Text,
    Tuple,
    Union,
    cast,
)
import requests
from .cache import (  # noqa
    CacheStorageBase,
    FileCache,
    SQLiteCache,
    MemoryCache,
    CacheResponse,
)
from ._types import (
    _Data,
    PreparedRequest,
    RequestsCookieJar,
    _HooksInput,
    _AuthType,
    Response,
)


__version__ = "2.0.6"
_user_agent = " ".join(("scrapelib", __version__, requests.utils.default_user_agent()))


_log = logging.getLogger("scrapelib")
_log.addHandler(logging.NullHandler())


class HTTPMethodUnavailableError(requests.RequestException):
    """
    Raised when the supplied HTTP method is invalid or not supported
    by the HTTP backend.
    """

    def __init__(self, message: str, method: str):
        super().__init__(message)
        self.method = method


class HTTPError(requests.HTTPError):
    """
    Raised when urlopen encounters a 4xx or 5xx error code and the
    raise_errors option is true.
    """

    def __init__(self, response: Response, body: dict = None):
        message = "%s while retrieving %s" % (response.status_code, response.url)
        super().__init__(message)
        self.response = response
        self.body = body or self.response.text


class FTPError(requests.HTTPError):
    def __init__(self, url: str):
        message = "error while retrieving %s" % url
        super().__init__(message)


class RetrySession(requests.Session):
    def __init__(self) -> None:
        super().__init__()
        self._retry_attempts = 0
        self.retry_wait_seconds: float = 10

    # retry_attempts is a property so that it can't go negative
    @property
    def retry_attempts(self) -> int:
        return self._retry_attempts

    @retry_attempts.setter
    def retry_attempts(self, value: int) -> None:
        self._retry_attempts = max(value, 0)

    def accept_response(self, response: Response, **kwargs: dict) -> bool:
        return response.status_code < 400

    def request(
        self,
        method: str,
        url: Union[str, bytes, Text],
        params: Union[None, bytes, MutableMapping[Text, Text]] = None,
        data: _Data = None,
        headers: Optional[MutableMapping[Text, Text]] = None,
        cookies: Union[None, RequestsCookieJar, MutableMapping[Text, Text]] = None,
        files: Optional[MutableMapping[Text, IO[Any]]] = None,
        auth: _AuthType = None,
        timeout: Union[None, float, Tuple[float, float], Tuple[float, None]] = None,
        allow_redirects: Optional[bool] = True,
        proxies: Optional[MutableMapping[Text, Text]] = None,
        hooks: Optional[_HooksInput] = None,
        stream: Optional[bool] = None,
        verify: Union[None, bool, Text] = True,
        cert: Union[Text, Tuple[Text, Text], None] = None,
        json: Optional[Any] = None,
        retry_on_404: bool = False,
    ) -> Response:
        # the retry loop
        tries = 0
        exception_raised = None

        while tries <= self.retry_attempts:
            exception_raised = None

            try:
                resp = super().request(
                    method,
                    url,
                    params=params,
                    data=data,
                    headers=headers,
                    cookies=cookies,
                    files=files,
                    auth=auth,
                    timeout=timeout,
                    allow_redirects=allow_redirects,
                    proxies=proxies,
                    hooks=hooks,
                    stream=stream,
                    verify=verify,
                    cert=cert,
                    json=json,
                )

                # break from loop on an accepted response
                if self.accept_response(resp) or (
                    resp.status_code == 404 and not retry_on_404
                ):
                    break

            # note: This is a pretty broad catch-all, but given the plethora of things that can
            #       happen during a requests.request it is used to try to be complete &
            #       future-proof this as much as possible.
            #       Should it become a problem we could either alter to exclude a few others
            #       the way we handle SSLError or we could go back to enumeration of all types.
            except Exception as e:
                if isinstance(e, requests.exceptions.SSLError):
                    raise
                exception_raised = e

            # if we're going to retry, sleep first
            tries += 1
            if tries <= self.retry_attempts:
                # twice as long each time
                wait = self.retry_wait_seconds * (2 ** (tries - 1))
                _log.debug("sleeping for %s seconds before retry" % wait)
                if exception_raised:
                    _log.warning(
                        "got %s sleeping for %s seconds before retry",
                        exception_raised,
                        wait,
                    )
                else:
                    _log.warning("sleeping for %s seconds before retry", wait)
                time.sleep(wait)

        # out of the loop, either an exception was raised or we had a success
        if exception_raised:
            raise exception_raised
        return resp


class ThrottledSession(RetrySession):
    _last_request: float
    _throttled: bool = False

    def _throttle(self) -> None:
        now = time.time()
        diff = self._request_frequency - (now - self._last_request)
        if diff > 0:
            _log.debug("sleeping for %fs" % diff)
            time.sleep(diff)
            self._last_request = time.time()
        else:
            self._last_request = now

    @property
    def requests_per_minute(self) -> int:
        return self._requests_per_minute

    @requests_per_minute.setter
    def requests_per_minute(self, value: int) -> None:
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

    def request(
        self,
        method: str,
        url: Union[str, bytes, Text],
        params: Union[None, bytes, MutableMapping[Text, Text]] = None,
        data: _Data = None,
        headers: Optional[MutableMapping[Text, Text]] = None,
        cookies: Union[None, RequestsCookieJar, MutableMapping[Text, Text]] = None,
        files: Optional[MutableMapping[Text, IO[Any]]] = None,
        auth: _AuthType = None,
        timeout: Union[None, float, Tuple[float, float], Tuple[float, None]] = None,
        allow_redirects: Optional[bool] = True,
        proxies: Optional[MutableMapping[Text, Text]] = None,
        hooks: Optional[_HooksInput] = None,
        stream: Optional[bool] = None,
        verify: Union[None, bool, Text] = True,
        cert: Union[Text, Tuple[Text, Text], None] = None,
        json: Optional[Any] = None,
        retry_on_404: bool = False,
    ) -> Response:
        if self._throttled:
            self._throttle()
        return super().request(
            method,
            url,
            params=params,
            data=data,
            headers=headers,
            cookies=cookies,
            files=files,
            auth=auth,
            timeout=timeout,
            allow_redirects=allow_redirects,
            proxies=proxies,
            hooks=hooks,
            stream=stream,
            verify=verify,
            cert=cert,
            json=json,
            retry_on_404=retry_on_404,
        )


# this object exists because Requests assumes it can call
# resp.raw._original_response.msg.getheaders() and we need to cope with that
class DummyObject(object):
    _original_response: "DummyObject"
    msg: "DummyObject"

    def getheaders(self, name: str) -> str:
        return ""

    def get_all(self, name: str, default: str) -> str:
        return default


_dummy = DummyObject()
_dummy._original_response = DummyObject()
_dummy._original_response.msg = DummyObject()


class FTPAdapter(requests.adapters.BaseAdapter):
    def send(
        self,
        request: PreparedRequest,
        stream: bool = False,
        timeout: Union[None, float, Tuple[float, float], Tuple[float, None]] = None,
        verify: Union[bool, str] = False,
        cert: Union[None, Union[bytes, Text], Container[Union[bytes, Text]]] = None,
        proxies: Optional[Mapping[str, str]] = None,
    ) -> Response:
        if request.method != "GET":
            raise HTTPMethodUnavailableError(
                "FTP requests do not support method '%s'" % request.method,
                cast(str, request.method),
            )
        try:
            if isinstance(timeout, tuple):
                timeout_float = timeout[0]
            else:
                timeout_float = cast(float, timeout)
            real_resp = urllib_urlopen(cast(str, request.url), timeout=timeout_float)
            # we're going to fake a requests.Response with this
            resp = requests.Response()
            resp.status_code = 200
            resp.url = cast(str, request.url)
            resp.headers = requests.structures.CaseInsensitiveDict()
            resp._content = real_resp.read()
            resp.raw = _dummy
            return resp
        except URLError:
            raise FTPError(cast(str, request.url))


# compose sessions, order matters (cache then throttle then retry)
class CachingSession(ThrottledSession):
    def __init__(self, cache_storage: Optional[CacheStorageBase] = None) -> None:
        super().__init__()
        self.cache_storage = cache_storage
        self.cache_write_only = False

    def key_for_request(
        self,
        method: str,
        url: Union[str, bytes],
        params: Union[None, bytes, MutableMapping[Text, Text]] = None,
    ) -> Optional[str]:
        """Return a cache key from a given set of request parameters.

        Default behavior is to return a complete URL for all GET
        requests, and None otherwise.

        Can be overriden if caching of non-get requests is desired.
        """
        if method != "get":
            return None

        return requests.Request(url=url, params=params).prepare().url

    def should_cache_response(self, response: Response) -> bool:
        """Check if a given Response object should be cached.

        Default behavior is to only cache responses with a 200
        status code.
        """
        return response.status_code == 200

    def request(
        self,
        method: str,
        url: Union[str, bytes, Text],
        params: Union[None, bytes, MutableMapping[Text, Text]] = None,
        data: _Data = None,
        headers: Optional[MutableMapping[Text, Text]] = None,
        cookies: Union[None, RequestsCookieJar, MutableMapping[Text, Text]] = None,
        files: Optional[MutableMapping[Text, IO[Any]]] = None,
        auth: _AuthType = None,
        timeout: Union[None, float, Tuple[float, float], Tuple[float, None]] = None,
        allow_redirects: Optional[bool] = True,
        proxies: Optional[MutableMapping[Text, Text]] = None,
        hooks: Optional[_HooksInput] = None,
        stream: Optional[bool] = None,
        verify: Union[None, bool, Text] = True,
        cert: Union[Text, Tuple[Text, Text], None] = None,
        json: Optional[Any] = None,
        retry_on_404: bool = False,
    ) -> CacheResponse:
        """Override, wraps Session.request in caching.

        Cache is only used if key_for_request returns a valid key
        and should_cache_response was true as well.
        """
        # short circuit if cache isn't configured
        if not self.cache_storage:
            resp = super().request(
                method,
                url,
                params=params,
                data=data,
                headers=headers,
                cookies=cookies,
                files=files,
                auth=auth,
                timeout=timeout,
                allow_redirects=allow_redirects,
                proxies=proxies,
                hooks=hooks,
                stream=stream,
                verify=verify,
                cert=cert,
                json=json,
                retry_on_404=retry_on_404,
            )
            resp = cast(CacheResponse, resp)
            resp.fromcache = False
            return resp

        method = method.lower()

        request_key = self.key_for_request(method, url)
        resp_maybe = None

        if request_key and not self.cache_write_only:
            resp_maybe = self.cache_storage.get(request_key)

        if resp_maybe:
            resp = cast(CacheResponse, resp_maybe)
            resp.fromcache = True
        else:
            resp = super().request(
                method,
                url,
                data=data,
                params=params,
                headers=headers,
                cookies=cookies,
                files=files,
                auth=auth,
                timeout=timeout,
                allow_redirects=allow_redirects,
                proxies=proxies,
                hooks=hooks,
                stream=stream,
                verify=verify,
                cert=cert,
                json=json,
                retry_on_404=retry_on_404,
            )
            # save to cache if request and response meet criteria
            if request_key and self.should_cache_response(resp):
                self.cache_storage.set(request_key, resp)
            resp = cast(CacheResponse, resp)
            resp.fromcache = False

        return resp


class Scraper(CachingSession):
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

    def __init__(
        self,
        raise_errors: bool = True,
        requests_per_minute: int = 60,
        retry_attempts: int = 0,
        retry_wait_seconds: float = 5,
        verify: bool = True,
        header_func: Optional[Callable[[Union[bytes, str]], dict]] = None,
    ):

        super().__init__()
        self.mount("ftp://", FTPAdapter())

        # added by this class
        self.raise_errors = raise_errors
        self._header_func = header_func
        self.verify = verify

        # added by ThrottledSession
        self.requests_per_minute = requests_per_minute

        # added by RetrySession
        self.retry_attempts = retry_attempts
        self.retry_wait_seconds = retry_wait_seconds

        # added by CachingSession
        self.cache_storage = None
        self.cache_write_only = True

        # non-parameter options
        self.timeout: Optional[float] = None
        self.user_agent = _user_agent

        # statistics
        self.reset_stats()

    def reset_stats(self) -> None:
        self._total_requests = 0
        self._total_time = 0.0

    @property
    def average_request_time(self) -> float:
        if self._total_requests:
            return self._total_time / self._total_requests
        else:
            return 0

    @property
    def user_agent(self) -> str:
        return self.headers["User-Agent"]

    @user_agent.setter
    def user_agent(self, value: str) -> None:
        self.headers["User-Agent"] = value

    @property
    def disable_compression(self) -> bool:
        return self.headers["Accept-Encoding"] == "text/*"

    @disable_compression.setter
    def disable_compression(self, value: bool) -> None:
        # disabled: set encoding to text/*
        if value:
            self.headers["Accept-Encoding"] = "text/*"
        # enabled: if set to text/* pop, otherwise leave unmodified
        elif self.headers.get("Accept-Encoding") == "text/*":
            self.headers["Accept-Encoding"] = "gzip, deflate, compress"

    def request(
        self,
        method: str,
        url: Union[str, bytes, Text],
        params: Union[None, bytes, MutableMapping[Text, Text]] = None,
        data: _Data = None,
        headers: Optional[MutableMapping[Text, Text]] = None,
        cookies: Union[None, RequestsCookieJar, MutableMapping[Text, Text]] = None,
        files: Optional[MutableMapping[Text, IO[Any]]] = None,
        auth: _AuthType = None,
        timeout: Union[None, float, Tuple[float, float], Tuple[float, None]] = None,
        allow_redirects: Optional[bool] = True,
        proxies: Optional[MutableMapping[Text, Text]] = None,
        hooks: Optional[_HooksInput] = None,
        stream: Optional[bool] = None,
        verify: Union[None, bool, Text] = True,
        cert: Union[Text, Tuple[Text, Text], None] = None,
        json: Optional[Any] = None,
        retry_on_404: bool = False,
    ) -> CacheResponse:
        _log.info("{} - {!r}".format(method.upper(), url))

        # apply global timeout
        if not timeout:
            timeout = self.timeout

        # ordering matters here:
        # func headers are applied on top of class headers
        # param headers are applied on top of those
        if self._header_func:
            func_headers = requests.structures.CaseInsensitiveDict(
                self._header_func(url)
            )
        else:
            func_headers = requests.structures.CaseInsensitiveDict()

        final_headers = requests.sessions.merge_setting(
            func_headers,
            self.headers,
            dict_class=requests.structures.CaseInsensitiveDict,
        )
        final_headers = requests.sessions.merge_setting(
            headers, final_headers, dict_class=requests.structures.CaseInsensitiveDict
        )

        _start_time = time.time()

        resp = super().request(
            method,
            url,
            timeout=timeout,
            headers=final_headers,
            params=params,
            data=data,
            cookies=cookies,
            files=files,
            auth=auth,
            allow_redirects=allow_redirects,
            proxies=proxies,
            hooks=hooks,
            stream=stream,
            verify=verify,
            cert=cert,
            json=json,
            retry_on_404=retry_on_404,
        )
        self._total_requests += 1
        self._total_time += time.time() - _start_time

        if self.raise_errors and not self.accept_response(resp):
            raise HTTPError(resp)
        return resp

    def urlretrieve(
        self,
        url: str,
        filename: str = None,
        method: str = "GET",
        body: dict = None,
        dir: str = None,
        **kwargs: Any,
    ) -> Tuple[str, Response]:
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

        fhandle: IO  # declare type of file handle as IO so both will work
        if not filename:
            fd, filename = tempfile.mkstemp(dir=dir)
            fhandle = os.fdopen(fd, "wb")
        else:
            fhandle = open(filename, "wb")

        fhandle.write(result.content)
        fhandle.close()

        return filename, result


_default_scraper = Scraper(requests_per_minute=0)
