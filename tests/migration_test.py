#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.migration."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import gflags as flags
from google.apputils import basetest

from moe import actions
from moe import base
from moe import db_client
from moe import moe_app
from moe import push_codebase
import test_util

FLAGS = flags.FLAGS


def setUp():
  moe_app.InitForTest()


class MigrationTest(basetest.TestCase):

  def testNothingToExport(self):
    project = test_util.EmptyMoeProject()

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python',
         '1002': 'simple_python'})

    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'simple_python'})

    config = actions.MigrationConfig(base.Migration.EXPORT,
                                     internal_creator,
                                     project.internal_repository,
                                     public_creator,
                                     project.public_repository,
                                     project.export_strategy)
    revisions = [ base.Revision('1002') ]
    export = actions.Migration(base.Revision('1001'),
                               base.Revision('1'),
                               revisions,
                               project,
                               config, False, -1)

    result = export.Perform()
    self.assertEqual(result, None)

  def testNothingToImport(self):
    project = test_util.EmptyMoeProject()

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python'})

    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'simple_python',
         '2': 'simple_python'})

    config = actions.MigrationConfig(base.Migration.IMPORT,
                                     public_creator,
                                     project.public_repository,
                                     internal_creator,
                                     project.internal_repository,
                                     project.import_strategy)
    revisions = [ base.Revision('2') ]
    action = actions.Migration(
        base.Revision('1'), base.Revision('1001'),
        revisions, project, config, False, -1)

    result = action.Perform()
    self.assertEqual(result, None)

  def testSingleExportPending(self):
    mock_db = test_util.MockDbClient(migration_id_seed=88)
    mock_editor = test_util.MockEditor()
    mock_client = test_util.MockClient(
      lambda migration_strategy, revisions: mock_editor)
    project = test_util.EmptyMoeProject()

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python',
         '1002': 'simple_python2'})

    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'simple_python'},
        lambda: mock_client)

    config = actions.MigrationConfig(base.Migration.EXPORT,
                                     internal_creator,
                                     project.internal_repository,
                                     public_creator,
                                     project.public_repository,
                                     project.export_strategy)
    revisions = [ base.Revision('1002', changelog='log') ]
    action = actions.Migration(
        base.Revision('1001'), base.Revision('1'),
        revisions, project, config, False, -1)

    result = action.Perform(db=mock_db)
    self.assertFalse(result)

    expected = base.Migration(
        migration_id='88',
        direction=base.Migration.EXPORT,
        status=base.Migration.ACTIVE,
        up_to_revision=base.Revision('1002'),
        changelog='log',
        revisions=revisions)
    self.assertEqual(expected.Dict(), mock_db.GetMigration('88').Dict())

  def testSingleExportCommit(self):
    mock_db = test_util.MockDbClient(migration_id_seed=88)
    mock_editor = test_util.MockEditor(commit_id='2')
    mock_client = test_util.MockClient(
      lambda migration_strategy, revisions: mock_editor)
    report = base.MoeReport()
    project = test_util.EmptyMoeProject()
    project.public_repository = test_util.MockRepositoryConfig('',
        repository=test_util.MockRepository(''))

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python',
         '1002': 'simple_python2'})

    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'simple_python'},
         lambda: mock_client)

    config = actions.MigrationConfig(base.Migration.EXPORT,
                                     internal_creator,
                                     project.internal_repository,
                                     public_creator,
                                     project.public_repository,
                                     project.export_strategy)
    revisions = [ base.Revision('1002', changelog='log') ]
    action = actions.Migration(
        base.Revision('1001'), base.Revision('1'),
        revisions, project, config, False, -1)

    result = action.Perform(db=mock_db)
    equivalence_check = result.actions[0]
    self.assertEqual(equivalence_check.internal_revision, '1002')
    self.assertEqual(equivalence_check.public_revision, '2')
    self.assertFalse(result.actions[1:])
    self.assertTrue(mock_editor.ChangesMade())

    expected = base.Migration(
        migration_id='88',
        direction=base.Migration.EXPORT,
        status=base.Migration.SUBMITTED,
        up_to_revision=base.Revision('1002'),
        revisions=revisions,
        submitted_as=base.Revision('2'),
        changelog='log',
        )
    self.assertEqual(mock_db.GetMigration('88').Dict(), expected.Dict())

  def testSingleImport(self):
    mock_db = test_util.MockDbClient(migration_id_seed=88)
    mock_editor = test_util.MockEditor()
    mock_client = test_util.MockClient(
      lambda migration_strategy, revisions: mock_editor)
    project = test_util.EmptyMoeProject()

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python'},
        lambda: mock_client)

    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'simple_python',
         '2': 'simple_python2'})

    config = actions.MigrationConfig(base.Migration.IMPORT,
                                     public_creator,
                                     project.public_repository,
                                     internal_creator,
                                     project.internal_repository,
                                     project.import_strategy)
    revisions = [ base.Revision('2', changelog='log') ]
    action = actions.Migration(
        base.Revision('1'), base.Revision('1001'),
        revisions, project, config, False, -1)

    result = action.Perform(db=mock_db)
    self.assertFalse(result)
    self.assertTrue(mock_editor.ChangesMade())

    expected = base.Migration(
        migration_id='88',
        direction=base.Migration.IMPORT,
        status=base.Migration.ACTIVE,
        up_to_revision=base.Revision('2'),
        changelog='log',
        revisions=revisions)
    self.assertEqual(mock_db.GetMigration('88').Dict(), expected.Dict())

  def testSkipsBrokenCodebase(self):
    mock_db = test_util.MockDbClient(migration_id_seed=88)
    mock_editor = test_util.MockEditor()
    mock_client = test_util.MockClient(
      lambda migration_strategy, revisions: mock_editor)
    project = test_util.EmptyMoeProject()

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python',
         '1002': None,
         '1003': 'simple_python2',
        },
        lambda: mock_client)

    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'simple_python'})

    config = actions.MigrationConfig(base.Migration.EXPORT,
                                     internal_creator,
                                     project.internal_repository,
                                     public_creator,
                                     project.export_strategy,
                                     project.public_repository)
    revisions = [ base.Revision('1002', changelog='1002'),
                  base.Revision('1003', changelog='1003')]
    action = actions.Migration(
        base.Revision('1001'), base.Revision('1'),
        revisions, project, config, False, 1)

    result = action.Perform(db=mock_db)
    migration = result.actions[0]
    migrated_revisions = migration.revisions
    # because we couldn't migrate 1002 on its own, we now want to migrate
    # 1002 *and* 1003
    self.assertEqual(len(migrated_revisions), 2)
    self.assertEqual(migrated_revisions[0].rev_id, '1002')
    self.assertEqual(migrated_revisions[1].rev_id, '1003')

  def testErrorsOnLastBrokenCodebase(self):
    mock_db = test_util.MockDbClient(migration_id_seed=88)
    mock_editor = test_util.MockEditor()
    mock_client = test_util.MockClient(
      lambda migration_strategy, revisions: mock_editor)
    report = base.MoeReport()
    project = test_util.EmptyMoeProject()

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python',
         '1002': None,
        },
        lambda: mock_client)

    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'simple_python'})

    config = actions.MigrationConfig(base.Migration.EXPORT,
                                     internal_creator,
                                     project.internal_repository,
                                     public_creator,
                                     project.public_repository,
                                     project.export_strategy)
    revisions = [ base.Revision('1002', changelog='1002')]
    action = actions.Migration(
        base.Revision('1001'),
        base.Revision('1'),
        revisions, project, config, False, 1)

    self.assertRaises(base.CodebaseCreationError, action.Perform,
                      db=mock_db)

  def testAddMultipleChangelogs(self):
    mock_db = test_util.MockDbClient()
    mock_editor = test_util.MockEditor()
    mock_client = test_util.MockClient(
        lambda migration_strategy, revisions: mock_editor)
    project = test_util.EmptyMoeProject()

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python',
         '1002': 'simple_python2',
         '1003': 'simple_python',
         '1004': 'simple_python2'
        })

    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'simple_python'},
        lambda: mock_client)

    config = actions.MigrationConfig(base.Migration.EXPORT,
                                     internal_creator,
                                     project.internal_repository,
                                     public_creator,
                                     project.public_repository,
                                     project.export_strategy)
    revisions = [base.Revision('1002', changelog='Change 1: a change',
                               single_scrubbed_log='a change'),
                 base.Revision('1003', changelog='Change 2: another change',
                               single_scrubbed_log='another change'),
                 base.Revision('1004', changelog='Change 3: something',
                               single_scrubbed_log='something')]
    action = actions.Migration(
        base.Revision('1001'),
        base.Revision('1'),
        revisions, project, config, False, -1)

    result = action.Perform(db=mock_db)
    self.assertEqual(result, None)
    self.assertEqual(mock_db.GetMigration('1', abbreviated=False).changelog,
                     '\n\n'.join([r.changelog for r in revisions]))

  def testDivideMultipleChangelogs(self):
    mock_db = test_util.MockDbClient()
    mock_editor = test_util.MockEditor()
    mock_client = test_util.MockClient(
        lambda migration_strategy, revisions: mock_editor)
    project = test_util.EmptyMoeProject()
    project.export_strategy.separate_revisions = True

    internal_creator = test_util.StaticCodebaseCreator(
        {'1001': 'simple_python',
         '1002': 'simple_python2',
         '1003': 'simple_python',
         '1004': 'simple_python2'
        })

    public_creator = test_util.StaticCodebaseCreator(
        {'1': 'simple_python'},
        lambda: mock_client)

    config = actions.MigrationConfig(base.Migration.EXPORT,
                                     internal_creator,
                                     project.internal_repository,
                                     public_creator,
                                     project.public_repository,
                                     project.export_strategy)
    revisions = [base.Revision('1002', changelog='Change 1: a change',
                               single_scrubbed_log='a change'),
                 base.Revision('1003', changelog='Change 2: another change',
                               single_scrubbed_log='another change'),
                 base.Revision('1004', changelog='Change 3: something',
                               single_scrubbed_log='something')]
    action = actions.Migration(
        base.Revision('1001'),
        base.Revision('1'),
        revisions, project, config, False, 1)

    result = action.Perform(db=mock_db)
    self.assertEqual(len(result.actions), 1)
    self.assertEqual(mock_db.GetMigration('1', abbreviated=False).changelog,
                     'a change')

    result = result.actions[0].Perform(db=mock_db)
    self.assertEqual(len(result.actions), 1)
    self.assertEqual(mock_db.GetMigration('2', abbreviated=False).changelog,
                     'another change')

    result = result.actions[0].Perform(db=mock_db)
    self.assertEqual(result, None)
    self.assertEqual(mock_db.GetMigration('3', abbreviated=False).changelog,
                     'something')


if __name__ == '__main__':
  basetest.main()
