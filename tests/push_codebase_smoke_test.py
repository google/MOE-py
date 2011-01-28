#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Smoke test for push_codebase.

This doesn't test the logic of pushing. Instead, it tests that push_codebase
can function as a binary without exploding.
"""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import os

import gflags as flags

from google.apputils import basetest

from moe import push_codebase
import test_util


FLAGS = flags.FLAGS


def setUp():
  FLAGS.Reset()
  push_codebase.DefineFlags(FLAGS)


def tearDown():
  FLAGS.Reset()


class PushCodebaseSmokeTest(basetest.TestCase):
  def RunScenario(self, config_file_name, codebase_expectations,
                  editor_expectations):
    # Mock out
    test_util.MockOutDatabase()
    test_util.MockOutMakeRepositoryConfig()

    FLAGS.project_config_file = test_util.TestResourceFilename(
        os.path.join('push_codebase_smoke_test', config_file_name))

    test_util.MockOutPusher(self,
                            codebase_expectations,
                            editor_expectations)

    push_codebase.main([])

  def testImport(self):
    FLAGS.Reset()
    FLAGS.destination = 'internal'
    self.RunScenario('project_config.txt',
                     ('test_public', 'head'),
                     ('test_internal', 'head'))

  def testExport(self):
    FLAGS.Reset()
    FLAGS.destination = 'public'
    self.RunScenario('project_config.txt',
                     ('test_internal', 'head'),
                     ('test_public', 'head'))

  def testImportAtRevision(self):
    FLAGS.Reset()
    FLAGS.destination = 'internal'
    FLAGS.destination_revision = '1001'
    self.RunScenario('project_config.txt',
                     ('test_public', 'head'),
                     ('test_internal', '1001'))

  def testExportFromRevision(self):
    FLAGS.Reset()
    FLAGS.destination = 'public'
    FLAGS.source_revision = '1001'
    self.RunScenario('project_config.txt',
                     ('test_internal', '1001'),
                     ('test_public', 'head'))


if __name__ == '__main__':
  basetest.main()
