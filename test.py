import os
import sys
import glob
import json
import time
import socket
import tempfile
import robotparser
from multiprocessing import Process

if sys.version_info[1] < 7:
    try:
        import unittest2 as unittest
    except ImportError:
        print 'Test Suite requires Python 2.7 or unittest2'
        sys.exit(1)
else:
    import unittest

import mock
import flask
import httplib2
import scrapelib

HTTPBIN = 'http://httpbin.org/'

app = flask.Flask(__name__)
app.config.shaky_fail = False
app.config.shaky_404_fail = False


@app.route('/')
def index():
    resp = app.make_response("Hello world!")
    return resp


@app.route('/shaky')
def shaky():
    # toggle failure state each time
    app.config.shaky_fail = not app.config.shaky_fail

    if app.config.shaky_fail:
        flask.abort(500)
    else:
        return "shaky success!"


@app.route('/shaky404')
def shaky404():
    # toggle failure state each time
    app.config.shaky_404_fail = not app.config.shaky_404_fail

    if app.config.shaky_404_fail:
        flask.abort(404)
    else:
        return "shaky404 success!"


def run_server():
    class NullFile(object):
        def write(self, s):
            pass

    sys.stdout = NullFile()
    sys.stderr = NullFile()

    app.run()


class HeaderTest(unittest.TestCase):
    def test_keys(self):
        h = scrapelib.Headers()
        h['A'] = '1'

        self.assertEqual(h['A'], '1')

        self.assertEqual(h.getallmatchingheaders('A'), ["A: 1"])
        self.assertEqual(h.getallmatchingheaders('b'), [])
        self.assertEqual(h.getheaders('A'), ['1'])
        self.assertEqual(h.getheaders('b'), [])

        # should be case-insensitive
        self.assertEqual(h['a'], '1')
        h['a'] = '2'
        self.assertEqual(h['A'], '2')

        self.assert_('a' in h)
        self.assert_('A' in h)

        del h['A']
        self.assert_('a' not in h)
        self.assert_('A' not in h)

    def test_equality(self):
        h1 = scrapelib.Headers()
        h1['Accept-Encoding'] = '*'

        h2 = scrapelib.Headers()
        self.assertNotEqual(h1, h2)

        h2['accept-encoding'] = 'not'
        self.assertNotEqual(h1, h2)

        h2['accept-encoding'] = '*'
        self.assertEqual(h1, h2)


