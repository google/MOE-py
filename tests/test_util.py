#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Utilities for helping to test MOE."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import os

import gflags as flags
from google.apputils import resources

from moe import base
from moe import codebase_utils
from moe import config
from moe import db_client

FLAGS = flags.FLAGS


def TestResourceName(name):
  """Return a resource name for a resource under the test data directory."""
  prefix = __name__ + ':data/'
  return prefix + name


def TestResourceFilename(name):
  """Return the filename of a resource under the test data directory.

  Args:
    name: A resource name under the test data directory. The path should end in
          '/' if name is a directory, which additionally may result in an
          expensive zipfile extraction.

  Returns:
    The name of a file or directory containing the contents of the requested
    resource name.
  """
  name = TestResourceName(name)
  return resources.GetResourceFilename(name.rstrip('/'))


def EmptyMoeProject():
  return config.MoeProject('test')


class MockDbClient(db_client.MoeDbClient):
  """A mock version of the db_client that keeps all database information.

  See interface in db_client.ServerBackedModeDbClient.
  """

  def __init__(self, project=None, migration_id_seed=1):
    """Constructs.

    Args:
      project: config.MoeProject, the project using this client
      migration_id_seed: int, the first migration id to use
    """
    self.project = project
    self.next_migration_id = migration_id_seed
    self.migrations = {}
    self.equivalences = []

  def _NextID(self):
    result = str(self.next_migration_id)
    self.next_migration_id += 1
    return result

  def NoteEquivalence(self, equivalence):
    """Add this equivalence, noting it as current."""
    self.equivalences.append(equivalence)

  def FindEquivalences(self, r, which_repository):
    if which_repository is base.INTERNAL:
      return [e for e in self.equivalences if e.internal_revision == r.rev_id]
    else:
      return [e for e in self.equivalences if e.public_revision == r.rev_id]

  def GetMigration(self, migration_id, abbreviated=True):
    """Get one migration from the database."""
    if migration_id in self.migrations:
      return self.migrations[migration_id]
    raise base.Error('No such migration: %s' % migration_id)

  def FindMigration(self, up_to_revision, abbreviated=True):
    """Get one migration from the database matching given criteria."""
    def Match(m):
      return m.up_to_revision == up_to_revision
    matches = [m for m in self.migrations.values() if Match(m)]
    if len(matches) == 0:
      return None
    elif len(matches) == 1:
      return matches[0]
    raise base.Error('Multiple migrations matching [%s]' %
                     up_to_revision.rev_id)

  def StartMigration(self, direction, up_to_revision,
                     changelog='', diff='', link='', migrated_revisions=None,
                     source_repository=''):
    """Note the start of a migration."""
    migration = base.Migration(
        self._NextID(), direction, base.Migration.ACTIVE,
        up_to_revision, changelog=changelog, diff=diff, link=link,
        revisions=migrated_revisions)

    self.migrations[migration.migration_id] = migration
    return migration.migration_id

  def FinishMigration(self, migration_id, submitted_as):
    """Note that a migration has finished."""
    migration = self.migrations[migration_id]
    migration.status = base.Migration.SUBMITTED
    migration.submitted_as = submitted_as

  def HasRevisionBeenMigrated(self, revision):
    for m in self.migrations:
      if m.up_to_revision == revision:
        return m
    return None

  # def NoteMigration(self, direction, migrated_revision,
  #                   equivalence, submitted_revision, changelog='',
  #                   diff='', link='', base_revision=None):
  #   """Note that a migration has occurred and has been completed."""
  #   if not base_revision:
  #     if direction == base.Migration.EXPORT:
  #       base_revision = equivalence.public_revision
  #       if direction == base.Migration.IMPORT:
  #         base_revision = equivalence.internal_revision
  #   id = self.StartMigration(direction, migrated_revision,
  #                            migrated_revision, base_revision,
  #                            equivalence, changelog=changelog,
  #                            diff=diff, link=link)
  #   self.FinishMigration(id, submitted_revision)

  # def CancelMigration(self, migration_id):
  #   """Cancel the specified migration."""
  #   self.migrations[migration_id].status = base.Migration.CANCELED

  def UpdateMigrationDiff(self, migration_id, diff='', link=''):
    if diff:
      self.migrations[migration_id].diff = diff
    if link:
      self.migrations[migration_id].link = link

  def GetDashboardUrl(self):
    return 'mock.dashboard.url'

  def Disconnect(self):
    pass

  def NoteRevisions(self, *args, **kwargs):
    pass


