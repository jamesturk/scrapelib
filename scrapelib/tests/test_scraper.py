import os
import glob
import tempfile
from io import BytesIO
from typing import Optional, Dict, Union, Any, List, cast
from requests.structures import CaseInsensitiveDict

import mock
import pytest  # type: ignore
import requests
from .. import Scraper, HTTPError, HTTPMethodUnavailableError, URLError, FTPError
from .. import _user_agent as default_user_agent
from ..cache import MemoryCache, CacheResponse

HTTPBIN = "http://httpbin.org/"


class FakeResponse(object):
    def __init__(
        self,
        url: str,
        code: int,
        content: Union[str, bytes],
        encoding: str = "utf-8",
        headers: Optional[Dict] = None,
    ):
        self.url = url
        self.status_code = code
        self.content = content
        self.text = str(content)
        self.encoding = encoding
        self.headers = headers or {}


def request_200(method: str, url: str, *args: Any, **kwargs: Any) -> FakeResponse:
    return FakeResponse(url, 200, b"ok")


def request_sslerror(method: str, url: str, *args: Any, **kwargs: Any) -> None:
    raise requests.exceptions.SSLError("sslfail")


mock_200 = mock.Mock(wraps=request_200)
mock_sslerror = mock.Mock(wraps=request_sslerror)


def test_fields() -> None:
    # timeout=0 means None
    s = Scraper(
        requests_per_minute=100,
        raise_errors=False,
        retry_attempts=-1,  # will be 0
        retry_wait_seconds=100,
    )
    assert s.requests_per_minute == 100
    assert s.raise_errors is False
    assert s.retry_attempts == 0  # -1 becomes 0
    assert s.retry_wait_seconds == 100


def test_get() -> None:
    s = Scraper(requests_per_minute=0)
    resp = s.get(HTTPBIN + "get?woo=woo")
    assert resp.status_code == 200
    assert resp.json()["args"]["woo"] == "woo"