class ScraperTest(unittest.TestCase):

    def _setup_cache(self):
        self.cache_dir = tempfile.mkdtemp()
        self.error_dir = tempfile.mkdtemp()
        self.s = scrapelib.Scraper(requests_per_minute=0,
                                   error_dir=self.error_dir,
                                   cache_dir=self.cache_dir,
                                   use_cache_first=True)


    def setUp(self):
        self.cache_dir = tempfile.mkdtemp()
        self.error_dir = tempfile.mkdtemp()
        self.s = scrapelib.Scraper(requests_per_minute=0,
                                   error_dir=self.error_dir,
                                   follow_robots=False
                                  )

    def tearDown(self):
        if hasattr(self, 'cache_dir'):
            for path in glob.iglob(os.path.join(self.cache_dir, "*")):
                os.remove(path)
            os.rmdir(self.cache_dir)
        for path in glob.iglob(os.path.join(self.error_dir, "*")):
            os.remove(path)
        os.rmdir(self.error_dir)

    def test_get(self):
        resp = self.s.urlopen(HTTPBIN + 'get?woo=woo')
        self.assertEqual(resp.response.code, 200)
        self.assertEqual(json.loads(resp)['args']['woo'], 'woo')

    def test_request_throttling(self):
        s = scrapelib.Scraper(requests_per_minute=30, follow_robots=False,
                              accept_cookies=False)
        self.assertEqual(s.requests_per_minute, 30)

        # mock to quickly return a dummy response
        mock_do_request = mock.Mock(return_value=(
            scrapelib.Response('', '', None, None), 'ok'))
        mock_sleep = mock.Mock()

        # check that sleep is called
        with mock.patch('time.sleep', mock_sleep):
            with mock.patch.object(s, '_do_request', mock_do_request):
                s.urlopen('http://dummy/')
                s.urlopen('http://dummy/')
                s.urlopen('http://dummy/')
                self.assert_(mock_sleep.call_count == 2)
                # should have slept for ~2 seconds
                self.assert_(1.8 <= mock_sleep.call_args[0][0] <= 2.2)
                self.assert_(mock_do_request.call_count == 3)

        # unthrottled, should be able to fit in lots of calls
        s.requests_per_minute = 0
        mock_do_request.reset_mock()
        mock_sleep.reset_mock()

        with mock.patch('time.sleep', mock_sleep):
            with mock.patch.object(s, '_do_request', mock_do_request):
                s.urlopen('http://dummy/')
                s.urlopen('http://dummy/')
                s.urlopen('http://dummy/')
                self.assert_(mock_sleep.call_count == 0)
                self.assert_(mock_do_request.call_count == 3)

    def test_user_agent(self):
        resp = self.s.urlopen(HTTPBIN + 'user-agent')
        ua = json.loads(resp)['user-agent']
        self.assertEqual(ua, scrapelib._user_agent)

        self.s.user_agent = 'a different agent'
        resp = self.s.urlopen(HTTPBIN + 'user-agent')
        ua = json.loads(resp)['user-agent']
        self.assertEqual(ua, 'a different agent')

    def test_default_to_http(self):

        def do_request(url, *args, **kwargs):
            return scrapelib.Response(url, url), ''
        mock_do_request = mock.Mock(wraps=do_request)

        with mock.patch.object(self.s, '_do_request', mock_do_request):
            self.assertEqual('http://dummy/',
                             self.s.urlopen("dummy/").response.url)

    def test_follow_robots(self):
        self.s.follow_robots = True

        def do_request(url, *args, **kwargs):
            return scrapelib.Response(url, url, code=200), ''

        with mock.patch.object(self.s, '_do_request', do_request):

            # set a fake robots.txt for http://dummy
            parser = robotparser.RobotFileParser()
            parser.parse(['User-agent: *', 'Disallow: /private/', 'Allow: /'])
            self.s._robot_parsers['http://dummy/robots.txt'] = parser

            # anything behind private fails
            self.assertRaises(scrapelib.RobotExclusionError, self.s.urlopen,
                              "http://dummy/private/secret.html")
            # but others work
            self.assertEqual(200,
                             self.s.urlopen("http://dummy/").response.code)

            # turn off follow_robots, everything works
            self.s.follow_robots = False
            self.assertEqual(200,
             self.s.urlopen("http://dummy/private/secret.html").response.code)

    def test_error_context(self):
        def do_request(url, *args, **kwargs):
            return scrapelib.Response(url, url), ''
        mock_do_request = mock.Mock(wraps=do_request)

        with mock.patch.object(self.s, '_do_request', mock_do_request):
            def raises():
                with self.s.urlopen("http://dummy/"):
                    raise Exception('test')

            self.assertRaises(Exception, raises)
        self.assertTrue(os.path.isfile(os.path.join(
            self.error_dir, "http:,,dummy,")))

    def test_404(self):
        self.assertRaises(scrapelib.HTTPError, self.s.urlopen,
                          HTTPBIN + 'status/404')

        self.s.raise_errors = False
        resp = self.s.urlopen(HTTPBIN + 'status/404')
        self.assertEqual(404, resp.response.code)

    def test_500(self):
        self.assertRaises(scrapelib.HTTPError, self.s.urlopen,
                          HTTPBIN + 'status/500')

        self.s.raise_errors = False
        resp = self.s.urlopen(HTTPBIN + 'status/500')
        self.assertEqual(resp.response.code, 500)

    def test_follow_redirect(self):
        redirect_url = HTTPBIN + 'redirect/1'
        final_url = HTTPBIN + 'get'

        resp = self.s.urlopen(redirect_url)
        self.assertEqual(final_url, resp.response.url)
        self.assertEqual(redirect_url, resp.response.requested_url)
        self.assertEqual(200, resp.response.code)

        self.s.follow_redirects = False
        resp = self.s.urlopen(redirect_url)
        self.assertEqual(redirect_url, resp.response.url)
        self.assertEqual(redirect_url, resp.response.requested_url)
        self.assertEqual(302, resp.response.code)

    def test_caching(self):
        self._setup_cache()

        resp = self.s.urlopen(HTTPBIN + 'status/200')
        self.assertFalse(resp.response.fromcache)
        resp = self.s.urlopen(HTTPBIN + 'status/200')
        self.assert_(resp.response.fromcache)

        self.s.use_cache_first = False
        resp = self.s.urlopen(HTTPBIN + 'status/200')
        self.assertFalse(resp.response.fromcache)

    def test_urlretrieve(self):
        # assume urlopen works fine
        content = self.s._wrap_result(scrapelib.Response('', '', code=200),
                                      'in your file')
        fake_urlopen = mock.Mock(return_value=content)

        with mock.patch.object(self.s, 'urlopen', fake_urlopen):
            fname, resp = self.s.urlretrieve("http://dummy/")
            with open(fname) as f:
                self.assertEqual(f.read(), 'in your file')
                self.assertEqual(200, resp.code)
            os.remove(fname)

            (fh, set_fname) = tempfile.mkstemp()
            fname, resp = self.s.urlretrieve("http://dummy/",
                                             set_fname)
            self.assertEqual(fname, set_fname)
            with open(set_fname) as f:
                self.assertEqual(f.read(), 'in your file')
                self.assertEqual(200, resp.code)
            os.remove(set_fname)

    # TODO: on these retry tests it'd be nice to ensure that it tries
    # 3 times for 500 and once for 404

    def test_retry_httplib2(self):
        s = scrapelib.Scraper(retry_attempts=3, retry_wait_seconds=0.1)

        # one failure, then success
        resp, content = s._do_request('http://localhost:5000/shaky',
                                      'GET', None, {})
        self.assertEqual(content, 'shaky success!')

        # 500 always
        resp, content = s._do_request(HTTPBIN + 'status/500',
                                      'GET', None, {})
        self.assertEqual(resp.code, 500)

    def test_retry_httplib2_404(self):
        s = scrapelib.Scraper(retry_attempts=3, retry_wait_seconds=0.1)

        # like shaky but raises a 404
        resp, content = s._do_request('http://localhost:5000/shaky404',
                                      'GET', None, {}, retry_on_404=True)
        self.assertEqual(content, 'shaky404 success!')

        # 404
        resp, content = s._do_request(HTTPBIN + 'status/404',
                                      'GET', None, {})
        self.assertEqual(resp.code, 404)

    def test_socket_retry(self):
        orig_request = httplib2.Http().request
        count = []

        # On the first call raise socket.timeout
        # On subsequent calls pass through to httplib2.Http.request
        def side_effect(*args, **kwargs):
            if count:
                return orig_request(*args, **kwargs)
            count.append(1)
            raise socket.timeout('timed out :(')

        mock_request = mock.Mock(side_effect=side_effect)

        with mock.patch.object(httplib2.Http, 'request', mock_request):
            s = scrapelib.Scraper(retry_attempts=0, retry_wait_seconds=0.1)
            self.assertRaises(socket.timeout, self.s.urlopen,
                              "http://localhost:5000/")

        mock_request.reset_mock()
        count = []
        with mock.patch.object(httplib2.Http, 'request', mock_request):
            s = scrapelib.Scraper(retry_attempts=2, retry_wait_seconds=0.1)
            resp = s.urlopen("http://localhost:5000/")
            self.assertEqual(resp, "Hello world!")

    def test_disable_compression(self):
        s = scrapelib.Scraper(disable_compression=True)

        headers = s._make_headers("http://google.com")
        self.assertEqual(headers['accept-encoding'], 'text/*')

        # A supplied Accept-Encoding headers overrides the
        # disable_compression option
        s.headers['accept-encoding'] = '*'
        headers = s._make_headers('http://google.com')
        self.assertEqual(headers['accept-encoding'], '*')

    def test_callable_headers(self):
        s = scrapelib.Scraper(headers=lambda url: {'URL': url})

        headers = s._make_headers('http://google.com')
        self.assertEqual(headers['url'], 'http://google.com')

        # Make sure it gets called freshly each time
        headers = s._make_headers('example.com')
        self.assertEqual(headers['url'], 'example.com')

    def test_ftp_method_restrictions(self):
        # only http(s) supports non-'GET' requests
        self.assertRaises(scrapelib.HTTPMethodUnavailableError,
                          lambda: self.s.urlopen("ftp://google.com",
                                                 method='POST'))


if __name__ == '__main__':
    process = Process(target=run_server)
    process.start()
    time.sleep(0.1)
    try:
        unittest.main()
    finally:
        process.terminate()
