#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""A module that classifies sensitive words."""

import re

from google.apputils import stopwatch

from moe.scrubber import base


class SensitiveStringScrubber(base.FileScrubber):
  """Base class for scrubbers that find sensitive strings in files."""

  def ScrubFile(self, file_obj, context):
    """Scrub a file all at once."""
    timer = self._TimerName()
    stopwatch.sw.start(timer)
    sensitive_strings = self.FindSensitiveStrings(file_obj.Contents())
    for w in sensitive_strings:
      # AddError takes care of checking the whitelist, if applicable.
      context.AddError(base.ScrubberError(self.FilterName(), w, '', file_obj))
    stopwatch.sw.stop(timer)

  def _TimerName(self):
    """The name of the stopwatch timer for a specific subclass."""
    return self.FilterName().lower() + 's'

  def FilterName(self):
    """The name of the filter for a specific subclass."""
    raise NotImplementedError


class SensitiveReScrubber(SensitiveStringScrubber):
  """Helper class to find sensitive regular expression matches."""

  def __init__(self, sensitive_res):
    self.sensitive_res = [re.compile(r) for r in sensitive_res]

  def FindSensitiveStrings(self, text):
    result = []
    for sensitive_re in self.sensitive_res:
      result.extend(m.group() for m in sensitive_re.finditer(text))
    return result

  def FilterName(self):
    return 'SENSITIVE_RE'


class SensitiveWordScrubber(SensitiveStringScrubber):
  """Helper class to find sensitive words."""

  def __init__(self, words):
    self.words_re = _GenerateSensitiveWordsRe(words)

  # NB(dbentley): we use a two pass strategy, for speed!
  # 1st, we look for anything that might be an occurrence of a sensitive word.
  # 2nd, we inspect each to see if it's a real usage ("thisIsSecret"),
  # or incidental ("secretes")

  def FindSensitiveStrings(self, text):
    """Determines whether the given text contains a sensitive word.

    Args:
      text: str

    Returns:
      The sensitive word if we find a match, nil otherwise.
    """
    if not self.words_re:
      return []
    hits = self.words_re.finditer(text)
    result = []
    for hit in hits:
      hit_text = hit.group()
      # we consider four cases:
      # 1) not all alphabetic
      # 2) crazy
      # 3) all lower case
      # 4) all upper case
      # 5) initial capital
      # not all alphabetic ('http://GO/') is probably still sensitive.
      # a crazy spelling ('pInto') is probably at a word boundary, so we ignore
      # for each of the rest, we determine whether this is a good word break.
      # if so, we report it as an issue.
      capitalization = DetermineCapitalization(hit_text)
      if capitalization is CRAZY:
        continue
      if capitalization is NON_ALPHA:
        result.append(hit_text.lower())
        continue
      exceptions = EXCEPTIONS[capitalization]
      if IsWord(hit, exceptions):
        result.append(hit_text.lower())
    return result

  def FilterName(self):
    return 'SENSITIVE_WORD'


# NB(dbentley): everything here below is to help with word extraction.
# the strategy is this:
# 1) we determine what the capitalization is. There's upper, lower,
# title, non_alpha (some characters are not letters), and crazy.
# 2) we determine if a match is a word by looking at the characters surrounding
# it. Specifically, the letter before and the letter after. If either of those
# letters matches an exception function, we find that it isn't a word.
# e.g., if the match is all lower case ("secret") and either the character
# before it is also lower case ("a"), then "secret" is *not* a valid word
# (for the purposes of this discussion), because it's a part of "secrete".

# Python pseudo-enum
UPPER = object()
LOWER = object()
TITLE = object()
NON_ALPHA = object()
CRAZY = object()


def DetermineCapitalization(text):
  """Determine the capitalization of text."""
  if not text.isalpha():
    return NON_ALPHA
  if text.islower():
    return LOWER
  if text.isupper():
    return UPPER
  if text.istitle():
    return TITLE
  return CRAZY


# Dictionary<capitalization -> (str->bool, str->bool)> (take that, Haskell)
EXCEPTIONS = {
    UPPER: (unicode.isupper, unicode.isupper),
    LOWER: (unicode.islower, unicode.islower),
    TITLE: (lambda s: False, unicode.islower),
    }


def IsWord(match, exceptions):
  """Determine if a match is a word.

  Args:
    match: re.Match Object
    exceptions: tuple of (str->bool, str->bool), functions that will return true
      if the letter before and after the match (respectively) indicate this
      match is not a word per se but instead part of a larger word.

  Returns:
    True if a match is a word; False otherwise.
  """

  before_exception, after_exception = exceptions
  before_index = match.start() - 1
  if before_index >= 0:
    if before_exception(match.string[before_index]):
      return False
  # NB(dbentley): match.end() is the character after the end already
  after_index = match.end()
  if after_index < len(match.string):
    if after_exception(match.string[after_index]):
      return False

  return True


def _GenerateSensitiveWordsRe(words):
  """Returns the regexp for matching sensitive words.

  Args:
    words: A sequence of strings.

  Returns:
    A pattern object, matching any of the given words. If words is empty,
    returns None.
  """
  if not words:
    return None
  union = []
  for word in words:
    union.append(word)
    union.append(word.capitalize())
    union.append(word.upper())
  return re.compile(u'(%s)' % u'|'.join(union))
