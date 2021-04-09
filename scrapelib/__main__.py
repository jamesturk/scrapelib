# pragma: no cover
import sys
from . import Scraper, _user_agent
import argparse


def scrapeshell() -> None:
    # clear argv for IPython
    orig_argv = sys.argv[1:]
    sys.argv = sys.argv[:1]

    try:
        from IPython import embed  # type: ignore
    except ImportError:
        print("scrapeshell requires ipython >= 0.11")
        return
    try:
        import lxml.html  # type: ignore

        USE_LXML = True
    except ImportError:
        USE_LXML = False

    parser = argparse.ArgumentParser(
        prog="scrapeshell", description="interactive python shell for" " scraping"
    )
    parser.add_argument("url", help="url to scrape")
    parser.add_argument(
        "--ua",
        dest="user_agent",
        default=_user_agent,
        help="user agent to make requests with",
    )
    parser.add_argument(
        "-p",
        "--postdata",
        dest="postdata",
        default=None,
        help="POST data (will make a POST instead of GET)",
    )
    args = parser.parse_args(orig_argv)

    scraper = Scraper()
    scraper.user_agent = args.user_agent
    url = args.url
    if args.postdata:
        html = scraper.post(args.url, args.postdata)
    else:
        html = scraper.get(args.url)

    if USE_LXML:
        doc = lxml.html.fromstring(html.content)  # noqa

    print("local variables")
    print("---------------")
    print("url: %s" % url)
    print("html: requests Response instance")
    if USE_LXML:
        print("doc: `lxml HTML element`")
    else:
        print("doc not available: lxml not installed")
    embed()


scrapeshell()
