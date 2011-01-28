#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""Scrubbers that go line-by-line, without any understanding of language."""

__author__ = 'dbentley@google.com (Dan Bentley)'

import re

import logging
from google.apputils import stopwatch

from moe.scrubber import base
from moe.scrubber import usernames


class LineScrubber(base.FileScrubber):
  """A LineScrubber scans a file line-by-line.

  For each line, it can call multiple LineOrientedScrubber's.
  """

  def __init__(self, scrubbers):
    """Initialize.

    Args:
      scrubbers: seq of LineScrubber, scrubbers to use
    """
    self._line_scrubbers = scrubbers

  def ScrubFile(self, file_obj, context):
    """Scrub a file by scrubbing each line."""
    stopwatch.sw.start('line_scrubber')
    for line in file_obj.Contents().split('\n'):
      self._ScrubLine(line, file_obj, context)
    stopwatch.sw.stop('line_scrubber')

  def _ScrubLine(self, line, file_obj, context):
    """Scrub one line fully."""
    revisions = []
    original_line = line
    for scrubber in self._line_scrubbers:
      result = scrubber.ScrubLine(line, file_obj)
      if isinstance(result, base.ScrubberError):
        context.AddError(result)
      if isinstance(result, base.Revision):
        revision = result
        line = revision.new_text
        revisions.append(revision)
        # stop going through the scrubbers. besides the fact that we're
        # removing the line anyway, string ops in future ScrubLine() calls
        # would fail on a NoneType.
        if line is None:
          break

    if revisions:
      # None means remove the entire line, not just its contents.
      # empty string '' will remove the contents and leave the "\n"
      if line is None:
        file_obj.RewriteContent('%s\n' % original_line, '')
      else:
        file_obj.RewriteContent(original_line, line)
      logging.debug('Rewriting comment %s in %s because: %s',
                    original_line, file_obj.filename,
                    ','.join([r.reason for r in revisions]))


# TODO(dbentley): this interface might be at the root of performance problems.
# Maybe instead it should have a method that returns a regular expression.
# The framework then searches for that regex in the file, and only if there's
# a hit will it call ScrubLine. This way, in the common case, there's no
# function called per line.
class LineOrientedScrubber(object):
  """Interface for scrubbing one line at a time."""

  def ScrubLine(self, line, file_obj):
    """Scrub line, returning None, a base.Revision, or a base.ScrubberError."""
    raise NotImplementedError


class PythonAuthorDeclarationScrubber(LineOrientedScrubber):
  """A scrubber of Python __author__ declaration lines."""

  def __init__(self, username_filter=None):
    LineOrientedScrubber.__init__(self)
    self._email_address_filter = usernames.EmailAddressFilter(username_filter)

  AUTHOR_RE = re.compile((r'^__author__\s+=\s+'
                          r'\(?[\'\"](.*)[\'\"]\)?$'), re.M)

  def ScrubLine(self, line, unused_file_obj):
    """Scrub author declaration from a single line."""
    author = self.AUTHOR_RE.search(line)
    if author:
      new_text = self.AUTHOR_RE.sub('', line)
      if self._email_address_filter.CanPublish(author.group(1)):
        return
      return base.Revision(
          new_text,
          'Scrubbing __author__')


class JsDirectoryRename(LineOrientedScrubber):
  """Scrubs module names in javascript.

  When we open source closure, we change javascript/closure to closure/goog.
  """

  def __init__(self, internal_directory, public_directory):
    LineOrientedScrubber.__init__(self)
    self._internal_directory = internal_directory
    self._public_directory = public_directory

  def ScrubLine(self, line, unused_file_obj):
    if self._internal_directory not in line:
      return

    new_text = line.replace(self._internal_directory, self._public_directory)
    return base.Revision(new_text, 'Rename javascript directory %s to %s' % (
        self._internal_directory, self._public_directory))
