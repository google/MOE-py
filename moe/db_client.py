#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""MOE stores state in a database; this is the client for that database.

DOCUMENTATION ALERT!
This is an interface to a domain-specific distributed database.
"""

__author__ = 'dbentley@google.com (Daniel Bentley)'


import getpass
import os
import socket
import sys
import thread
import time
import urllib
import urllib2

import json as simplejson

from google.apputils import file_util
import gflags as flags

from moe import base
from moe import config
from moe import config_utils
from moe import moe_app
from moe import moe_project

FLAGS = flags.FLAGS

flags.DEFINE_string('db_file', '', 'file MOE DB is stored in')
flags.DEFINE_string('moe_db_url',
                    '',
                    'URL of MOE DB server')
flags.DEFINE_boolean('allow_concurrent_instances', False,
                     'If the MOE DB process lock should be skipped')


def Equivalence(internal_revision, public_revision):
  """An Equivalence is a marker that two codebases are equivalent.

  MOE works to keep codebases equivalent, and so many tools want to start
  from the last equivalence.

  Equivalent codebases are likely to have differences between files.
  E.g. if only noisy files differ, the codebases will be different
  but equivalent.

  An Equivalence is a special case of a Correspondence.

  Args:
    internal_revision: str, the internal revision that is equivalent.
    public_revision: str, the public revision that is equivalent.

  Returns:
    An Equivalence.
  """
  return base.Correspondence(internal_revision, public_revision)


DIRECTION_NAMES = {base.Migration.EXPORT: 'export',
                   base.Migration.IMPORT: 'import'}

DIFF_MAX_LENGTH = 100000


class MoeDbClient(object):
  """Abstract interface for the MOE Database to a client project."""

  def NoteEquivalence(self, equivalence,
                      verification_status=base.VERIFICATION_VERIFIED):
    """Add this Equivalence for this project, noting it as current.

    Args:
      equivalence: base.Correspondence
      verification_status: int, one of base.VERIFICATION_*
    """
    raise NotImplementedError

  def StartMigration(self, direction, up_to_revision,
                     migrated_revisions=None):
    """Note the start of a migration.

    Args:
      direction: one of base.Migration.DIRECTION_VALUES
      up_to_revision: base.Revision, the revision that got sent out
      migrated_revisions: list of base.Revision, the revisions migrated

    Returns:
      str, a migration ID. This ID is an opaque token that has no
           relation to either of the revisions' ID's.
    """
    raise NotImplementedError

  def FinishMigration(self, migration_id, submitted_as):
    """Note that a migration has finished.

    Args:
      migration_id: str, the ID of the migration that is now submitted
      submitted_as: base.Revision, the revision the migration was submitted as
    """
    raise NotImplementedError

  def CancelMigration(self, migration_id):
    """Cancel the migration identified by migration_id.

    Args:
      migration_id: str, ID of the migration to cancel

    Note: the migration is not necessarily expunged from the DB.
    """
    raise NotImplementedError

  def GetRevisions(self, repository, num_revisions=100):
    """Get revisions stored in the MOE db.

    Args:
      repository: str, the repository to get revisions from
      num_revisions: int, the number of revisions to fetch

    Returns:
      seq of base.Revision
    """
    raise NotImplementedError

  def FindEquivalences(self, revision, which_repository):
    """Find all equivalences this revision was a part of.

    Args:
      revision: base.Revision
      which_repository: base.{INTERNAL, PUBLIC}, which side of the equivalence
                        we expect this to be on.

    Returns:
      seq of base.Correspondence
    """
    raise NotImplementedError

  def HasRevisionBeenMigrated(self, revision):
    """Determine if revision has been migrated.

    Args:
      revision: base.Revision

    Returns: base.Migration
    """
    raise NotImplementedError


# NB(dbentley): there was FileBackedMoeDbClient. It serialized state in
# a protocol buffer. But it wasn't used much. If you find a use for this
# (testing?), it should be fairly easy to resurrect.


def _Get(url, method, args=None):
  """Get the specified resource.

  Args:
    url: str, the MOE db url
    method: str, the method to call on the api
    args: dict of str to str, the arguments to pass

  Returns:
    object, the loaded JSON result.

  Raises:
    base.HttpError if there was an error
  """
  args = args or {}
  url = '%s/api/%s' % (url.rstrip('/'), method)
  if args:
    url = '%s?%s' % (url, urllib.urlencode(EncodeRecursively(args)))

  try:
    url_result = urllib2.urlopen(url=url)
  except urllib2.HTTPError, e:
    raise base.HttpError('GET failed for %s\nError=%s\nContents=%s'
                    % (url, str(e), e.read()))

  data = url_result.read().decode('utf-8')
  result = simplejson.loads(data)
  return result['data']


def GetStoredProject(url, project_name):
  """Return the project from the config stored in the db.

  Args:
    url: str, URL of the server to connect to
    project_name: str, the project to fetch

  Returns:
    config.MoeProject, or None if the config is not stored in the db.
  """
  try:
    data = _Get(url, 'project/%s' % project_name)
  except base.Error:
    return None
  config_data = data.get('config')
  if not config_data:
    return None
  return config.ParseConfigText(config_data)


def _Post(url, method, data=None):
  """Post data to method."""
  url = '%s/api/%s' % (url.rstrip('/'), method)
  encoded_data = urllib.urlencode(EncodeRecursively(data or {}))

  try:
    url_result = urllib2.urlopen(url=url, data=encoded_data)
  except urllib2.HTTPError, e:
    contents = e.read()
    raise base.HttpError('POST failed for %s\nData=%s\nError=%s\nContents=%s'
                         % (url, encoded_data, str(e), contents),
                         contents=contents)

  result = simplejson.loads(url_result.read().decode('utf-8'))
  return result['data']


def MakeProjectContext(create_project=False, acquire_lock=None):
  """Figure out the MOE project and its context.

  This looks at flags, the running database, and the config file.

  Args:
    create_project: boolean, whether to create the project if it doesn't exist
    acquire_lock: boolean, whether to acquire a lock on the project (None means
                  use the value implied by --allow_concurrent_instances)

  Returns:
    moe_project.MoeProjectContext

  Raises:
    base.Error if a project and client cannot be created. This may also happen
    based on the current environment. E.g., if acquire_lock=True and another
    process on this project is running. This is to prevent two people running
    manage_codebases at the same time and pushing confusingly similar changes
    (and populating the MOE db with confusingly similar but potentially
    conflicting data).

  NB:
    This code is complicated because the user wants it to "Do The Right Thing."
    An example: which server should we connect to? This could read from the flag
    setting the moe_db_url, or the flag specifying the config file (which
    contains a moe_db_url). And then we need to make sure to read that config
    file before contacting the db. But if the project_config_file isn't set,
    we need to talk to the db before reading the config.

    The most rigorous definition of this function is its code and test
    (in db_client_test).
  """
  name = FLAGS.project
  config_file_path = FLAGS.project_config_file
  config_obj = None
  if acquire_lock is None:
    acquire_lock = not FLAGS.allow_concurrent_instances

  if not name and not config_file_path:
    raise base.Error(
        'Must specify at least one of --project or --project_config_file')

  if config_file_path:
    # At this point in MOE setup, there is no moe_app.RUN, so we need to
    # handle output on our own.
    print 'Reading config file from', config_file_path
    config_obj = config.ParseConfigFile(config_file_path)
    if name and name != config_obj.name:
      raise base.Error('Name "%s" from --project and name "%s" from config '
                       'differ.' % (name, config_obj.name))

  moe_app._Init(name or config_obj.name)

  url = ( (FLAGS['moe_db_url'].present and FLAGS.moe_db_url) or
          (config_obj and config_obj.moe_db_url) or
          FLAGS.moe_db_url)
  stored_project = GetStoredProject(url, name or config_obj.name)
  if not stored_project:
    if not create_project:
      raise base.Error(
          'Project %s does not exist. Create it on the MOE db.' %
          (name or config_obj.name))

  if not config_obj:
    # The command-line contained --project but not --project_config_file.
    # We'll read the current config file in from the filesystem, based on
    # the stored project's filename.
    if not stored_project.filename:
      raise base.Error(
          "Cannot determine where your project's config file lives. "
          "Please run MOE once with --project_config_file <path_to_config_file>"
          )
    absolute_config_path = config_utils.MakeConfigFilenameAbsolute(
        stored_project.filename)
    try:
      print 'Reading config file from', absolute_config_path
      current_config_text = file_util.Read(absolute_config_path)
    except IOError:
      raise base.Error(
          'Could not find config file "%s" (expected it at "%s")' %
          (stored_project.filename, absolute_config_path))
    config_obj = config.ParseConfigText(current_config_text,
                                        filename=stored_project.filename)

  _Post(url, 'update_project',
        {'project_name': config_obj.name,
         'project_config': str(config_obj.Serialized()),
         'internal_repository_info': simplejson.dumps(
             config_obj.internal_repository_config.Info()),
         'public_repository_info': simplejson.dumps(
             config_obj.public_repository_config.Info()),
         })
  db = ServerBackedMoeDbClient(config_obj, record_process=acquire_lock,
                               url=url)
  project_context = moe_project.MoeProjectContext(config_obj, db)
  return project_context


class ServerBackedMoeDbClient(MoeDbClient):
  """Client of MOE db's server implementation, based on AppEngine."""

  def __init__(self, project,
               record_process=True, url=None):
    """Initialize, populating project config if necessary.

    Args:
      project: config.MoeProject
      record_process: bool, whether to record this process's run
      url: str, the URL of a server to connect to, for testing
    """
    MoeDbClient.__init__(self)

    url = url or project.moe_db_url or FLAGS.moe_db_url
    self._url = url.rstrip('/')

    self.project = project
    self._connected = True
    self._record_process = record_process

    self._process_id = '%s[%s]@%s' % (getpass.getuser(), os.getpid(),
                                      socket.gethostname())
    if self._record_process:
      try:
        self._Post('start_process',
                   {'project_name': self.project.name,
                    'process_id': self._process_id,
                    'require_lock': record_process})
      except base.Error, e:
        if 'Project already has a running process' in e.contents:
          raise base.Error(
              "Another client is accessing this MOE project. "
              "We've failed eagerly to avoid confusion."
              "Skip this check with --allow_concurrent_instances "
              "(e.g., if you believe the server is mistaken)")
        else:
          raise
      thread.start_new_thread(self._RunUpdateProcess, ())

  def _RunUpdateProcess(self):
    """Continually notify the db of this process's existence."""
    while self._connected:
      self._Post('update_process',
                 {'project_name': self.project.name,
                  'process_id': self._process_id})
      time.sleep(60)  # sleep for one minute

  def _Get(self, method, args=None):
    """Get the specified resource. Return loaded JSON result."""
    if not self._connected:
      raise base.Error('MOE db client has been disconnected')
    return _Get(self._url, method, args)

  def _Post(self, method, data=None):
    """Post data to method."""
    if FLAGS.debug_dry_run:
      return self._DryRunPost(method)
    if not self._connected:
      raise base.Error('MOE db client has been disconnected')

    return _Post(self._url, method, data)

  _DRY_RUN_RESULTS = {
      'start_migration': {'migration_id': '<new-migration-id>'},
      'note_migration': {'migration_id': '<noted-migration-id>'},
      }

  def _DryRunPost(self, method):
    """Version of _Post that returns stub results during a dry run."""
    return self._DRY_RUN_RESULTS.get(method)

  def GetDashboardUrl(self):
    return '%s/project/%s' % (self._url, self.project.name)

  def NoteEquivalence(self, equivalence,
                      verification_status=base.VERIFICATION_VERIFIED):
    """Add this Equivalence for this project, noting it as current."""
    data = {'project_name': self.project.name,
            'internal_revision': simplejson.dumps(
                {'rev_id': equivalence.internal_revision}),
            'public_revision': simplejson.dumps(
                {'rev_id': equivalence.public_revision}),
           }

    if verification_status is not None:
      data['verification_status'] = verification_status

    self._Post('note_equivalence', data)

  def StartMigration(self, direction, up_to_revision,
                     migrated_revisions=None,
                     changelog='', diff='', link='', pre_approved=False):
    """Note the start of a migration.

    Args:
      direction: one of base.Migration.DIRECTION_VALUES
      up_to_revision: base.Revision, the revision that got sent out
      migrated_revisions: list of base.Revision, the revisions migrated
      changelog: str, the commit changelog of the migration
      diff: str, the diff of the migration's code
      link: str, a URL link to the migration's changes
      pre_approved: bool, whether the migration is approved on creation

    Returns:
      str, a migration ID. This ID is an opaque token that has no
           relation to either of the revision ID's.
    """
    data = {'project_name': self.project.name,
            'changelog': changelog,
            'diff': diff,
            'link': link,
            'direction': DIRECTION_NAMES[direction],
            'up_to_revision': simplejson.dumps(up_to_revision.Dump()),
            'migrated_revisions': simplejson.dumps(
                [r.Dump() for r in migrated_revisions or []]),
           }
    if pre_approved:
      data['status'] = base.Migration.APPROVED

    result = self._Post('start_migration', data=data)
    return result['migration_id']

  def FinishMigration(self, migration_id, submitted_as):
    """Note that a migration has finished.

    Args:
      migration_id: str, the ID of the migration that is now submitted
      submitted_as: base.Revision, the revision that this was finished as
    """
    data = {'migration_id': migration_id,
            'submitted_as': simplejson.dumps(submitted_as.Dump()),
            'project_name': self.project.name,
           }
    try:
      self._Post('finish_migration', data=data)
    except base.HttpError:
      # it was a stray instance of the string "MOE_MIGRATION"
      pass

  def NoteMigration(self, direction, up_to_revision,
                    submitted_as, changelog='',
                    diff='', link=''):
    """Note that a migration has occurred and has been completed.

    Args:
      direction: one of base.Migration.DIRECTION_VALUES
      migrated_revision: str, the revision being migrated
      equivalence: Equivalence, the equivalence this is based on
      submitted_revision: str, the revision the migration was submitted as
      changelog: str, the commit changelog of the migration
      diff: str, the diff of the migration's code
      link: str, a URL link to the migration's changes

    Returns:
      str, a migration ID. This ID is an opaque token that has no
           relation to either of the revision ID's.
    """
    data = {'project_name': self.project.name,
            'changelog': changelog,
            'diff': diff,
            'link': link,
            'direction': DIRECTION_NAMES[direction],
            'up_to_revision': simplejson.dumps(
                up_to_revision.Dump()),
            'submitted_as': simplejson.dumps(
                submitted_as.Dump()),
           }
    result = self._Post('note_migration', data=data)
    return result['migration_id']

  def CancelMigration(self, migration_id):
    """Cancel the migration identified by migration_id.

    Args:
      migration_id: str, ID of the migration to cancel

    Note: the migration is not necessarily expunged from the DB.
    """
    data = {'migration_id': migration_id}
    try:
      self._Post('cancel_migration', data=data)
    except base.HttpError:
      # it was a stray instance of the string "MOE_MIGRATION"
      pass

  def MigrationInfo(self, migration_id, abbreviated=True):
    """Get the info about one Migration.

    Args:
      migration_id: str, the id of the migration to get info about.
      abbreviated: bool, whether to skip returning large data fields

    Returns:
      a dictionary of key->value

    NB:
      this is necessary for now for logging and debugging in the
      case of talking to the server, which is why it's a raw dictionary
      instead of a nice pythonic object. TODO(dbentley): revisit this
      decision.
    """
    try:
      return self._Get('migration_info', {'migration_id': migration_id,
                                          'abbreviated': abbreviated,
                                          'project_name': self.project.name })
    except base.HttpError:
      return None

  def GetMigration(self, migration_id, abbreviated=True):
    """Get one migration from the database.

    Args:
      migration_id: str, the id of the migration to get info about.
      abbreviated: bool, whether to skip returning large data fields

    Returns:
      base.Migration
    """
    info = self.MigrationInfo(migration_id, abbreviated)
    if not info:
      return None
    return base.Migration(**StringifyKeys(info))

  def FindMigration(self, up_to_revision, abbreviated=True):
    """Get one migration from the database.

    Args:
      up_to_revision: base.Revision

    Returns:
      base.Migration or None if there is no matching migration
    """
    result = self._Get('find_migration',
                       {'project_name': self.project.name,
                        'up_to_revision':
                          simplejson.dumps(up_to_revision.Dump()),
                        'abbreviated': abbreviated})
    if result:
      return base.Migration(**StringifyKeys(result))
    else:
      return None

  def UpdateMigrationDiff(self, migration_id, diff='', link=''):
    """Update the diff for a migration in the db.

    Args:
      migration_id: str, the migration to update
      diff: str, the diff to use
      link: str, a URL for the changes in the migration
    """
    if len(diff) > DIFF_MAX_LENGTH:
      diff = diff[:DIFF_MAX_LENGTH]
    self._Post('update_migration_diff',
               {'migration_id': migration_id, 'diff': diff, 'link': link,
                'project_name': self.project.name })

  def GetLastProcess(self):
    """Get information for the last manage_codebases run from the db.

    Returns:
      a dictionary of key->value
    """
    return self._Get('get_last_process',
                     {'project_name': self.project.name})


  # Noting a revision takes non-zero time. If there are many revisions to note,
  # this can exceed deadlines, leaving MOE dead in the water.
  MAX_REVISIONS_PER_BATCH = 10

  def NoteRevisions(self, revisions):
    """Note revisions as occurring in a repository.

    Args:
      revisions: seq of base.Revision

    NB:
      idempotent (per-revision)
    """
    while revisions:
      if len(revisions) > self.MAX_REVISIONS_PER_BATCH:
        current = revisions[:self.MAX_REVISIONS_PER_BATCH]
        revisions = revisions[self.MAX_REVISIONS_PER_BATCH:]
      else:
        current = revisions
        revisions = []
      self._Post('note_revisions',
                 {'revisions': simplejson.dumps([r.Dump() for r in current])})

  def GetRevisions(self, repository_name, num_revisions=100):
    """Get revisions for this repository.

    Args:
      repository_name: str, the repository to look in
      num_revisions: int, number of revisions to fetch

    """
    result_dict = self._Get('revisions', {'repository': repository_name,
                                          'num_revisions': num_revisions})
    return RevisionsFromDicts(result_dict['revisions'])

  def FindEquivalences(self, revision, which_repository):
    """Find all equivalences this revision was a part of.

    Args:
      revision: base.Revision
      which_repository: base.{INTERNAL, PUBLIC}, which side of the equivalence
                        we expect this to be on.

    Returns:
      seq of base.Correspondence
    """
    request_dict = { 'project_name': self.project.name }
    if which_repository == base.INTERNAL:
      request_dict['internal_revision'] = simplejson.dumps(revision.Dump())
    elif which_repository == base.PUBLIC:
      request_dict['public_revision'] = simplejson.dumps(revision.Dump())
    else:
      raise base.Error('Invalid which_repository: %s' % repr(which_repository))
    result_dict = self._Get('find_equivalences', request_dict)
    equivalences = result_dict['equivalences']
    return [e for e in EquivalencesFromDicts(equivalences)]

  def FindUnverifiedEquivalences(self):
    """Find all equivalences for this project that are unverified.

    Args:
      None

    Returns:
      seq of base.Correspondence
    """
    request_dict = {'project_name': self.project.name,
                    'verification_status': base.VERIFICATION_UNVERIFIED}

    result_dict = self._Get('find_equivalences', request_dict)
    return EquivalencesFromDicts(result_dict['equivalences'])

  def HasRevisionBeenMigrated(self, revision):
    request_dict = { 'project_name': self.project.name,
                     'revision': simplejson.dumps(revision.Dump()) }

    data = self._Get('migration_for_revision', request_dict).get('migration')
    if data:
      result = base.Migration(**StringifyKeys(data))
      return result
    else:
      return None

  class RecentHistory(object):
    def __init__(self, internal_revisions, public_revisions, equivalences,
                 exports, imports):
      self.internal_revisions = internal_revisions
      self.public_revisions = public_revisions
      self.equivalences = equivalences
      self.exports = exports
      self.imports = imports

  def GetRecentHistory(self):
    """Get Recent History (encapsulated in a RecentHistory) of the project."""
    data = self._Get('recent_history',
                     {'project_name': self.project.name})

    internal_revisions = RevisionsFromDicts(data['internal_revisions'])
    public_revisions = RevisionsFromDicts(data['public_revisions'])
    equivalences = EquivalencesFromDicts(data['equivalences'])
    exports = MigrationsFromDicts(data['exports'])
    imports = MigrationsFromDicts(data['imports'])

    return self.RecentHistory(internal_revisions, public_revisions,
                              equivalences, exports, imports)

  # TODO(dbentley): fix this.
  # def GetRevisionDestinations(self, revisions, repository_name):
  #   """Find where revisions end up after migrations.

  #   Args:
  #     revisions: list of base.Revision
  #     repository_name: str

  #   Returns:
  #     dict of rev_id -> (dict of repository_name -> value)
  #   """
  #   rev_ids = [r.rev_id for r in revisions]
  #   return FixEncoding(
  #       self._Get('revisions/destinations',
  #                 {'project_name': self.project.name,
  #                  'revisions': simplejson.dumps(rev_ids),
  #                  'repository': repository_name
  #                  }))

  # TODO(dbentley): fix this
  # def GetWeeklyStatistics(self):
  #   """Get statistics for the past week of this project."""
  #   return self._Get('get_weekly_statistics',
  #                    {'project_name': self.project.name})

  def Disconnect(self):
    """Disconnect this client from the db.

    NB:
      The client will no longer be able to communicate with the db
      after calling this method.
    """
    if not self._record_process:
      return
    try:
      self._Post('end_process',
                 {'project_name': self.project.name,
                  'process_id': self._process_id})
    except base.Error:
      # Fail silently; the user can't do anything about this, and the
      # errors will show up on the admin console.
      pass
    self._connected = False


