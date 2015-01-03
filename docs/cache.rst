cache overview
==============

.. module:: scrapelib.cache

Assign a :class:`MemoryCache` or :class:`FileCache` to the ``cache_storage``
property of a :class:`scrapelib.Scraper` to cache responses::

    from scrapelib import Scraper
    from scrapelib.cache import FileCache
    cache = FileCache('cache-directory')
    scraper = Scraper()
    scraper.cache_storage = cache

MemoryCache object
------------------

.. autoclass:: MemoryCache
    :members:


FileCache object
----------------

.. autoclass:: FileCache


