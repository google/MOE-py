#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Smoke test for create_codebase.

This doesn't test the logic of creating. Instead, it tests that create_codebase
can function without exploding.
"""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import os

import gflags as flags

from google.apputils import basetest

from moe import create_codebase
import test_util


FLAGS = flags.FLAGS


CREATE = create_codebase.CreateCodebaseCmd('create_codebase', FLAGS)


class CreateCodebaseTest(basetest.TestCase):
  def setUp(self):
    FLAGS.Reset()

  def RunScenario(self, config_file_name, codebase_expectation):
    # Mock out
    test_util.MockOutDatabase()
    test_util.MockOutMakeRepositoryConfig()

    FLAGS.project_config_file = test_util.TestResourceFilename(
        # We use the same project config as push_codebase_smoke_test
        os.path.join('push_codebase_smoke_test', config_file_name))

    CREATE.Run([])
    self.assertEqual([codebase_expectation], test_util.CREATED_CODEBASES)
    test_util.CREATED_CODEBASES = []

  def testInternal(self):
    FLAGS.source_repository = 'internal'
    self.RunScenario('project_config.txt',
                     ('test_internal', 'head'))

  def testPublic(self):
    FLAGS.source_repository = 'public'
    self.RunScenario('project_config.txt',
                     ('test_public', 'head'))

  def testInternalAtRevision(self):
    FLAGS.source_repository = 'internal'
    FLAGS.source_revision = '1001'
    self.RunScenario('project_config.txt',
                     ('test_internal', '1001'))

  def testPublicAtRevision(self):
    FLAGS.source_repository = 'public'
    FLAGS.source_revision = '1'
    self.RunScenario('project_config.txt',
                     ('test_public', '1'))


if __name__ == '__main__':
  basetest.main()
