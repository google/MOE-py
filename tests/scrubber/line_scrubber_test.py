#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""Sanity check for line_scrubber.py."""

__author__ = ('nicksantos@google.com (Nick Santos)')

from google.apputils import basetest

from moe.scrubber import base
from moe.scrubber import line_scrubber
from moe.scrubber import usernames


class LineScrubberTest(basetest.TestCase):
  """Unittests for the line search."""

  def ScrubPythonAuthor(self, line):
    return line_scrubber.PythonAuthorDeclarationScrubber(
        username_filter=usernames.UsernameFilter(
            publishable_usernames=set(['publishable']))).ScrubLine(line, None)

  def assertAuthor(self, expected, line):
    result = self.ScrubPythonAuthor(line)
    self.assertTrue(isinstance(result, base.Revision),
                    'Expected revision, got %s' % result)
    self.assertEquals(expected, result.new_text)

  def assertNotScrubbed(self, line):
    self.assertEquals(None, self.ScrubPythonAuthor(line))

  def testObviousCases(self):
    self.assertAuthor('', '__author__ = "foo@google.com"')
    self.assertAuthor('',
                      '__author__ = ("foo1@google.com", "foo2@google.com")')
    self.assertNotScrubbed('__author__ = ("publishable@google.com")')

  def testAuthorInString(self):
    self.assertNotScrubbed('\'__author__ = ("nicksantos@google.com")\'')
    self.assertNotScrubbed('"__author__ = (\'nicksantos@google.com\')"')

if __name__ == '__main__':
  basetest.main()
