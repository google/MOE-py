#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.

"""Base interfaces and code for source control in MOE."""

__author__ = 'dbentley@google.com (Dan Bentley)'


import os

from moe import base


# TODO(dbentley): refactor parts of base.py having to do with source control
# into here.


class CleanClientFinder(object):
  """Finds clean clients for reuse.

  Source control clients can be expensive to create, but cheap to reuse. This
  class helps a person in need of a client find a clean client to reuse.
  """

  def __init__(self, clients_dir):
    self._clients_dir = clients_dir

  def FindClient(self, client_creator):
    """Find a suitable client.

    Args:
      client_creator: str -> base.SourceControlClient. Function that takes a
        directory path and tries to instantiate a source control client within.
        It either returns a client or raises a base.InvalidClientError.

    Returns:
      base.SourceControlClient

    Raises:
      base.Error, if it cannot find a client
    """
    potential_clients = os.listdir(self._clients_dir)
    for p in potential_clients:
      try:
        c = client_creator(os.path.join(self._clients_dir, p))
        c.Checkout()
        return c
      except base.InvalidClientError:
        pass
      print 'Cannot use client in %s; consider cleaning' % os.path.join(
          self._clients_dir, p)

    existing_files = set(potential_clients)

    # if we get here, we need to make a new directory
    for i in range(256):  # reasonable size
      client_name = 'client' + str(i)
      if client_name in existing_files:
        continue
      return client_creator(os.path.join(self._clients_dir, client_name))

    raise base.Error(
        ('Cannot find a new client in %s. All %d sub-directories are dirty.\n'
         'Consider cleaning up one (or more) sub-directories.\n'
         'Consider removing one (or more) sub-directories.'
        ) % (self._clients_dir, len(potential_clients)))
