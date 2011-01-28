#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.codebase_utils."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import gflags as flags

from google.apputils import basetest

from moe import base
from moe import codebase_utils
from moe import moe_app
import test_util

FLAGS = flags.FLAGS

def setUp():
  moe_app.InitForTest()


class CodebaseUtilsTest(basetest.TestCase):

  def testWalk(self):
    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python'})

    codebase = internal_creator.Create('1001')
    self.assertEqual(codebase.Walk(), ['foo.py'])

    codebase2 = codebase_utils.Codebase(
        codebase.ExpandedPath(), additional_files_re='foo.py')
    self.assertEqual(codebase2.Walk(), [])

  def testCreateInProjectSpace(self):
    class MockTranslator(object):
      def FromProjectSpace(self):
        return 'foo'

      def ToProjectSpace(self):
        return 'bar'

      def Translate(self, unused_codebase):
        path = test_util.TestResourceFilename('codebases/modified_python/')
        return codebase_utils.Codebase(path, project_space='bar')

    foo_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python'}, project_space='foo',
        translators=[MockTranslator()])
    created_codebase = foo_creator.CreateInProjectSpace('1001',
                                                        project_space='foo')
    self.assertEqual('foo', created_codebase.ProjectSpace())

    created_codebase = foo_creator.CreateInProjectSpace('1001',
                                                        project_space='bar')
    self.assertEqual('bar', created_codebase.ProjectSpace())

    self.assertRaises(
        base.Error,
        foo_creator.CreateInProjectSpace,
        '1001', project_space='baz')


if __name__ == '__main__':
  basetest.main()
