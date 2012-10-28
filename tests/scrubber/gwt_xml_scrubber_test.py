#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.scrubber.gwt_xml_scrubber."""

__author__ = 'arb@google.com (Anthony Baxter)'

from google.apputils import basetest
from moe.scrubber import gwt_xml_scrubber
import test_util


class GwtXmlScrubberTest(basetest.TestCase):

  def setUp(self):
    self.scrubber = gwt_xml_scrubber.GwtXmlScrubber(set(['foo.bar', 'cat.dog']))

  def assertScrubbing(self, contents, expected):
    fake_file = test_util.FakeFile(contents, 'fake_file.gwt.xml')
    self.scrubber.ScrubFile(fake_file, None)
    basetest.DiffTestStrings(expected, fake_file.Contents())

  def testFilesUntouched(self):
    fake_file = test_util.FakeFile('', 'goo.xml')
    self.scrubber.ScrubFile(fake_file, None)
    self.assertFalse(fake_file.written)
    fake_file = test_util.FakeFile('<module></module>')
    self.scrubber.ScrubFile(fake_file, None)
    self.assertFalse(fake_file.written)

  def testScrubbing(self):
    contents = '<module><inherits name="banana.banana"/></module>'
    fake_file = test_util.FakeFile(contents)
    self.scrubber.ScrubFile(fake_file, None)
    self.assertEquals(contents, fake_file.Contents())

  def testScrubbingSomeModulesScrubedSomeLeft(self):
    # A random .gwt.xml with random spaces and newlines note the newline
    # inside a tag.
    self.assertScrubbing('<module>'
                         '<inherits\n'
                         'name="banana.banana"/>'
                         '<inherits name="foo.bar"/>'
                         '</module>',

                         '\n'.join(['<?xml version="1.0" encoding="utf-8"?>',
                                    '<module>',
                                    '  <inherits name="banana.banana"/>',
                                    '</module>',
                                    '']))

  def testScrubbingAllModulesScrubbed(self):
    self.assertScrubbing('<?xml version="1.0"  ?><module>'
                         '<inherits name="foo.bar"/>'
                         '<inherits name="cat.dog"/>'
                         '</module>',
                         '\n'.join(['<?xml version="1.0" encoding="utf-8"?>',
                                    '<module/>',
                                    '']))

if __name__ == '__main__':
  basetest.main()
