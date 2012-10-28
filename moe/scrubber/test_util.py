#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Test utilities for the MOE scrubber."""

__author__ = 'dborowitz@google.com (Dave Borowitz)'

import os
import time

from google.apputils import file_util
import gflags as flags
from google.apputils import resources
from moe.scrubber import base

FLAGS = flags.FLAGS


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


class FakeFile(object):
  """A fake file object that can be useful in unit tests."""

  def __init__(self, contents=None, filename=None):
    if contents is not None:
      self._contents = contents
      self.filename = filename or ('%d_%f.txt' % (hash(contents), time.time()))
    elif filename is not None:
      self._contents = file_util.Read(filename)
      self.filename = os.path.basename(filename)
    else:
      raise base.Error('at least one of file or contents must be specified')

    self._contents_filename = os.path.join(
        FLAGS.test_tmpdir,
        os.path.basename(self.filename))
    self.new_contents = contents
    self.deleted = False
    self.written = False

  def Contents(self):
    return self._contents.decode('utf-8')

  def ContentsFilename(self):
    file_util.Write(self._contents_filename, self._contents)
    return self._contents_filename

  def WriteContents(self, new_contents):
    self._contents = new_contents
    self.new_contents = new_contents
    self.written = True

  def Delete(self):
    self.deleted = True
