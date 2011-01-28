#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""A module that implements a whitelist for the scrubber."""


class Whitelist(object):
  """A whitelist allows false positives to be silence."""

  def __init__(self, entries):
    """Create a whitelist.

    Args:
      entries: seq of tuples of (filter, trigger, filename)
    """
    self._entries = entries

  def Allows(self, error):
    """Determine whether this whitelist allows base.ScrubberError error."""

    if isinstance(error, str):
      return False

    # TODO(dbentley): this is linear but could be constant time.
    for filter_name, trigger, filename in self._entries:
      if (error.filter == filter_name and
          error.trigger.lower() == trigger.lower() and
          (filename == '*' or error.file_obj.relative_filename == filename)):
        return True
    return False
