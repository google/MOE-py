#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""A simple middleware-based cache for app engine.

NOTE: the cache must be reset at the beginning of each request
and after each db.put().
"""

import logging

from google.appengine.ext import db


class Cache(object):
  """A Cache object for app engine entities (i.e., instances of Model)."""

  def __init__(self):
    self._cache = {}

  def get(self, key):
    if not key:
      return None
    if key.has_id_or_name():
      key_str = str(key)
      if key_str not in self._cache:
        self._cache[key_str] = db.get(key)
      return self._cache[key_str]
    else:
      # Not cacheable. Ruh-roh.
      logging.warn('Key has neither id nor name: %s', key)
      return db.get(key)


CACHE = Cache()


def Reset():
  global CACHE
  CACHE = Cache()


class CacheResettingMiddleware(object):
  """Middleware that resets the cache on each request."""

  def __init__(self, app):
    self._app = app

  def __call__(self, environ, start_response):
    Reset()
    return self._app.__call__(environ, start_response)


def CachingProperty(property_name, include_setter=False):
  """Make a property that caches what it accesses.

  Args:
    property_name: str, the name of the hidden property
    include_setter: bool, whether to include a setter

  Returns:
    a property
  """

  def get_property(self):
    cls = type(self)
    return CACHE.get(getattr(cls, property_name).get_value_for_datastore(self))
  args = [get_property]

  if include_setter:
    def set_property(self, value):
      setattr(self, property_name, value)
    args.append(set_property)
  return property(*args)


class CacheInvalidatingModel(db.Model):
  """A subclass of Model that invalidates the cache on each put."""

  def put(self, *args, **kwargs):
    Reset()
    return db.Model.put(self, *args, **kwargs)


_ORIGINAL_PUT = db.put


def InvalidateCacheOnPut(*args, **kwargs):
  Reset()
  return _ORIGINAL_PUT(*args, **kwargs)


db.put = InvalidateCacheOnPut
