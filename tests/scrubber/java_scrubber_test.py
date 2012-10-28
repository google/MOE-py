#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.scrubber.java_scrubber."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

from google.apputils import basetest
from moe.scrubber import base
from moe.scrubber import java_scrubber
import test_util


class FakeContext(object):
  def __init__(self):
    self.error_added = False

  def AddError(self, *unused_args, **unused_kwargs):
    self.error_added = True


class JavaScrubberTest(basetest.TestCase):
  def assertMeaningful(self, text, filename=None):
    scrubber = java_scrubber.EmptyJavaFileScrubber(base.ACTION_DELETE)
    file_obj = test_util.FakeFile(text, filename)
    scrubber.BatchScrubFiles([file_obj], None)
    if file_obj.deleted:
      self.fail('Text %s is not meaningful, but should be' % text)

  def assertNotMeaningful(self, text, filename=None):
    scrubber = java_scrubber.EmptyJavaFileScrubber(base.ACTION_DELETE)
    file_obj = test_util.FakeFile(text, filename)
    scrubber.BatchScrubFiles([file_obj], None)
    if not file_obj.deleted:
      self.fail('Text %s is not meaningful, but should be' % text)

  def testError(self):
    scrubber = java_scrubber.EmptyJavaFileScrubber(base.ACTION_ERROR)
    fake_file = test_util.FakeFile('')
    fake_context = FakeContext()
    scrubber.BatchScrubFiles([fake_file], fake_context)
    self.assert_(fake_context.error_added, 'ScrubFile did not error')

  def testDelete(self):
    scrubber = java_scrubber.EmptyJavaFileScrubber(base.ACTION_DELETE)
    fake_file = test_util.FakeFile('', 'EmptyFile.java')
    fake_context = FakeContext()
    scrubber.BatchScrubFiles([fake_file], fake_context)
    self.assert_(fake_file.deleted, 'ScrubFile did not delete')

  def testRaises(self):
    scrubber = java_scrubber.EmptyJavaFileScrubber(base.ACTION_IGNORE)
    fake_file = test_util.FakeFile('', 'EmptyFile.java')
    fake_context = FakeContext()
    self.assertRaises(base.Error,
                      scrubber.BatchScrubFiles,
                      [fake_file], fake_context)

  def testBatch(self):
    scrubber = java_scrubber.EmptyJavaFileScrubber(base.ACTION_DELETE)
    empty_file = test_util.FakeFile('', 'EmptyFile.java')
    nonempty_file = test_util.FakeFile('public class Foo {}', 'Foo.java')
    fake_context = FakeContext()
    scrubber.BatchScrubFiles([empty_file, nonempty_file], fake_context)
    self.assert_(empty_file.deleted, 'ScrubFile did not delete empty file')
    self.assert_(not nonempty_file.deleted, 'ScrubFile deleted non-empty file')

  def testJavaMeaningfulness(self):
    self.assertMeaningful('public class Foo;')
    self.assertMeaningful('public interface Foo;')
    self.assertMeaningful('public static func()')
    self.assertMeaningful('class Bar; package com.google.foo')
    self.assertMeaningful(' "String Constant"; ')
    self.assertMeaningful(
        '// comment\npackage foo;\n public class Bar {}\nimport f;')

    self.assertNotMeaningful('/* class Foo */')
    self.assertNotMeaningful('')
    self.assertNotMeaningful('package com.google.foo;')
    self.assertNotMeaningful('import com.google.foo;')
    self.assertNotMeaningful(
        '// comment\npackage foo;\n \nimport f;')
    self.assertNotMeaningful('\n\n\n\n\t\t\n  \n')

  def testPackageInfo(self):
    self.assertMeaningful('', 'foo/package-info.java')


