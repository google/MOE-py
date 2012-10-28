#!/usr/bin/env python
#
# Copyright 2012 Google Inc. All Rights Reserved.

"""Tests for moe.scrubber.replacer."""



from google.apputils import basetest
from moe.scrubber import base
from moe.scrubber import replacer
import test_util


class ReplacerTest(basetest.TestCase):

  def testSucceeds(self):
    subs = [('foo', 'bar'), ('hello', 'goodbye')]
    repl = replacer.ReplacerScrubber(subs)
    fake_file = test_util.FakeFile('hello foo')
    repl.ScrubFile(fake_file, None)
    self.assertEqual('goodbye bar', fake_file.Contents())

  def testNoMatch(self):
    subs = [('blah', 'bar')]
    repl = replacer.ReplacerScrubber(subs)
    fake_file = test_util.FakeFile('hello foo')  # 'blah' not found here
    repl.ScrubFile(fake_file, None)
    self.assertEqual('hello foo', fake_file.Contents())  # No new contents

  def testNoRegex(self):
    subs = [(r'fo*', 'bar')]
    repl = replacer.ReplacerScrubber(subs)
    fake_file = test_util.FakeFile('hello fo*')  # Matches literal 'fo*'
    repl.ScrubFile(fake_file, None)
    self.assertEqual('hello bar', fake_file.Contents())


class RegexReplacerTest(basetest.TestCase):

  def testPlainSucceeds(self):
    subs = [('foo', 'bar'), ('hello', 'goodbye')]
    repl = replacer.RegexReplacerScrubber(subs)
    fake_file = test_util.FakeFile('hello foo')
    repl.ScrubFile(fake_file, None)
    self.assertEqual('goodbye bar', fake_file.Contents())

  def testRegexSucceeds(self):
    subs = [(r'fo{2}', 'bar'), (r'(he)(l)\2o', r'\1\2\2 no')]
    repl = replacer.RegexReplacerScrubber(subs)
    fake_file = test_util.FakeFile('hello foo')
    repl.ScrubFile(fake_file, None)
    self.assertEqual('hell no bar', fake_file.Contents())

  def testNoMatch(self):
    subs = [(r'bl(a)h', 'bar')]
    repl = replacer.RegexReplacerScrubber(subs)
    fake_file = test_util.FakeFile('hello foo')  # r'bl(a)h' not found here
    repl.ScrubFile(fake_file, None)
    self.assertEqual('hello foo', fake_file.Contents())  # No new contents


if __name__ == '__main__':
  basetest.main()
