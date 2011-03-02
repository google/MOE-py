#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.

"""String replacement scrubbers."""

__author__ = 'dbentley@google.com'

import re

from moe.scrubber import base


class ReplacerScrubber(base.FileScrubber):
  """Scrubber that replaces constant strings with other constant strings."""

  def __init__(self, subs):
    base.FileScrubber.__init__(self)

    self._re_scrubber = base.RegexScrubber([
        (re.escape(o), r) for (o, r) in subs])

  def ScrubFile(self, file_obj, context):
    self._re_scrubber.ScrubFile(file_obj, context)


# TODO(dbentley): expose some sort of reg-ex based scrubbing.
# What is the downside to this?
# It will be nice for the scrubber to be reversible.
# As an example: let's say that what's referred to as vector internally
# should be std::vector publicly. When we undo scrubbing, any instances
# of vector that were previously scrubbed to std::vector can be undone. But
# new instances of std::vector in the public cannot be unscrubbed to vector.
# This means new public code can lead to compile errors internally.
# The solution is to use a reversible scrubber. Thus, when you specify
# that internal vector should be scrubbed to std::vector, you're also telling
# the scrubber that public std::vector should be scrubbed to vector.
# But it's impossible to reverse scrubbing, e.g., codeword([a-z]*) -> \1 .