class CoalesceBlankLinesScrubberTest(basetest.TestCase):
  def assertCoalesces(self, original, expected=None, maximum_blank_lines=1):
    scrubber = java_scrubber.CoalesceBlankLinesScrubber(maximum_blank_lines)

    if not expected:
      expected = original

    fake_file = test_util.FakeFile(original)
    scrubber.ScrubFile(fake_file, None)
    self.assertMultiLineEqual(expected, fake_file.Contents())

  def testCoalesceBlankLines(self):
    for i in xrange(2, 10):
      self.assertCoalesces('\n' * i, '\n\n')
    self.assertCoalesces('class Foo {\n}')
    self.assertCoalesces('\n\n')
    self.assertCoalesces('\n')
    self.assertCoalesces('"\\n" +\n"\\n"')
    for i in xrange(2, 10):
      self.assertCoalesces(
          'first line%ssecond' % ('\n' * i),
          'first line\n\nsecond')

    for i in xrange(3, 10):
      self.assertCoalesces('\n' * i, '\n\n\n', maximum_blank_lines=2)
      self.assertCoalesces(
          'first line%ssecond' % ('\n' * i),
          'first line\n\n\nsecond', maximum_blank_lines=2)


class TestSizeAnnotationScrubberTest(basetest.TestCase):
  def setUp(self):
    self.scrubber = java_scrubber.TestSizeAnnotationScrubber()

  def assertTestSizeScrubbed(self, original, expected=None):
    if expected is None:
      expected = original

    fake_file = test_util.FakeFile(original)
    self.scrubber.ScrubFile(fake_file, None)
    self.assertMultiLineEqual(expected, fake_file.Contents())

  def testScrubTestSizes(self):
    self.assertTestSizeScrubbed('class Foo {\n  public void testFoo {\n  }\n}')
    self.assertTestSizeScrubbed(
        '@Sequential\nclass Foo {\n  public void testFoo {\n  }\n}',
        '\nclass Foo {\n  public void testFoo {\n  }\n}')
    self.assertTestSizeScrubbed(
        '@Sequential\nclass Foo {\n  public void testFoo {\n  }\n}',
        '\nclass Foo {\n  public void testFoo {\n  }\n}')
    self.assertTestSizeScrubbed(
        'class Foo {\n  @SmallTest\n  public void testFoo {\n  }\n}',
        'class Foo {\n\n  public void testFoo {\n  }\n}')
    self.assertTestSizeScrubbed(
        'class Foo {\n  @MediumTest\n  public void testFoo {\n  }\n}',
        'class Foo {\n\n  public void testFoo {\n  }\n}')
    self.assertTestSizeScrubbed(
        'class Foo {\n  @MediumTest(banana)\n  public void testFoo {\n  }\n}',
        'class Foo {\n\n  public void testFoo {\n  }\n}')
    self.assertTestSizeScrubbed(
        'class Foo {\n  @LargeTest\n  public void testFoo {\n  }\n}',
        'class Foo {\n\n  public void testFoo {\n  }\n}')
    self.assertTestSizeScrubbed(
        'class Foo {\n  @LargeTest(foo=bar)\n  public void testFoo {\n  }\n}',
        'class Foo {\n\n  public void testFoo {\n  }\n}')
    self.assertTestSizeScrubbed(
        'class Foo {\n  @Test\n  public void testFoo {\n  }\n}',
        'class Foo {\n  @Test\n  public void testFoo {\n  }\n}')


class JavaRenameTest(basetest.TestCase):

  def assertNotScrubbed(self, text, internal_package, public_package,
                        filename=''):
    scrubber = java_scrubber.JavaRenameScrubber(internal_package,
                                                public_package)
    f = test_util.FakeFile(text, filename)
    scrubber.ScrubFile(f, None)
    if f.Contents() != text:
      self.fail("Text %s was scrubbed, but shouldn't be" % text)

  def assertScrubbed(self, expected, text, internal_package, public_package,
                     filename=''):
    scrubber = java_scrubber.JavaRenameScrubber(internal_package,
                                                public_package)
    f = test_util.FakeFile(text, filename)
    scrubber.ScrubFile(f, None)
    if f.Contents() == text:
      self.fail("Text %s was not scrubbed, but should've been" % text)

    self.assertEqual(expected, f.Contents())

  def testRename(self):
    self.assertNotScrubbed('com.google.bar',
                           'com.google.foo', 'com.public.foo')
    self.assertScrubbed('com.public.foo', 'com.google.foo',
                        'com.google.foo', 'com.public.foo')
    self.assertScrubbed('/com/public/foo', '/com/google/foo',
                        'com.google.foo', 'com.public.foo')

    # TODO(dbentley): is this really the right behavior?
    self.assertScrubbed('com.public.foobar', 'com.google.foobar',
                        'com.google.foo', 'com.public.foo')


if __name__ == '__main__':
  basetest.main()