def EncodeRecursively(data):
  try:
    if isinstance(data, list):
      return [EncodeRecursively(item) for item in data]
    if isinstance(data, dict):
      return dict([(EncodeRecursively(k), EncodeRecursively(v))
                   for (k, v) in data.items()])
    if isinstance(data, unicode):
      return data.encode('utf-8')
    return data
  except UnicodeEncodeError, e:
    print repr(data)
    print e
    sys.exit(1)


def RevisionsFromDicts(revision_dicts):
  return [base.Revision(r['rev_id'], r['repository_name'],
                        author=r.get('author'), time=r.get('time'))
          for r in revision_dicts]


def EquivalencesFromDicts(equivalence_dicts):
  return [base.Correspondence(e['internal_revision']['rev_id'],
                              e['public_revision']['rev_id'])
          for e in equivalence_dicts]


def MigrationsFromDicts(migration_dicts):
  return [base.Migration(**StringifyKeys(m)) for m in migration_dicts]


def StringifyKeys(d):
  """Turn a dict with unicode keys into a dict with str keys.

  The latter can be passed as kwargs with **; the former cannot.

  Args:
    d: dict of basestring -> object

  Returns:
    dict of str -> object

  Raises:
    some kind of unicode error in the case where a key needs to be
    unicode.
  """
  return dict((str(k), v) for k, v in d.iteritems())
