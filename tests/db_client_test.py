#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Unit test for db_client.py's client-side functions.

This does not send anything over the wire.
"""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import os

from mox import stubout

import gflags as flags
from google.apputils import basetest

from moe import base
from moe import config
from moe import config_utils
from moe import db_client
import test_util

FLAGS = flags.FLAGS


class MockDbClient(object):
  def __init__(self, project, record_process=True, url=None):
    pass


class DbClientTest(basetest.TestCase):
  def setUp(self):
    FLAGS.Reset()
    self.stubs = stubout.StubOutForTesting()
    self.stubs.Set(db_client, '_Get', None)
    self.stubs.Set(db_client, '_Post', None)
    self.config_file_path = test_util.TestResourceFilename(
        'db_client/project_config.txt')
    self.name = 'foo'
    db_client.ServerBackedMoeDbClient = MockDbClient
    db_client.GetStoredProject = self._GetStoredProject
    test_util.MockOutMakeRepositoryConfig()

  def _AcceptPost(self, url, method, *unused_args, **unused_kwargs):
    pass

  def AllowPost(self):
    self.stubs.Set(db_client, '_Post', self._AcceptPost)

  def _GetStoredProject(self, unused_url, project_name):
    if project_name == 'foo':
      result = config.MoeProject('foo')
      result.filename = 'foo/moe_config.txt'
      return result
    return None

  def assertSucceeds(self, create_project=False):
    (project, db) = db_client.MakeProjectAndDbClient(
        create_project=create_project)
    self.assertEqual(type(project), config.MoeProject)
    self.assertEqual(type(db), MockDbClient)

  def testNoArgs(self):
    self.assertRaisesWithRegexpMatch(
        base.Error,
        'Must specify at least one of --project or --project_config_file',
        db_client.MakeProjectAndDbClient)

  def testConfigFileOnly(self):
    FLAGS.project_config_file = self.config_file_path
    self.AllowPost()
    self.assertSucceeds()

  def testIncompatibleNames(self):
    FLAGS.project_config_file = self.config_file_path
    FLAGS.project = 'bar'  # conflict
    self.assertRaisesWithRegexpMatch(
        base.Error,
        'Name "bar" from --project and name "foo" from config differ',
        db_client.MakeProjectAndDbClient)

  def testCompatibleNames(self):
    FLAGS.project_config_file = self.config_file_path
    FLAGS.project = self.name
    self.AllowPost()
    self.assertSucceeds()

  def testNameOnly(self):
    FLAGS.project = self.name
    config_utils.MakeConfigFilenameAbsolute = lambda s: self.config_file_path
    self.AllowPost()
    self.assertSucceeds()

  def testNonexistent(self):
    FLAGS.project = 'bar'
    self.assertRaisesWithRegexpMatch(
        base.Error,
        'does not exist',
        db_client.MakeProjectAndDbClient)

  def testNonExistentButCreate(self):
    self.AllowPost()

    FLAGS.project_config_file = test_util.TestResourceFilename(
        'db_client/bar_project_config.txt')
    self.assertSucceeds(create_project=True)

if __name__ == '__main__':
  basetest.main()
