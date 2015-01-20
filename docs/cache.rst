cache overview
==============

.. module:: scrapelib.cache

Assign a :class:`MemoryCache`, :class:`FileCache`, or :class:`SQLiteCache` to
the ``cache_storage`` property of a :class:`scrapelib.Scraper` to cache
responses::

    from scrapelib import Scraper
    from scrapelib.cache import FileCache
    cache = FileCache('cache-directory')
    scraper = Scraper()
    scraper.cache_storage = cache
    scraper.cache_write_only = False

MemoryCache object
------------------

.. autoclass:: MemoryCache
    :members:


FileCache object
----------------

.. autoclass:: FileCache
    :members:


SQLiteCache object
------------------

.. autoclass:: SQLiteCache
    :members:

