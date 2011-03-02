#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Integration test for db_client and the db backend."""

__author__ = 'dbentley@google.com (Daniel Bentley)'


import os
import signal
import sys
import subprocess
import time
import urllib2

import pkg_resources
import json as simplejson

from google.apputils import file_util
import gflags as flags
from google.apputils import resources
from google.apputils import basetest

from moe import base
from moe import config
from moe import config_utils
from moe import db_client
import test_util

from moe import moe_app

FLAGS = flags.FLAGS


PROCESS = None

# Ordered list of places to look for the dev appserver binary. Including the
# whole binary in this test seems like a bad idea.
APPSERVER_PATHS = [
    os.environ.get('DEV_APPSERVER'),
    '~/google_appengine/dev_appserver.py',
    ]
APPSERVER_PATHS = [p for p in APPSERVER_PATHS if p] # strip off empty entries


def TestResourceName(name):
  return test_util.TestResourceName(os.path.join('db', name))


def setUp():
  """Set up a database."""
  # pylint: disable-msg=W0603
  moe_app.InitForTest()
  global PROCESS
  env = dict(os.environ)

  executable = None
  for path in APPSERVER_PATHS:
    if not path:
      continue
    path = os.path.expanduser(path)
    if os.access(path, os.X_OK):
      executable = path
      break
  if not executable:
    raise RuntimeError(
        ('No dev_appserver.py found. Install somewhere in %s '
         '(or set environment variable DEV_APPSERVER)'
         ) % repr(APPSERVER_PATHS))

  db_app_dir = pkg_resources.resource_filename(
      pkg_resources.Requirement.parse('moe'), 'moe/dbapp/')
  # clear datastore on start, for better reproducibility
  args = [executable, '--require_indexes', '--clear_datastore', db_app_dir]
  PROCESS = subprocess.Popen(args, env=env)
  WaitForServer()


def tearDown():
  # TODO(dbentley): what if it doesn't respond?
  os.kill(PROCESS.pid, signal.SIGTERM)


def InternalRevision(rev_id, project, **kwargs):
  return base.Revision(rev_id,
                       project.internal_repository_config.Info()['name'],
                       **kwargs)


def PublicRevision(rev_id, project, **kwargs):
  return base.Revision(rev_id, project.public_repository_config.Info()['name'],
                       **kwargs)

def Post(url, data):
  return db_client._Post('http://localhost:8080', url, data)

def Get(url, data):
  return db_client._Get('http://localhost:8080', url, data)

class MoeDbTest(basetest.TestCase):

  def _CreateProject(self, test_name='testProject', with_equivalence=False,
                     project=None, record_process=True, file='default_project'):
    if not project:
      json = resources.GetResource(TestResourceName(file))
      json = json.replace('createProject', test_name)
      project = config.MoeProjectConfigFromJson(simplejson.loads(json))
      Post(
          'update_project',
          {'project_name': project.name,
           'project_config': str(project.Serialized()),
           'internal_repository_info':
             simplejson.dumps(project.internal_repository_config.Info()),
           'public_repository_info':
             simplejson.dumps(project.public_repository_config.Info())})
    self._client = db_client.ServerBackedMoeDbClient(
        project=project,
        record_process=record_process,
        url='http://localhost:8080')
    if with_equivalence:
      self._client.NoteEquivalence(db_client.Equivalence('1001', '1'))
    return self._client.project

  def tearDown(self):
    if hasattr(self, '_client') and self._client._connected:
      self._client.Disconnect()

  def testCreateProject(self):
    project = self._CreateProject('createProject')
    stored_project = db_client.GetStoredProject(
        'http://localhost:8080',
        'createProject')
    self.assertTrue(isinstance(stored_project, config.MoeProjectConfig),
                    str(stored_project))
    self.assertMultiLineEqual(str(stored_project.Serialized()),
                              str(project.Serialized()))

  def testGetNonexistentProject(self):
    stored_project = db_client.GetStoredProject(
        'http://localhost:8080',
        'nonexistent_project')
    self.assertEqual(None, stored_project)

  def testOneEquivalence(self):
    project = self._CreateProject('OneEquivalence')
    equivalence = db_client.Equivalence('1001', '1')
    self._client.NoteEquivalence(equivalence)

    stored_equivalences = self._client.FindEquivalences(
        InternalRevision('1001', project),
        base.INTERNAL
        )
    self.assertEqual([equivalence], stored_equivalences)

    stored_equivalences = self._client.FindEquivalences(
        PublicRevision('1', project),
        base.PUBLIC
        )
    self.assertEqual([equivalence], stored_equivalences)

    stored_equivalences = self._client.FindEquivalences(
        PublicRevision('1001', project),
        base.PUBLIC
        )
    self.assertEqual([], stored_equivalences)

  def testInvalidEquivalence(self):
    project = self._CreateProject('InvalidEquivalence')
    equivalence = db_client.Equivalence('1001', '1')
    self._client.NoteEquivalence(equivalence)

    invalid_equivalence = db_client.Equivalence('1002', '1')
    self._client.NoteEquivalence(invalid_equivalence,
                                 verification_status=base.VERIFICATION_INVALID)
    stored_equivalences = self._client.FindEquivalences(
        PublicRevision('1', project),
        base.PUBLIC
        )
    self.assertEqual([equivalence], stored_equivalences)

  def testEquivalencesFromDifferentProjects(self):
    project_a = self._CreateProject('ProjEquivalenceA')
    client_a = self._client

    project_b = self._CreateProject('ProjEquivalenceB')
    client_b = self._client

    equivalence_a = db_client.Equivalence('1001', '1')
    client_a.NoteEquivalence(equivalence_a)

    equivalence_b = db_client.Equivalence('1001', '2')
    client_b.NoteEquivalence(equivalence_b)

    equivalence_a2 = db_client.Equivalence('1002', '3')
    client_a.NoteEquivalence(equivalence_a2)

    equivalence_b2 = db_client.Equivalence('1003', '3')
    client_b.NoteEquivalence(equivalence_b2)

    self.assertEqual([equivalence_a], client_a.FindEquivalences(
        InternalRevision('1001', project_a),
        base.INTERNAL))
    self.assertEqual([], client_a.FindEquivalences(
        InternalRevision('1001', project_b),
        base.INTERNAL))

    self.assertEqual([equivalence_a], client_a.FindEquivalences(
        PublicRevision('1', project_a),
        base.PUBLIC))
    self.assertEqual([], client_a.FindEquivalences(
        PublicRevision('2', project_a),
        base.PUBLIC))
    self.assertEqual([equivalence_a2], client_a.FindEquivalences(
        PublicRevision('3', project_a),
        base.PUBLIC))

    self.assertEqual([], client_b.FindEquivalences(
        InternalRevision('1001', project_a),
        base.INTERNAL))
    self.assertEqual([equivalence_b], client_b.FindEquivalences(
        InternalRevision('1001', project_b),
        base.INTERNAL))

    self.assertEqual([], client_b.FindEquivalences(
        PublicRevision('1', project_b),
        base.PUBLIC))
    self.assertEqual([equivalence_b], client_b.FindEquivalences(
        PublicRevision('2', project_b),
        base.PUBLIC))
    self.assertEqual([equivalence_b2], client_b.FindEquivalences(
        PublicRevision('3', project_b),
        base.PUBLIC))

  def testEquivalenceVerification(self):
    self._CreateProject('EquivalenceVerification')
    equivalence1 = db_client.Equivalence('1001', '1')
    self._client.NoteEquivalence(equivalence1)
    equivalence2 = db_client.Equivalence('1003', '3')
    self._client.NoteEquivalence(
        equivalence2,
        verification_status=base.VERIFICATION_UNVERIFIED)

    stored_equivalences = self._client.FindUnverifiedEquivalences()
    self.assertEqual([equivalence2], stored_equivalences)

    self._client.NoteEquivalence(equivalence2)
    self.assertEqual([], self._client.FindUnverifiedEquivalences())

  def testMigration(self):
    project = self._CreateProject('Migration', with_equivalence=True)
    migration_id = self._client.StartMigration(
        base.Migration.EXPORT, InternalRevision('1003', project))
    migration = self._client.GetMigration(migration_id)
    expected = base.Migration(
        **{'migration_id': migration_id,
           'status': 'Pending',
           'direction': 'export',
           'project_name': 'Migration',
           'up_to_revision': InternalRevision('1003', project),
           'submitted_as': None})
    self.assertDictEqual(migration.Dict(), expected.Dict())

    migration = self._client.FindMigration(
        InternalRevision('1003', project))
    self.assertDictEqual(migration.Dict(), expected.Dict())

    self._client.FinishMigration(migration_id,
                                 PublicRevision('5', project))
    migration = self._client.GetMigration(migration_id)
    expected = base.Migration(
        **{'migration_id': migration_id,
           'status': 'Submitted',
           'direction': 'export',
           'project_name': 'Migration',
           'up_to_revision': InternalRevision('1003', project),
           'submitted_as': PublicRevision('5', project).Dump(),
           })
    self.assertDictEqual(migration.Dict(), expected.Dict())

    migration = self._client.FindMigration(InternalRevision('1003', project))
    self.assertDictEqual(migration.Dict(), expected.Dict())

    migration = self._client.FindMigration(InternalRevision('1007', project))
    self.assertEqual(None, migration)

    migration = self._client.HasRevisionBeenMigrated(
        InternalRevision('1003', project))
    self.assertEqual(expected.Dict(), migration.Dict())

    migration = self._client.HasRevisionBeenMigrated(
        InternalRevision('1007', project))
    self.assertEqual(None, migration)

  def testNoteMigration_new(self):
    project = self._CreateProject('NoteNewMigration', with_equivalence=True)
    migration_id = self._client.NoteMigration(
        base.Migration.EXPORT,
        InternalRevision('1003', project),
        PublicRevision('3', project))
    migration = self._client.GetMigration(migration_id)
    expected = base.Migration(
        **{'migration_id': migration_id,
           'status': 'Submitted',
           'direction': 'export',
           'project_name': 'NoteNewMigration',
           'up_to_revision': InternalRevision('1003', project),
           'submitted_as': PublicRevision('3', project).Dump(),
           })
    self.assertDictEqual(migration.Dict(), expected.Dict())

    migration = self._client.FindMigration(
        InternalRevision('1003', project))
    self.assertDictEqual(migration.Dict(), expected.Dict())

  def testLongChangelog(self):
    project = self._CreateProject('LongLog', with_equivalence=True)
    changelog = resources.GetResource(TestResourceName('long_changelog.txt'))
    migration_id = self._client.StartMigration(
        base.Migration.EXPORT, InternalRevision('1003', project),
        changelog=changelog)
    migration = self._client.GetMigration(migration_id, abbreviated=False)
    expected = base.Migration(
        **{'migration_id': migration_id,
           'changelog': changelog,
           'status': 'Pending',
           'direction': 'export',
           'project_name': 'LongLog',
           'up_to_revision': InternalRevision('1003', project),
           'submitted_as': None})
    self.assertDictEqual(migration.Dict(), expected.Dict())

    migration = self._client.FindMigration(
        InternalRevision('1003', project),
        abbreviated=False)
    self.assertDictEqual(migration.Dict(), expected.Dict())

  def testStoringRevisions(self):
    project = self._CreateProject('Revisions', with_equivalence=True)
    revision_1002 = InternalRevision('1002', project, author='foo@google.com')
    revision_1004 = InternalRevision('1004', project, author='bar@google.com')
    migration_id = self._client.StartMigration(
        base.Migration.EXPORT, revision_1004,
        migrated_revisions=[revision_1002, revision_1004])
    migration = self._client.GetMigration(migration_id, abbreviated=False)
    expected = base.Migration(
        **{'migration_id': migration_id,
           'status': 'Pending',
           'direction': 'export',
           'project_name': 'LongLog',
           'up_to_revision': revision_1004,
           'submitted_as': None,
           'revisions': [revision_1002.Dump(), revision_1004.Dump()],
          })
    self.assertDictEqual(migration.Dict(), expected.Dict())

  def testGettingRevisions(self):
    project = self._CreateProject('QueryRevisions')
    revision_1002 = InternalRevision('1002', project,
                                     author='foo@google.com',
                                     time='2010-7-8 01:02:03')
    revision_1004 = InternalRevision('1004', project,
                                     author='bar@google.com',
                                     time='2010-7-14 13:12:11')
    revision_3 = PublicRevision('3', project, author='baz@notgoogle.com')
    export_id = self._client.StartMigration(
        base.Migration.EXPORT, revision_1004,
        migrated_revisions=[revision_1002, revision_1004])
    import_id = self._client.StartMigration(
        base.Migration.IMPORT, revision_3,
        migrated_revisions=[revision_3])
    revisions = self._client.GetRevisions('QueryRevisions_internal_svn')
    self.assertListEqual([revision_1004.Dump(), revision_1002.Dump()],
                         [r.Dump() for r in revisions])
    revisions = self._client.GetRevisions('QueryRevisions_internal_svn',
                                          num_revisions=1)
    self.assertListEqual([revision_1004.Dump()], [r.Dump() for r in revisions])
    self.assertRaisesWithRegexpMatch(
        base.Error,
        'No such repository',
        self._client.GetRevisions,
        'nonexistent_repository')


  def testNotingRevisions(self):
    project = self._CreateProject('NoteRevisions')
    revision_101 = PublicRevision('101', project, author='foo@test.com')
    revision_102 = PublicRevision('102', project, author='bar@test.com')
    self._client.NoteRevisions([revision_101, revision_102])
    revisions = self._client.GetRevisions('NoteRevisions_public_svn')
    self.assertListEqual([revision_102.Dump(), revision_101.Dump()],
                         [r.Dump() for r in revisions])

    # test idempotence of noting revisions
    self._client.NoteRevisions([revision_101, revision_102])
    revisions = self._client.GetRevisions('NoteRevisions_public_svn')
    self.assertListEqual([revision_102.Dump(), revision_101.Dump()],
                         [r.Dump() for r in revisions])

    # Test batching
    long_revisions = [InternalRevision(str(1001 + i), project)
                      for i in range(103)]
    self._client.NoteRevisions(long_revisions)
    revisions = self._client.GetRevisions('NoteRevisions_internal_svn',
                                          num_revisions=150)
    self.assertListEqual(list(reversed(long_revisions)), revisions)

  def testDiff(self):
    project = self._CreateProject('Diff', with_equivalence=True)
    migration_id = self._client.StartMigration(
        base.Migration.EXPORT, InternalRevision('1003', project),
        changelog=u'sample changelog\u2026')
    diff = 'somewhat long diff...' * 1000
    self._client.UpdateMigrationDiff(migration_id, diff=diff)

    migration = self._client.GetMigration(migration_id, abbreviated=False)
    expected = base.Migration(
        **{'migration_id': migration_id,
           'changelog': u'sample changelog\u2026',
           'status': 'Pending',
           'direction': 'export',
           'diff': diff,
           'project_name': 'Migration',
           'up_to_revision': InternalRevision('1003', project),
           'submitted_as': None})
    self.assertDictEqual(migration.Dict(), expected.Dict())

  def testLongDiff(self):
    project = self._CreateProject('LongDiff', with_equivalence=True)
    migration_id = self._client.StartMigration(
        base.Migration.EXPORT, InternalRevision('1003', project),
        changelog='sample changelog')
    diff = 'long diff is long...' * 10000
    self._client.UpdateMigrationDiff(migration_id, diff=diff)

    migration = self._client.GetMigration(migration_id, abbreviated=False)
    self.assertNotEqual(diff, migration.diff)

  def testLink(self):
    project = self._CreateProject('Link', with_equivalence=True)
    migration_id = self._client.StartMigration(
        base.Migration.EXPORT, InternalRevision('1003', project),
        changelog='sample changelog')
    link = 'http://codereview.appspot.com/'
    self._client.UpdateMigrationDiff(migration_id, link=link)

    migration = self._client.GetMigration(migration_id, abbreviated=False)
    self.assertEqual(link, migration.link)

  def testGetLastProcess(self):
    self._CreateProject('CheckProcess')
    process_data = self._client.GetLastProcess()
    self.assertEqual(process_data['project_name'], u'CheckProcess')
    self.assertEqual(process_data['running'], True)

  def testProjectLockError(self):
    project = config.MoeProjectConfig('ProjectLock')
    Post(
        'update_project',
        {'project_name': project.name,
         'project_config': str(project.Serialized()),
         'internal_repository_info':
           simplejson.dumps(project.internal_repository_config.Info()),
         'public_repository_info':
           simplejson.dumps(project.public_repository_config.Info())})
    unused_db = db_client.ServerBackedMoeDbClient(
        project,
        url='http://localhost:8080')
    self.assertRaisesWithRegexpMatch(
        base.Error,
        'Another client is accessing this MOE project',
        db_client.ServerBackedMoeDbClient,
        project=project, url='http://localhost:8080')

  def testFinishMigration(self):
    project = self._CreateProject('FinishMigration')
    # FinishMigration will fail silently.
    self._client.FinishMigration('123',
                                 PublicRevision('5', project))

  def testComments(self):
    project = self._CreateProject('Comments')
    migration_id = self._client.StartMigration(
        base.Migration.EXPORT, InternalRevision('1003', project),
        changelog='sample changelog')
    comments = Get(
        'comments',
        {'migration_id': migration_id})['comments']
    self.assertEqual(0, len(comments))

    comment_data = {
        'migration_id': migration_id,
        'file': 'file.js',
        'date': "Half past a monkey's ass",
        'lineno': '10',
        'author': 'nicksantos',
        'text': 'This code is terrible',
    }
    last_comment_id = Post(
        'add_comment', comment_data)['comment_id']

    comments = Get(
        'comments',
        {'migration_id': migration_id})['comments']
    self.assertEqual(1, len(comments))
    for key in comment_data.keys():
      self.assertEqual(comment_data[key], comments[0][key],
                       'Comment data: %s' % key)

    Post(
        'edit_comment',
        {'comment_id': last_comment_id,
         'comment_text': 'This code looks good to me'})
    comments = Get('comments',
        {'migration_id': migration_id})['comments']
    self.assertEqual('This code looks good to me', comments[0]['text'])

  def testApproveMigration(self):
    project = self._CreateProject('ApproveMigration')
    migration_id = self._client.StartMigration(
        base.Migration.EXPORT, InternalRevision('1003', project),
        changelog='sample changelog')
    comments = Get(
        'comments',
        {'migration_id': migration_id})['comments']
    comment_data_1 = {
        'migration_id': migration_id,
        'text': 'indent +2',
    }
    comment_data_2 = {
        'migration_id': migration_id,
        'text': 'Needs a semicolon',
    }
    comment_id_1 = Post('add_comment', comment_data_1)['comment_id']
    comment_id_2 = Post('add_comment', comment_data_2)['comment_id']

    Post('approve_migration',
         {'migration_id': migration_id})

    server_migration = self._client.MigrationInfo(migration_id, False)
    self.assertEqual('Approved', server_migration['status'])
    self.assertEqual('sample changelog', server_migration['changelog'])

    # Unapprove and re-approve.
    Post('unapprove_migration',
         {'migration_id': migration_id})
    Post('approve_migration',
         {'migration_id': migration_id,
          'changelog': 'real changelog',
          'comment_id_0': comment_id_1,
          'comment_text_0': 'indent +4',
          'comment_id_1': comment_id_2,
          'comment_text_1': 'oh, i see the semicolon'})

    server_migration = self._client.MigrationInfo(migration_id, False)
    self.assertEqual('real changelog', server_migration['changelog'])

    comments = Get('comments',
        {'migration_id': migration_id})['comments']
    comments_dict = {}
    for c in comments:
      comments_dict[c['comment_id']] = c['text']
    self.assertEqual('indent +4', comments_dict[comment_id_1])
    self.assertEqual('oh, i see the semicolon', comments_dict[comment_id_2])

  def testRecentHistory(self):
    project = self._CreateProject('RecentHistory')

    # note internal revisions
    revision_1001 = InternalRevision('1001', project)
    revision_1002 = InternalRevision('1002', project)
    revision_1003 = InternalRevision('1003', project)
    revision_1004 = InternalRevision('1004', project)
    revision_1005 = InternalRevision('1005', project)
    revision_1006 = InternalRevision('1006', project)
    internal_revisions = [
        revision_1001, revision_1002, revision_1003,
        revision_1004, revision_1005, revision_1006]
    self._client.NoteRevisions(internal_revisions)

    # note public revisions
    revision_1 = PublicRevision('1', project)
    revision_2 = PublicRevision('2', project)
    revision_3 = PublicRevision('3', project)
    revision_4 = PublicRevision('4', project)
    revision_5 = PublicRevision('5', project)
    revision_6 = PublicRevision('6', project)
    public_revisions = [
        revision_1, revision_2, revision_3,
        revision_4, revision_5, revision_6]
    self._client.NoteRevisions(public_revisions)

    # note equivalences
    equivalences = set()
    equivalence = db_client.Equivalence('1001', '1')
    self._client.NoteEquivalence(equivalence)
    equivalences.add(equivalence)

    equivalence = db_client.Equivalence('1002', '2')
    self._client.NoteEquivalence(equivalence)
    equivalences.add(equivalence)

    equivalence = db_client.Equivalence('1004', '5')
    self._client.NoteEquivalence(equivalence)
    equivalences.add(equivalence)

    equivalence = db_client.Equivalence('1006', '6')
    self._client.NoteEquivalence(equivalence)
    equivalences.add(equivalence)

    # note exports
    exports = []
    imports = []

    def NoteExport(up_to_revision, submitted_as):
      migration_id = self._client.NoteMigration(
          base.Migration.EXPORT, up_to_revision, submitted_as)
      exports.append(base.Migration(
          migration_id, base.Migration.EXPORT,
          base.Migration.SUBMITTED, up_to_revision,
          submitted_as))

    def NoteImport(up_to_revision, submitted_as):
      migration_id = self._client.NoteMigration(
          base.Migration.IMPORT, up_to_revision, submitted_as)
      imports.append(base.Migration(
          migration_id, base.Migration.IMPORT,
          base.Migration.SUBMITTED, up_to_revision,
          submitted_as))

    NoteExport(revision_1002, revision_2)

    NoteImport(revision_3, revision_1004)

    NoteExport(revision_1003, revision_4)

    NoteExport(revision_1004, revision_5)

    NoteImport(revision_6, revision_1006)
    result = self._client.GetRecentHistory()

    self.assertEqual(list(reversed(internal_revisions)),
                     result.internal_revisions)
    self.assertEqual(list(reversed(public_revisions)),
                     result.public_revisions)
    self.assertSameElements(equivalences, result.equivalences)
    self.assertSameElements(exports, result.exports)
    self.assertSameElements(imports, result.imports)

  # TODO(dbentley): fix statistics
  # def testStatistics(self):
  #   self._CreateProject('Statistics', with_equivalence=True)
  #   revision_1002 = base.Revision('1002', '', 'foo@google.com')
  #   revision_1003 = base.Revision('1003', '', 'bar@google.com')
  #   revision_1004 = base.Revision('1004', '', 'foo@google.com')
  #   revision_2 = base.Revision('2', '', 'someone@somewhere.org')

  #   export1 = self._client.StartMigration(
  #       base.Migration.EXPORT, '1002', '1003', '1',
  #       db_client.Equivalence('1001', '1'),
  #       revisions=[revision_1002, revision_1003],
  #       source_repository='stats_test')
  #   export2 = self._client.StartMigration(
  #       base.Migration.EXPORT, '1004', '1004', '1',
  #       db_client.Equivalence('1001', '1'),
  #       revisions=[revision_1004],
  #       source_repository='stats_test')
  #   import1 = self._client.StartMigration(
  #       base.Migration.IMPORT, '2', '2', '1004',
  #       db_client.Equivalence('1001', '1'),
  #       revisions=[revision_2],
  #       source_repository='stats_svn')
  #   self._client.FinishMigration(import1, '1005')
  #   self._client.FinishMigration(export1, '3')
  #   self._client.FinishMigration(export2, '4')

  #   stats = self._client.GetWeeklyStatistics()
  #   self.assertEqual(stats[u'imports_finished'], 1)
  #   self.assertEqual(stats[u'import_authors'], 1)
  #   self.assertEqual(stats[u'exports_finished'], 2)
  #   self.assertEqual(stats[u'export_authors'], 2)

  def testDisconnect(self):
    project = self._CreateProject('Disconnect', with_equivalence=True)
    self._client.FinishMigration('123', InternalRevision('a', project))
    self._client.Disconnect()
    self.assertRaisesWithRegexpMatch(
        base.Error,
        'MOE db client has been disconnected',
        self._client.GetMigration, '123')


def WaitForServer():
  for _ in range(100):
    try:
      urllib2.urlopen('http://localhost:8080')
      return
    except urllib2.URLError:
      sys.stderr.write('Waiting for dev_appserver.py to start.\n')
      sys.stderr.flush()
      time.sleep(1)
      continue
  raise base.Error()


if __name__ == '__main__':
  basetest.main()