def test_post() -> None:
    s = Scraper(requests_per_minute=0)
    resp = s.post(HTTPBIN + "post", {"woo": "woo"})
    assert resp.status_code == 200
    resp_json = resp.json()
    assert resp_json["form"]["woo"] == "woo"
    assert resp_json["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_all_parameters_to_requests() -> None:
    s = Scraper(requests_per_minute=0)

    with mock.patch.object(requests.Session, "request", mock_200) as mocker:
        all_params = {
            "params": {"params": 1},
            "data": "data",
            "cookies": "cookies",
            "files": "files",
            "auth": "auth",
            "timeout": 100,
            "allow_redirects": False,
            "proxies": "Proxies",
            "hooks": "hooks",
            "stream": "stream",
            "verify": False,
            "cert": "cert",
            "json": "{}",
        }
        s.get("https://example.com", **all_params)
        mocker.assert_called_with(
            "GET",
            "https://example.com",
            headers={
                "User-Agent": default_user_agent,
                "Accept-Encoding": "gzip, deflate",
                "Accept": "*/*",
                "Connection": "keep-alive",
            },
            **all_params,
        )


def test_request_throttling() -> None:
    s = Scraper(requests_per_minute=30)
    assert s.requests_per_minute == 30

    mock_sleep = mock.Mock()

    # check that sleep is called on call 2 & 3
    with mock.patch("time.sleep", mock_sleep):
        with mock.patch.object(requests.Session, "request", mock_200):
            s.get("http://dummy/")
            s.get("http://dummy/")
            s.get("http://dummy/")
            assert mock_sleep.call_count == 2
            # should have slept for ~2 seconds
            assert 1.8 <= mock_sleep.call_args[0][0] <= 2.2

    # unthrottled, sleep shouldn't be called
    s.requests_per_minute = 0
    mock_sleep.reset_mock()

    with mock.patch("time.sleep", mock_sleep):
        with mock.patch.object(requests.Session, "request", mock_200):
            s.get("http://dummy/")
            s.get("http://dummy/")
            s.get("http://dummy/")
            assert mock_sleep.call_count == 0


def test_user_agent() -> None:
    s = Scraper(requests_per_minute=0)
    resp = s.get(HTTPBIN + "user-agent")
    ua = resp.json()["user-agent"]
    assert ua == default_user_agent

    s.user_agent = "a different agent"
    resp = s.get(HTTPBIN + "user-agent")
    ua = resp.json()["user-agent"]
    assert ua == "a different agent"


def test_user_agent_from_headers() -> None:
    s = Scraper(requests_per_minute=0)
    s.headers = cast(CaseInsensitiveDict, {"User-Agent": "from headers"})
    resp = s.get(HTTPBIN + "user-agent")
    ua = resp.json()["user-agent"]
    assert ua == "from headers"


def test_404() -> None:
    s = Scraper(requests_per_minute=0)
    pytest.raises(HTTPError, s.get, HTTPBIN + "status/404")

    s.raise_errors = False
    resp = s.get(HTTPBIN + "status/404")
    assert resp.status_code == 404


def test_500() -> None:
    s = Scraper(requests_per_minute=0)

    pytest.raises(HTTPError, s.get, HTTPBIN + "status/500")

    s.raise_errors = False
    resp = s.get(HTTPBIN + "status/500")
    assert resp.status_code == 500


def test_caching() -> None:
    cache_dir = tempfile.mkdtemp()
    s = Scraper(requests_per_minute=0)
    s.cache_storage = MemoryCache()
    s.cache_write_only = False

    resp = s.get(HTTPBIN + "status/200")
    assert not cast(CacheResponse, resp).fromcache
    resp = s.get(HTTPBIN + "status/200")
    assert cast(CacheResponse, resp).fromcache

    for path in glob.iglob(os.path.join(cache_dir, "*")):
        os.remove(path)
    os.rmdir(cache_dir)


def test_urlretrieve() -> None:
    s = Scraper(requests_per_minute=0)

    with mock.patch.object(requests.Session, "request", mock_200):
        fname, resp = s.urlretrieve("http://dummy/")
        with open(fname) as f:
            assert f.read() == "ok"
            assert resp.status_code == 200
        os.remove(fname)

        (fh, set_fname) = tempfile.mkstemp()
        fname, resp = s.urlretrieve("http://dummy/", set_fname)
        assert fname == set_fname
        with open(set_fname) as f:
            assert f.read() == "ok"
            assert resp.status_code == 200
        os.remove(set_fname)

        dirname = os.path.dirname(set_fname)
        fname, resp = s.urlretrieve("http://dummy/", dir=dirname)
        assert os.path.dirname(fname) == dirname
        with open(fname) as f:
            assert f.read() == "ok"
            assert resp.status_code == 200
        os.remove(fname)


# TODO: on these retry tests it'd be nice to ensure that it tries
# 3 times for 500 and once for 404


def test_retry() -> None:
    s = Scraper(retry_attempts=3, retry_wait_seconds=0.001, raise_errors=False)

    # On the first call return a 500, then a 200
    mock_request = mock.Mock(
        side_effect=[
            FakeResponse("http://dummy/", 500, "failure!"),
            FakeResponse("http://dummy/", 200, "success!"),
        ]
    )

    with mock.patch.object(requests.Session, "request", mock_request):
        resp = s.get("http://dummy/")
    assert mock_request.call_count == 2

    # 500 always
    mock_request = mock.Mock(
        return_value=FakeResponse("http://dummy/", 500, "failure!")
    )

    with mock.patch.object(requests.Session, "request", mock_request):
        resp = s.get("http://dummy/")
    assert resp.status_code == 500
    assert mock_request.call_count == 4


def test_retry_404() -> None:
    s = Scraper(retry_attempts=3, retry_wait_seconds=0.001, raise_errors=False)

    # On the first call return a 404, then a 200
    mock_request = mock.Mock(
        side_effect=[
            FakeResponse("http://dummy/", 404, "failure!"),
            FakeResponse("http://dummy/", 200, "success!"),
        ]
    )

    with mock.patch.object(requests.Session, "request", mock_request):
        resp = s.get("http://dummy/", retry_on_404=True)
    assert mock_request.call_count == 2
    assert resp.status_code == 200

    # 404 always
    mock_request = mock.Mock(
        return_value=FakeResponse("http://dummy/", 404, "failure!")
    )

    # retry on 404 true, 4 tries
    with mock.patch.object(requests.Session, "request", mock_request):
        resp = s.get("http://dummy/", retry_on_404=True)
    assert resp.status_code == 404
    assert mock_request.call_count == 4

    # retry on 404 false, just one more try
    with mock.patch.object(requests.Session, "request", mock_request):
        resp = s.get("http://dummy/", retry_on_404=False)
    assert resp.status_code == 404
    assert mock_request.call_count == 5


def test_retry_ssl() -> None:
    s = Scraper(retry_attempts=5, retry_wait_seconds=0.001, raise_errors=False)

    # ensure SSLError is considered fatal even w/ retries
    with mock.patch.object(requests.Session, "request", mock_sslerror):
        with pytest.raises(requests.exceptions.SSLError):
            s.get("http://dummy/", retry_on_404=True)
    assert mock_sslerror.call_count == 1


def test_timeout() -> None:
    s = Scraper()
    s.timeout = 0.001
    with pytest.raises(requests.Timeout):
        s.get(HTTPBIN + "delay/1")


def test_timeout_arg() -> None:
    s = Scraper()
    with pytest.raises(requests.Timeout):
        s.get(HTTPBIN + "delay/1", timeout=0.001)


def test_timeout_retry() -> None:
    # TODO: make this work with the other requests exceptions
    count: List[int] = []

    # On the first call raise timeout
    def side_effect(*args: Any, **kwargs: Any) -> FakeResponse:
        if count:
            return FakeResponse("http://dummy/", 200, "success!")
        count.append(1)
        raise requests.Timeout("timed out :(")

    mock_request = mock.Mock(side_effect=side_effect)

    s = Scraper(retry_attempts=0, retry_wait_seconds=0.001)

    with mock.patch.object(requests.Session, "request", mock_request):
        # first, try without retries
        # try only once, get the error
        pytest.raises(requests.Timeout, s.get, "http://dummy/")
        assert mock_request.call_count == 1

    # reset and try again with retries
    mock_request.reset_mock()
    count = []
    s = Scraper(retry_attempts=2, retry_wait_seconds=0.001)
    with mock.patch.object(requests.Session, "request", mock_request):
        resp = s.get("http://dummy/")
        # get the result, take two tries
        assert resp.content == "success!"
        assert mock_request.call_count == 2


def test_disable_compression() -> None:
    s = Scraper()
    s.disable_compression = True

    # compression disabled
    data = s.get(HTTPBIN + "headers")
    djson = data.json()
    assert "compress" not in djson["headers"]["Accept-Encoding"]
    assert "gzip" not in djson["headers"]["Accept-Encoding"]

    # default is restored
    s.disable_compression = False
    data = s.get(HTTPBIN + "headers")
    djson = data.json()
    assert "compress" in djson["headers"]["Accept-Encoding"]
    assert "gzip" in djson["headers"]["Accept-Encoding"]

    # A supplied Accept-Encoding headers overrides the
    # disable_compression option
    s.headers["Accept-Encoding"] = "xyz"
    data = s.get(HTTPBIN + "headers")
    djson = data.json()
    assert "xyz" in djson["headers"]["Accept-Encoding"]


def test_callable_headers() -> None:
    s = Scraper(header_func=lambda url: {"X-Url": url})

    data = s.get(HTTPBIN + "headers")
    assert data.json()["headers"]["X-Url"] == HTTPBIN + "headers"

    # Make sure it gets called freshly each time
    data = s.get(HTTPBIN + "headers?shh")
    assert data.json()["headers"]["X-Url"] == HTTPBIN + "headers?shh"


def test_headers_weirdness() -> None:
    s = Scraper()
    s.headers = cast(CaseInsensitiveDict, {"accept": "application/json"})
    data = s.get(HTTPBIN + "headers").json()
    assert data["headers"]["Accept"] == "application/json"

    s = Scraper()
    data = s.get(HTTPBIN + "headers", headers={"accept": "application/xml"}).json()
    assert data["headers"]["Accept"] == "application/xml"


def test_ftp_uses_urllib2() -> None:
    s = Scraper(requests_per_minute=0)
    urlopen = mock.Mock(return_value=BytesIO(b"ftp success!"))

    with mock.patch("scrapelib.urllib_urlopen", urlopen):
        r = s.get("ftp://dummy/")
        assert r.status_code == 200
        assert r.content == b"ftp success!"


def test_ftp_retries() -> None:
    count: List[int] = []

    # On the first call raise URLError, then work
    def side_effect(*args: Any, **kwargs: Any) -> BytesIO:
        if count:
            return BytesIO(b"ftp success!")
        count.append(1)
        raise URLError("ftp failure!")

    mock_urlopen = mock.Mock(side_effect=side_effect)

    # retry on
    with mock.patch("scrapelib.urllib_urlopen", mock_urlopen):
        s = Scraper(retry_attempts=2, retry_wait_seconds=0.001)
        r = s.get("ftp://dummy/", retry_on_404=True)
        assert r.content == b"ftp success!"
    assert mock_urlopen.call_count == 2

    # retry off, retry_on_404 on (shouldn't matter)
    count = []
    mock_urlopen.reset_mock()
    with mock.patch("scrapelib.urllib_urlopen", mock_urlopen):
        s = Scraper(retry_attempts=0, retry_wait_seconds=0.001)
        pytest.raises(FTPError, s.get, "ftp://dummy/", retry_on_404=True)
    assert mock_urlopen.call_count == 1


def test_ftp_method_restrictions() -> None:
    s = Scraper(requests_per_minute=0)

    # only http(s) supports non-'GET' requests
    pytest.raises(HTTPMethodUnavailableError, s.post, "ftp://dummy/")


def test_basic_stats() -> None:
    s = Scraper()
    with mock.patch.object(requests.Session, "request", mock_200):
        s.get("http://example.com")
        s.get("http://example.com")
        s.get("http://example.com")

    assert s._total_requests == 3
    assert s._total_time > 0
    assert s.average_request_time == s._total_time / 3

    three_time = s._total_time

    with mock.patch.object(requests.Session, "request", mock_200):
        s.get("http://example.com")
        assert s._total_requests == 4
        assert s._total_time > three_time
        assert s.average_request_time == s._total_time / 4


def test_reset_stats() -> None:
    s = Scraper()
    with mock.patch.object(requests.Session, "request", mock_200):
        s.get("http://example.com")
    assert s._total_requests == 1

    s.reset_stats()
    assert s._total_requests == 0

    with mock.patch.object(requests.Session, "request", mock_200):
        s.get("http://example.com")
    assert s._total_requests == 1
