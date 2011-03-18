import os
import sys
import glob
import time
import socket
import urllib2
import tempfile
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

app = flask.Flask(__name__)
app.config.shaky_fail = False
app.config.shaky_404_fail = False

@app.route('/')
def index():
    resp = app.make_response("Hello world!")
    return resp


@app.route('/ua')
def ua():
    resp = app.make_response(flask.request.headers['user-agent'])
    resp.headers['cache-control'] = 'no-cache'
    return resp


@app.route('/p/s.html')
def secret():
    return "secret"


@app.route('/redirect')
def redirect():
    return flask.redirect(flask.url_for('index'))


@app.route('/500')
def fivehundred():
    flask.abort(500)


@app.route('/robots.txt')
def robots():
    return """
    User-agent: *
    Disallow: /p/
    Allow: /
    """


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
    def setUp(self):
        self.cache_dir = tempfile.mkdtemp()
        self.error_dir = tempfile.mkdtemp()
        self.s = scrapelib.Scraper(requests_per_minute=0,
                                   error_dir=self.error_dir,
                                   cache_dir=self.cache_dir,
                                   use_cache_first=True)

    def tearDown(self):
        for path in glob.iglob(os.path.join(self.cache_dir, "*")):
            os.remove(path)
        os.rmdir(self.cache_dir)
        for path in glob.iglob(os.path.join(self.error_dir, "*")):
            os.remove(path)
        os.rmdir(self.error_dir)

    def test_get(self):
        self.assertEqual('Hello world!',
                         self.s.urlopen("http://localhost:5000/"))

    def test_request_throttling(self):
        requests = 0
        s = scrapelib.Scraper(requests_per_minute=30)
        self.assertEqual(s.requests_per_minute, 30)

        begin = time.time()
        while time.time() <= (begin + 1):
            s.urlopen("http://localhost:5000/")
            requests += 1
        self.assert_(requests <= 2)

        s.requests_per_minute = 500
        requests = 0
        begin = time.time()
        while time.time() <= (begin + 1):
            s.urlopen("http://localhost:5000/")
            requests += 1
        self.assert_(requests > 5)

    def test_user_agent(self):
        resp = self.s.urlopen("http://localhost:5000/ua")
        self.assertEqual(resp, scrapelib._user_agent)

        self.s.user_agent = 'a different agent'
        resp = self.s.urlopen("http://localhost:5000/ua")
        self.assertEqual(resp, 'a different agent')

    def test_default_to_http(self):
        self.assertEqual('Hello world!',
                         self.s.urlopen("localhost:5000/"))

    def test_follow_robots(self):
        self.assertRaises(scrapelib.RobotExclusionError, self.s.urlopen,
                          "http://localhost:5000/p/s.html")
        self.assertRaises(scrapelib.RobotExclusionError, self.s.urlopen,
                          "http://localhost:5000/p/a/t/h/")

        self.s.follow_robots = False
        self.assertEqual("secret",
                         self.s.urlopen("http://localhost:5000/p/s.html"))
        self.assertRaises(scrapelib.HTTPError, self.s.urlopen,
                          "http://localhost:5000/p/a/t/h/")

    def test_error_context(self):
        def raises():
            with self.s.urlopen("http://localhost:5000/"):
                raise Exception('test')

        self.assertRaises(Exception, raises)
        self.assertTrue(os.path.isfile(os.path.join(
            self.error_dir, "http:,,localhost:5000,")))

    def test_404(self):
        self.assertRaises(scrapelib.HTTPError, self.s.urlopen,
                          "http://localhost:5000/does/not/exist")

        self.s.raise_errors = False
        resp = self.s.urlopen("http://localhost:5000/does/not/exist")
        self.assertEqual(404, resp.response.code)

    def test_500(self):
        self.assertRaises(scrapelib.HTTPError, self.s.urlopen,
                          "http://localhost:5000/500")

        self.s.raise_errors = False
        resp = self.s.urlopen("http://localhost:5000/500")
        self.assertEqual(resp.response.code, 500)

    def test_follow_redirect(self):
        resp = self.s.urlopen("http://localhost:5000/redirect")
        self.assertEqual("http://localhost:5000/", resp.response.url)
        self.assertEqual("http://localhost:5000/redirect",
                         resp.response.requested_url)
        self.assertEqual(200, resp.response.code)

        self.s.follow_redirects = False
        resp = self.s.urlopen("http://localhost:5000/redirect")
        self.assertEqual("http://localhost:5000/redirect",
                         resp.response.url)
        self.assertEqual("http://localhost:5000/redirect",
                         resp.response.requested_url)
        self.assertEqual(302, resp.response.code)

        # No following redirects with urllib2 only
        scrapelib.USE_HTTPLIB2 = False
        s = scrapelib.Scraper()
        self.assertFalse(s.follow_redirects)
        scrapelib.USE_HTTPLIB2 = True

    def test_caching(self):
        resp = self.s.urlopen("http://localhost:5000/")
        self.assertFalse(resp.response.fromcache)
        resp = self.s.urlopen("http://localhost:5000/")
        self.assert_(resp.response.fromcache)

        self.s.use_cache_first = False
        resp = self.s.urlopen("http://localhost:5000/")
        self.assertFalse(resp.response.fromcache)

    def test_urlretrieve(self):
        fname, resp = self.s.urlretrieve("http://localhost:5000/")
        with open(fname) as f:
            self.assertEqual(f.read(), "Hello world!")
            self.assertEqual(200, resp.code)
        os.remove(fname)

        (fh, set_fname) = tempfile.mkstemp()
        fname, resp = self.s.urlretrieve("http://localhost:5000/",
                                         set_fname)
        self.assertEqual(fname, set_fname)
        with open(set_fname) as f:
            self.assertEqual(f.read(), "Hello world!")
            self.assertEqual(200, resp.code)
        os.remove(set_fname)


    # TODO: on these retry tests it'd be nice to ensure that it tries
    # 3 times for 500 and once for 404

    def test_retry_httplib2(self):
        s = scrapelib.Scraper(retry_attempts=3, retry_wait_seconds=0.1)

        # one failure, then success
        resp, content = s._do_request('http://localhost:5000/shaky',
                                      'GET', None, {}, use_httplib2=True)
        self.assertEqual(content, 'shaky success!')


        # 500 always
        resp, content = s._do_request('http://localhost:5000/500',
                                      'GET', None, {}, use_httplib2=True)
        self.assertEqual(resp.status, 500)


    def test_retry_httplib2_404(self):
        s = scrapelib.Scraper(retry_attempts=3, retry_wait_seconds=0.1)

        # like shaky but raises a 404
        resp, content = s._do_request('http://localhost:5000/shaky404',
                                      'GET', None, {}, use_httplib2=True,
                                      retry_on_404=True)
        self.assertEqual(content, 'shaky404 success!')

        # 404
        resp, content = s._do_request('http://localhost:5000/404',
                                      'GET', None, {}, use_httplib2=True)
        self.assertEqual(resp.status, 404)

    def test_retry_urllib2(self):
        s = scrapelib.Scraper(retry_attempts=3, retry_wait_seconds=0.1)

        # without httplib2
        resp = s._do_request('http://localhost:5000/shaky',
                             'GET', None, {}, use_httplib2=False)
        self.assertEqual(resp.read(), 'shaky success!')

        # 500 always
        self.assertRaises(urllib2.URLError, s._do_request,
                          'http://localhost:5000/500',
                          'GET', None, {}, use_httplib2=False)

    def test_retry_urllib2_404(self):
        s = scrapelib.Scraper(retry_attempts=3, retry_wait_seconds=0.1)

        # like shaky but raises a 404
        resp = s._do_request('http://localhost:5000/shaky404',
                             'GET', None, {}, use_httplib2=False,
                                      retry_on_404=True)
        self.assertEqual(resp.read(), 'shaky404 success!')

        # 404
        self.assertRaises(urllib2.HTTPError, s._do_request,
                          'http://localhost:5000/404', 'GET', None, {},
                          use_httplib2=False)

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

    def test_method_restrictions(self):
        # we can't use urllib2 for non GET/POST requests
        scrapelib.USE_HTTPLIB2 = False
        self.assertRaises(scrapelib.HTTPMethodUnavailableError,
                          lambda: self.s.urlopen("http://google.com",
                                                 method='PUT'))
        scrapelib.USE_HTTPLIB2 = True

        # only http(s) supports non-'GET' requests
        self.assertRaises(scrapelib.HTTPMethodUnavailableError,
                          lambda: self.s.urlopen("ftp://google.com",
                                                 method='POST'))


if __name__ == '__main__':
    process = Process(target=run_server)
    process.start()
    time.sleep(0.1)
    unittest.main(exit=False)
    process.terminate()
