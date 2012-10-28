#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""Common functions, classes, et cetera."""

__author__ = 'dbentley@google.com (Dan Bentley)'


import errno
import os
import re

import gflags as flags

# As this module imports no other scrubber module, put scrubber-wide flags here
FLAGS = flags.FLAGS
flags.DEFINE_string('java', os.getenv('JAVA') or 'java',
                    'Path to java command.')

# Constants for actions to apply on scrubbed objects.
ACTION_IGNORE = 'action_ignore'
ACTION_DELETE = 'action_delete'
ACTION_ERROR = 'action_error'


def ResourceName(name):
  """Get the resource name for a name relative to __file__.

  Args:
    name: str, the resource name, relative to this module.

  Returns:
    A resource name suitable for passing to e.g. resources.GetResource().
  """
  prefix = __name__ + ':/'
  return prefix + name


class ScrubberError(object):
  """An error that means the Scrubber found confidential but unscrubbable code.

  This is not an exception, but instead a failure of the scrubber. It should be
  remembered, but execution should continue.
  """

  def __init__(self, filter_name, trigger, reason, file_obj):
    """Initialize a ScrubberError.

    Args:
      filter_name: str, the name of the filter that created this error
      trigger: str, the name of the trigger that created this error
      reason: str, an explanation of the error
      file_obj: ScannedFile, the file this error was found in
    """
    self.filter = filter_name
    self.trigger = trigger
    self.reason = reason
    self.file_obj = file_obj

  def ReportText(self):
    """The text that should be included in a report of this run."""
    return 'Error in %s: %s' % (self.file_obj.filename,
                                self.reason)


class Revision(object):
  """A revision should be made for a reason."""

  def __init__(self, new_text, reason):
    self.new_text = new_text
    self.reason = reason


class FileScrubber(object):
  """A scrubber that operates on a file.

  Other scrubbers implement this interface, and then can provide their own,
  more specific interface. (E.g. CommentOrientedScrubber finds the comments;
  FilenameOrientedScrubber is for scrubbing that should happen based on
  filenames).
  """

  def ScrubFile(self, file_obj, context):
    """Scrub file_obj in context.

    Args:
      file_obj: ScannedFile, the file to scrub
      context: ScrubberContext, the context to evaluate it in
    """
    raise NotImplementedError


class BatchFileScrubber(object):
  """A scrubber that operates on a list of files, for efficiency reasons."""

  def BatchScrubFiles(self, file_objs, context):
    """Scrub file_objs in context.

    Args:
      file_objs: list(ScannedFile), the files to scrub
      context: ScrubberContext, the context to evaluate it in
    """
    raise NotImplementedError


class RegexScrubber(FileScrubber):
  """A scrubber that replaces matching regexes with a replacement."""

  def __init__(self, subs):
    """Initialize.

    Args:
      subs: seq of (regexable, str). The substitutions to make. The first
            element of the tuple is either a regex or a string. The second is
            the string to replace occurrences of the regex with.
    """
    FileScrubber.__init__(self)
    self._subs = [(re.compile(regex), repl) for (regex, repl) in subs]

  def ScrubFile(self, file_obj, context):
    """Scrub file_obj in context.

    Args:
      file_obj: ScannedFile, the file to scrub
      context: ScrubberContext, the context to evaluate it in
    """
    original_contents = file_obj.Contents()
    contents = original_contents
    for (regex, replacement) in self._subs:
      contents = regex.sub(replacement, contents)
    if contents != original_contents:
      file_obj.WriteContents(contents)


def MakeDirs(d):
  """Make directory 'd' exist."""
  try:
    os.makedirs(d)
  except OSError, e:
    if e.errno != errno.EEXIST:
      raise


class Error(Exception):
  """An Error.

  This is different from ScrubberError. ScrubberError is for when the
  code is not scrubbable. Error is for when the scrubber is confused.

  This is at the bottom of this file so as not to confuse the reader.
  """
  pass
