#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.
#

"""Tests for python_scrubber module."""



import os

from google.apputils import basetest

from moe.scrubber import base
from moe.scrubber import python_scrubber


class FakeScannedFile(object):
  def __init__(self, f=None, contents=''):
    if f:
      self._contents = open(file).read()
      self._contents_filename = os.path.basename(file)
      self.filename = os.path.basename(file)
    elif contents:
      self._contents = contents
      self._contents_filename = 'not specified'
      self.filename = 'not specified'
    else:
      raise base.Error('at least one of file or contents must be specified')
    self.new_contents = contents

  def Contents(self):
    return self._contents

  def ContentsFilename(self):
    return self._contents_filename

  def WriteContents(self, new_contents):
    self.new_contents = new_contents


class PythonScrubberModuleTest(basetest.TestCase):
  """Test module level functions."""

  def testParseImportLine(self):
    """Test ParseImportLine()."""

    lines = [
        'from a import b',
        'import a.b',
        '  import a.b',
        'other python line',
        'string ending with import hello',
        'from a import b as c',
        'import a as b',
        'import a.b as c',
    ]

    expect = [
        ('from', 'a.b', '', ''),
        ('import', 'a.b', '', ''),
        ('import', 'a.b', '  ', ''),
        None,
        None,
        ('from', 'a.b', '', ' as c'),
        ('import', 'a', '', ' as b'),
        ('import', 'a.b', '', ' as c'),
    ]

    for n in xrange(len(lines)):
      result = python_scrubber.ParseImportLine(lines[n])
      self.assertEqual(
          result, expect[n],
          'Error parsing: "' + lines[n] +
          '" expecting ' + repr(expect[n]) + ' but got ' + repr(result))


class PythonScrubTest(basetest.TestCase):
  def assertScrubbed(self, imr, line, new_text=None):
    """Assert a line was scrubbed.

    Args:
      imr: line scrubber class
      line: string line to scrub
      new_text: optional, expected scrubbed output
    """
    result = imr.ScrubLine(line, None)
    self.assertTrue(result is not None, line)
    self.assertTrue(isinstance(result, base.Revision))
    if new_text is None:
      self.assertTrue(result.new_text is new_text)
    else:
      self.assertEqual(result.new_text, new_text)

  def assertNotScrubbed(self, imr, line):
    """Assert that a line has not been scrubbed.

    Args:
      imr: line scrubber class
      line: string line to scrub
    """
    result = imr.ScrubLine(line, None)
    if result is not None:
      helper_text = 'Reason: %s, New text: %s' % (result.reason,
                                                  result.new_text)
    else:
      helper_text = ''
    self.assertTrue(result is None, helper_text)


class PythonModuleRemoveTest(PythonScrubTest):
  """Test PythonModuleRemove()."""

  def testNormal(self):
    imr = python_scrubber.PythonModuleRemove('a.b.c')

    self.assertNotScrubbed(imr, 'non-import python line with import in it')
    self.assertNotScrubbed(imr, 'from a.b import z')
    self.assertNotScrubbed(imr, '    from a.b import z')

    self.assertScrubbed(imr, 'import a.b.c')
    self.assertScrubbed(imr, 'from a.b import c')
    self.assertScrubbed(imr, '    from a.b import c')


class PythonModuleRenameTest(PythonScrubTest):
  """Test PythonModuleRename()."""

  def testNormal(self):
    imr = python_scrubber.PythonModuleRename('private.mod', 'publicmod')

    self.assertNotScrubbed(imr, 'non-import python line with import in it')
    self.assertNotScrubbed(imr, '# comment import hello')
    self.assertNotScrubbed(imr, 'from othermod import somemod')
    self.assertNotScrubbed(imr, '    from othermod import somemod')

    self.assertScrubbed(imr, 'import private.mod', 'import publicmod')
    self.assertScrubbed(imr, '  import private.mod', '  import publicmod')
    self.assertScrubbed(
        imr, 'from private import mod as bar', 'import publicmod as bar')
    self.assertScrubbed(
        imr, 'from private.mod import mod2', 'from publicmod import mod2')
    self.assertScrubbed(
        imr, 'from private.mod import mod2 as bar',
        'from publicmod import mod2 as bar')
    self.assertScrubbed(
        imr, 'foo = private.mod.Class()', 'foo = publicmod.Class()')

  def testCorrectSubstringReplacement(self):
    imr = python_scrubber.PythonModuleRename('a', 'b')

    self.assertScrubbed(imr, 'import a', 'import b')
    self.assertNotScrubbed(imr, 'import abc')
    self.assertNotScrubbed(imr, 'abcd')

  def testImportToFrom(self):
    imr = python_scrubber.PythonModuleRename('private', 'public.mod.submod')

    self.assertScrubbed(imr, 'import private',
                        'from public.mod import submod')
    self.assertScrubbed(imr, 'from private import foo',
                        'from public.mod.submod import foo')
    self.assertScrubbed(imr, 'from private.foo import bar',
                        'from public.mod.submod.foo import bar')

    self.assertScrubbed(
        imr, 'foo = private.class()', 'foo = submod.class()')

    imr = python_scrubber.PythonModuleRename('private', 'public')

    self.assertScrubbed(imr, 'import private',
                        'import public')
    self.assertScrubbed(imr, 'from private import foo',
                        'from public import foo')
    self.assertScrubbed(imr, 'from private import foo as bar',
                        'from public import foo as bar')
    self.assertScrubbed(
        imr, 'foo = private.class()', 'foo = public.class()')
    self.assertScrubbed(
        imr, 'import private.foo', 'import public.foo')
    self.assertNotScrubbed(
        imr, 'from mycompany import private')

  def testAsName(self):
    imr = python_scrubber.PythonModuleRename('private.mod', 'public.gmod',
                                             as_name='mod')
    self.assertScrubbed(imr, 'from private import mod',
                        'from public import gmod as mod')

    # Doesn't affect 'import' with a submodule.
    self.assertScrubbed(imr, 'import private.mod', 'import public.gmod as mod')

    # Doesn't override an existing 'as'.
    self.assertScrubbed(imr, 'from private import mod as something',
                        'from public import gmod as something')
    # This could be 'from public import gmod as something', but this is just as
    # good because of the 'as'.
    self.assertScrubbed(imr, 'import private.mod as something',
                        'import public.gmod as something')

  def testAsNameSame(self):
    imr = python_scrubber.PythonModuleRename('private.mod', 'mod',
                                             as_name='mod')

    # Don't do "import mod as mod", collapse to just "import mod"
    self.assertScrubbed(imr, 'import private.mod as mod',
                        'import mod')


class PythonShebangReplaceTest(basetest.TestCase):

  def assertScrubbed(self, scrubber, original_text, expected_text):
    f = FakeScannedFile(contents=original_text)
    scrubber.ScrubFile(f, None)
    self.assertEqual(expected_text, f.new_contents)

  def testSmoke(self):
    scrubber = python_scrubber.PythonShebangReplace('#!/usr/env python')

    self.assertScrubbed(
        scrubber,
        'test\ntest',
        '#!/usr/env python\ntest\ntest')

    self.assertScrubbed(
        scrubber,
        '#!/python\ntest\ntest',
        '#!/usr/env python\ntest\ntest')


if __name__ == '__main__':
  basetest.main()