def MockOutDatabase(db=None):
  if db:
    def MakeClient(*args, **kwargs):
      return db
  else:
    def MakeClient(project_name='', project=None,
                   create_project=False, record_process=True, url=None):
      return MockDbClient()
  db_client.ServerBackedMoeDbClient = None

  def MockMakeProjectAndDbClient(*unused_args, **unused_kwargs):
    project_obj = config.ParseConfigFile(FLAGS.project_config_file)
    return (project_obj, MakeClient())

  db_client.MakeProjectAndDbClient = MockMakeProjectAndDbClient


class MockCodebase(codebase_utils.Codebase):
  def __init__(self, name='', revision=''):
    self.name = name
    self.revision = revision
    self._path = 'Mock Codebases have no path'
    self._project_space = base.PUBLIC_STR

  def MakeEditor(self, migration_strategy):
    return MockEditor(repository_name=self.name, base_revision=self.revision)


CREATED_CODEBASES = []


class MockCodebaseCreator(codebase_utils.CodebaseCreator):
  def __init__(self, name):
    codebase_utils.CodebaseCreator.__init__(self, repository_name=name,
                                            project_space='')
    self.name = name

  def Create(self, revision='', report=None):
    if not revision:
      # NB(dbentley): this replicates what actual CodebaseCreators do.
      # If revision isn't given, it returns a Codebase at head.
      # This is so that uses that only want a recent codebase
      # (because the user offered no additional helpful information)
      # can get one without having to themselves query for the head
      # revision.
      revision = 'head'
    CREATED_CODEBASES.append ((self.name, revision))
    return MockCodebase(name=self.name, revision=revision)

  def RepositoryName(self):
    return self.name

  def ProjectSpace(self):
    return self.name


class MockSourceControlClient(object):
  def __init__(self, repository_name):
    self.repository_name = repository_name

  def MakeEditor(self, *unused_args, **unused_kwargs):
    return MockEditor(repository_name=self.repository_name,
                      base_revision='head')


class MockRepository(object):
  def __init__(self, name, head_revision='',
               revisions_since_equivalence_results=None):
    self.name = name
    self.head_revision = head_revision
    self.revisions_since_equivalence_results = (
        revisions_since_equivalence_results or ([], []))

  def GetHeadRevision(self, highest_rev_id=''):
    return highest_rev_id or self.head_revision

  def RevisionsSinceEquivalence(self, *args, **kwargs):
    return self.revisions_since_equivalence_results

  def MakeClient(self, *unused_args, **unused_kwargs):
    # TODO(dbentley): should this take a revision?
    return MockSourceControlClient(repository_name=self.name)

  def MakeRevisionFromId(self, id):
    return base.Revision(rev_id=id, repository_name=self.name)


class MockRepositoryConfig(base.RepositoryConfig):
  """An empty repository config."""

  def __init__(self, name, repository=None, cc=None, translators=None):
    self.name = name
    self.additional_files_re = None
    self.repository = repository or MockRepository(self.name)
    self.cc = cc or MockCodebaseCreator(self.name)

  def MakeRepository(self, temp_dir='', expander=''):
    return (self.repository, self.cc)

  def Serialized(self):
    return {}

  def Info(self):
    return {'name': self.name}


def MockOutMakeRepositoryConfig(repository_configs=None):
  """Mock out the making of repository configs.

  Args:
    repository_configs: dict of str -> tuple(Repository, CodebaseCreator)
  """

  if repository_configs:
    def MakeMockRepositoryConfig(json_config, repository_name='',
                                 translators=None):
      repository, cc = repository_configs[repository_name]
      return MockRepositoryConfig(repository_name, repository, cc)
  else:
    def MakeMockRepositoryConfig(json_config, repository_name='',
                                 translators=None):
      return MockRepositoryConfig(repository_name)
  config.MakeRepositoryConfig = MakeMockRepositoryConfig


