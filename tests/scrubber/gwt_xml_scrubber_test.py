#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.scrubber.gwt_xml_scrubber."""

__author__ = 'arb@google.com (Anthony Baxter)'

from google.apputils import basetest
from moe.scrubber import gwt_xml_scrubber


class FakeFileObj(object):
  def __init__(self, contents, filename='foo.gwt.xml'):
    self._contents = contents
    self.filename = filename
    self.deleted = False
    self.written = False

  def Contents(self):
    return self._contents

  def ContentsFilename(self):
    return self.filename

  def WriteContents(self, new_contents):
    self._contents = new_contents
    self.written = True

  def Delete(self):
    self.deleted = True


class GwtXmlScrubberTest(basetest.TestCase):

  def setUp(self):
    self.scrubber = gwt_xml_scrubber.GwtXmlScrubber(set(['foo.bar', 'cat.dog']))

  def assertScrubbing(self, contents, expected):
    fake_file = FakeFileObj(contents)
    self.scrubber.ScrubFile(fake_file, None)
    basetest.DiffTestStrings(expected, fake_file.Contents())

  def testFilesUntouched(self):
    fake_file = FakeFileObj('', 'goo.xml')
    self.scrubber.ScrubFile(fake_file, None)
    self.assertFalse(fake_file.written)
    fake_file = FakeFileObj('<module></module>')
    self.scrubber.ScrubFile(fake_file, None)
    self.assertFalse(fake_file.written)

  def testScrubbing(self):
    contents = '<module><inherits name="banana.banana"/></module>'
    fake_file = FakeFileObj(contents)
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

  def testScrubbingAllModulesScrubed(self):
    self.assertScrubbing('<?xml version="1.0"  ?><module>'
                         '<inherits name="foo.bar"/>'
                         '<inherits name="cat.dog"/>'
                         '</module>',
                         '\n'.join(['<?xml version="1.0" encoding="utf-8"?>',
                                    '<module/>',
                                    '']))

if __name__ == '__main__':
  basetest.main()
