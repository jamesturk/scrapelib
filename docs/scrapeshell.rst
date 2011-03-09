scrapeshell
===========

Many times, especially during development, it is useful to open an interactive shell to tinker with a page.  Often the HTML being returned is slightly out of sync with what is being seen in the browser, and it can be difficult to detect these differences without firing up an interactive python shell and inspecting what :meth:`~scrapelib.Scraper.urlopen` is returning.

If scrapelib is installed on your path it provides :program:`scrapeshell`, an entrypoint that will open an `IPython <http://ipython.scipy.org/moin/>`_ shell.  It will present the user with an instance of :class:`ResultStr` with the contents of the scraped page and if `lxml <http://lxml.de>`_ is installed, an :class:`lxml.html.HtmlElement` instance as well.

.. note:
    scrapeshell requires argparse and IPython, which are not dependencies of scrapelib


.. program:: scrapeshell

scrapeshell arguments
---------------------

.. option:: url

    scrapeshell requires a URL, which will then be retrieved via a :meth:`~scrapelib.Scraper.urlopen`
    call.

.. option:: --ua user_agent

    Set a custom user agent (useful for seeing if a site is returning different results based on UA).

.. option:: --robots

    Obey robots.txt (default is to ignore).

.. option:: --noredirect

    Don't follow redirects.