class MockClient(base.CodebaseClient):
  """A mock client."""
  def __init__(self, editor_creator):
    """Constructs.

    Args:
      editor_creator: function(migration_strategy, revisions) ->
                          base.CodebaseEditor, rule for making editors
    """
    self.editor_creator = editor_creator
    self.checked_out = False

  def Checkout(self):
    self.checked_out = True

  def MakeEditor(self, migration_strategy, revisions=None):
    return self.editor_creator(migration_strategy, revisions)


class MockEditor(base.CodebaseEditor):
  """A mock editor to give to push_codebase."""

  def __init__(self, repository_name='', base_revision='',
               walk_result=[], commit_id=None, diff='', link=''):
    self.repository_name = repository_name
    self.base_revision = base_revision
    self.walk_result = walk_result
    self.commit_id = commit_id
    self.diff = diff
    self.link = link
    self.files_seen_dest = []
    self._modified = None

  def Walk(self):
    return self.walk_result

  def Checkout(self):
    pass

  def PutFile(self, relative_dest, src):
    self.files_seen_dest.append(relative_dest)

  def ChangesMade(self):
    # Enforce precondition that FinalizeChange must be called before ChangesMade
    if self._modified is None:
      raise RuntimeError('Called ChangesMade before FinalizeChange')
    return self._modified

  def FinalizeChange(self, commit_message, report):
    self._modified = bool(self.files_seen_dest)

  def CommitChange(self, report):
    return self.commit_id

  def Diff(self):
    return self.diff

  def Link(self):
    return self.link

  def Root(self):
    return 'mock_root'


class StaticCodebaseCreator(codebase_utils.CodebaseCreator):
  """A CodebaseCreator that 'creates' by returning static directories."""

  def __init__(self, revision_to_path_map, client_creator=None,
               project_space=base.PUBLIC_STR, translators=None):
    """Constructs.

    Args:
      revision_to_path_map: dict of str->str, map from revision to path
                            within testdata/codebases of codebase to use.
      client_creator: function -> CodebaseClient, a way to get
                      a client to modify this codebase
      project_space: str, which project space this creates in
      translators: list of translators.Translators
    """
    codebase_utils.CodebaseCreator.__init__(self, project_space=project_space,
                                            translators=translators)
    self._revision_to_path_map = revision_to_path_map
    self._client_creator = client_creator

  def Create(self, revision, report=None):
    codebase = self._revision_to_path_map[revision]
    if not codebase:
      raise base.CodebaseCreationError()
    path = TestResourceFilename('codebases/%s/' % codebase)
    return codebase_utils.Codebase(path, client_creator=self._client_creator,
                                   project_space=self._project_space)


def MockOutPusher(test, codebase_expectations, editor_expectations):
  """Mock out the CodebasePusher so it will not actually try to push.

  Args:
    test: TestCase, the test (so that we can fail)
    codebase_expectations: tuple of str, str (codebase name and revision)
    editor_expectations: tuple of str, str (editor name and base_revision)
  """

  class MockPusher(object):
    def __init__(self, source_codebase, destination_editor,
                 report, **unused_kwargs):
      if not isinstance(source_codebase, codebase_utils.Codebase):
        test.fail('source_codebase is not a codebase: %s' % source_codebase)

      expected_name, expected_revision = codebase_expectations
      test.assertEqual(expected_name, source_codebase.name)
      test.assertEqual(expected_revision, source_codebase.revision)

      if not isinstance(destination_editor, base.CodebaseEditor):
        test.fail('destination_editor is not an editor: %s' %
                  destination_editor)
      expected_name, expected_revision = editor_expectations
      test.assertEqual(expected_name, destination_editor.repository_name)
      test.assertEqual(expected_revision, destination_editor.base_revision)

      if not isinstance(report, base.MoeReport):
        test.fail('report is not a report: %s' % report)

    def Push(self):
      self.pushed = True

  # push_codebase is both a binary and a library. If we import it, it registers
  # flags, which might duplicate other stuff.
  # Once we  have merged it into the main moe command, this will be solved.
  from moe import push_codebase
  push_codebase.CodebasePusher = MockPusher
