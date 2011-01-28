#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Test utilities for the MOE scrubber."""

__author__ = 'dborowitz@google.com (Dave Borowitz)'

from google.apputils import resources


def TestResourceName(name):
  """Return a resource name for a resource under the test data directory."""
  prefix = __name__ + ':data/'
  return prefix + name


def TestResourceFilename(name):
  """Return the filename of a resource under the test data directory.

  Args:
    name: A resource name under the test data directory. The path should end in
          '/' if name is a directory, which additionally may result in an
          expensive zipfile extraction.

  Returns:
    The name of a file or directory containing the contents of the requested
    resource name.
  """
  name = TestResourceName(name)
  return resources.GetResourceFilename(name.rstrip('/'))
