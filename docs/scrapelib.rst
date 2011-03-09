scrapelib overview
==================

.. module:: scrapelib

scrapelib is configured by instantiating an instance of a :class:`Scraper` with the desired options and paths.

Scraper object
--------------

.. autoclass:: Scraper
    :members:


Response objects
----------------

.. autoclass:: Response

.. autoclass:: Headers


ResultStr and ResultUnicode
~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. autoclass:: ResultStr

.. autoclass:: ResultUnicode


Exceptions
----------

All scrapelib exceptions are a subclass of :class:`ScrapeError`.

.. autoclass:: RobotExclusionError

.. autoclass:: HTTPMethodUnavailableError

.. autoclass:: HTTPError

