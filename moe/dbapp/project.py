#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved

import logging
import re

from django.utils import simplejson

from google.appengine.api import mail
from google.appengine.ext import db
from google.appengine.ext import webapp
from google.appengine.ext.webapp import mail_handlers

import base
import cgi
import datetime
import models
import os
import pstats
import re
import time


PROJECT_NAME_RE = re.compile('^[\w-]+$')

MESSAGE_SUBJECT_TEMPLATE = 'MOE pending migrations for project %s'
MESSAGE_SUBJECT_REGEXP = re.compile('for project ([\w-]+)')

_AUTOMATED_MESSAGE_FOOTER = """
# TODO(dborowitz): Probably need a better bulk-mail footer.
This is an automated mail sent by Make Open Easy. For more information, see
http://code.google.com/p/moe.
"""

PENDING_MIGRATION_MESSAGE_TEMPLATE = """Greetings %(ldap)s,

There are migrations pending for your project %(name)s.

%(migration_info)s

To approve all of these, you may forward this email to %(reply-to)s with an LGTM.
If you would like to make edits first, you can go to the MOE DB:
http://%(host)s/project/%(name)s/pending

Sincerely,
Your friendly automated MOE notifier
%(footer)"""

MIGRATION_INFO_MESSAGE_TEMPLATE = """- %(dir)s %(id)s of revisions %(revs)s
------ Changelog: ------
%(changelog)s
------------------------
"""
MIGRATION_INFO_REGEXP = re.compile('- (\w+) (\d+) of revisions (\[.*?])')


class Error(Exception):
  pass


def MaybePrintProfilingData(response):
  if base.PROFILING_ENABLED:
    response.out.write('<pre>')
    stats = pstats.Stats(base.GetProfiler(), stream=response.out)
    stats.sort_stats('cumulative')
    stats.print_stats(100)
    response.out.write('</pre>')


def GetProjectNames():
  """Returns a list of all project names, in sorted order"""
  return [p.name for p in db.Query(models.Project).order('name')]


def GetProjectInfos():
  projects = list(db.Query(models.Project).order('name'))
  return [{'name': p.name, 'scores': GetProjectScore(p)} for p in projects]


def GetProject(project_name):
  if not PROJECT_NAME_RE.match(project_name):
    raise Exception(
        'project name "%s" contains characters outsize [a-zA-Z0-9_]' %
        project_name)
  p = db.Query(models.Project).filter('name =', project_name).get()
  return p


def QueryProject(model, project):
  return db.Query(model).filter('project =', project)


def GetEquivalence(project, internal_revision, public_revision):
  q = (QueryProject(models.Equivalence, project)
       .filter('internal_revision =', internal_revision)
       .filter('public_revision =', public_revision))
  return q.get()


def GetCommentsByMigration(migration):
  """Get the comments for a migration"""
  q = db.Query(models.Comment).filter('migration =', migration)
  return list(q.fetch(1000))

def RevisionKeyName(rev_id, repository_name):
  """Compute the keyname for a revision.

  We use a keyname. This allows faster lookups. But more importantly, it
    enforces uniqueness. Each revision in a Repository exists at most once.
    This is useful, because otherwise we'd have a race condition.

  Args:
    rev_id: str, the revision id
    repository_name: str, the repository name

  Returns:
    str, the key name
  """
  return '%s:%s' % (repository_name, rev_id)


def FindEquivalences(project,
                     internal_revision_obj=None,
                     public_revision_obj=None,
                     verification_status=None):
  if (not internal_revision_obj and not public_revision_obj and
      verification_status is None):
    raise Error('Neither internal nor public nor verification_status given')
  q = QueryProject(models.Equivalence, project)
  if internal_revision_obj:
    q.filter('internal_revision_obj =', internal_revision_obj)
  if public_revision_obj:
    q.filter('public_revision_obj =', public_revision_obj)
  if verification_status:
    q.filter('verification_status =', int(verification_status))
  result = list(q.fetch(1000))
  if not verification_status:
    # By default, we do *not* want invalid equivalences.
    result = [e for e in result
              if not e.verification_status == models.VERIFICATION_INVALID]

  return result


def FindEquivalencesList(project,
                         internal_revisions=None,
                         public_revisions=None):
  if (not internal_revisions and not public_revisions):
    raise Error('Neither internal nor public given')
  q = QueryProject(models.Equivalence, project)
  if internal_revisions:
    q.filter('internal_revision_obj IN ', internal_revisions)
  if public_revisions:
    q.filter('public_revision_obj IN ', public_revisions)
  return [e for e in q.fetch(1000)
          if not e.verification_status == models.VERIFICATION_INVALID]


def GetRevisionFromRequest(request, project, param_name, repository=None):
  """Get a revision object encoded in the request.

  Args:
    request: AppEngine Request object
    project: models.Project
    param_name: str, the parameter the revision is stored in.
    repository: models.Repository; the repository to assume the revision is in.

  Returns:
    models.Revision
  """
  if param_name == 'internal_revision':
    repository = project.internal_repository
  if param_name == 'public_revision':
    repository = project.public_repository

  data = request.get(param_name)

  if data:
    data = simplejson.loads(data)
    rev_id = data['rev_id']
    if 'repository_name' in data:
      repository = GetRepository(data['repository_name'])
      # NB(dbentley): if this repository is None, that means that they have
      # specified a repository, but we don't know about it. This is
      # a semi-surprising error, and we should probably explain it better.
  else:
    rev_id = request.get(param_name + '_id')

  if not rev_id or not repository:
    return None

  return EnsureRevisionExists(rev_id, repository)


def GetRevision(rev_id, repository):
  """Get a revision by id and repository.

  Args:
    rev_id: str
    repository: models.Repository

  Returns:
    models.Revision
  """
  r = models.Revision.get_by_key_name(RevisionKeyName(rev_id, repository.name))
  return r


def EnsureRevisionExists(rev_id, repository):
  """Find a revision if it exists, or make a new one.

  Args:
    rev_id: str
    repository: models.Repository

  Returns:
    models.Revision, the matching revision if it exists, else the new one
  """
  revision = GetRevision(rev_id, repository)
  if not revision:
    keyname = RevisionKeyName(rev_id, repository.name)
    revision = models.Revision(key_name=keyname,
                               rev_id=rev_id,
                               repository_name=repository.name)
    revision.put()
  return revision


def MigrationKeynameFromRevisionObj(up_to_revision):
  """A migration's keyname is the keyname of its up_to_revision.

  Args:
    up_to_revision: models.Revision
  """
  return up_to_revision.key().name()


def LookupMigrationByRevision(up_to_revision):
  key_name = MigrationKeynameFromRevisionObj(up_to_revision)
  return models.Migration.get_by_key_name(key_name)


def LookupMigrationsByRevisions(project, revisions):
  q = (QueryProject(models.Migration, project)
       .filter('up_to_revision IN', revisions))
  return list(q.fetch(1000))


def LookupMigrationByMigrationId(migration_id):
  """Lookup Migration by Migration ID.

  Args:
    migration_id: int, id of the migration

  Returns:
    models.Migration
  """
  q = db.Query(models.Migration).filter('migration_id =', migration_id)
  return q.get()


def GetPendingMigrations(project):
  q = (QueryProject(models.Migration, project)
       .filter('status IN ', [models.STATUS_ACTIVE, models.STATUS_APPROVED]))
  return list(q.fetch(1000))


def GetProcess(project, process_id):
  q = (QueryProject(models.Process, project)
       .filter('process_id =', process_id))
  return q.get()


def GetLastSeenProcess(project):
  q = (QueryProject(models.Process, project)
       .order('-last_seen'))
  return q.get()


def GetProcessRange(project, start_time, end_time):
  q = (QueryProject(models.Process, project)
       .filter('start_time >', start_time))
  # filter can have at most one inequality
  result = [p for p in q if p.end_time and p.end_time < end_time]
  return result


def GetRepository(repository_name):
  return models.Repository.get_by_key_name(repository_name)


def UpdateRepository(info):
  """Update a repository so it reflects info.

  Args:
    info: dict of str->value.

  Returns:
    Repository
  """
  name = info['name']
  r = EnsureRepositoryExists(name)
  if 'parent_repository' in info:
    r.parent_repository = info['parent_repository']
  r.put()
  return r


def EnsureRepositoryExists(name):
  """Ensure a repository with the proper name exists in the datastore.

  Args:
    name: str, name of the project

  Returns:
    Repository
  """
  # TODO(dbentley): eventually, repositories will have more information and
  # we will want to update them with the current state.
  repository = GetRepository(name)
  if repository:
    return repository

  repository = models.Repository(key_name=name, name=name)
  repository.put()
  return repository


def GetProjectScore(project):
  """Get scores for aspects of this project.

  Args:
    project: models.Project

  Returns:
    dict of key -> {'value': str, 'score': one of [1, 2, 3, 4]}
  """
  data = {}
  now = datetime.datetime.utcnow()
  process = GetLastSeenProcess(project)
  if process:
    delta = now - process.last_seen
    if delta < datetime.timedelta(hours=36):
      value = 'last day'
      score = 4
    elif delta < datetime.timedelta(days=7):
      value = 'last week'
      score = 3
    elif delta < datetime.timedelta(days=14):
      value = 'last two weeks'
      score = 2
    else:
      value = 'more than two weeks ago'
      score = 1
  else:
    value = 'more than two weeks ago'
    score = 1
  data['last_run'] = {'value': value, 'score': score}
  return data


class ProjectPage(webapp.RequestHandler):
  def get(self, project_name):
    project = GetProject(project_name)
    if not project:
      self.response.out.write(
          base.RenderTemplate('no-such-project.html',
                              {'project_name' : project_name}))
      self.error(404)
      return

    if not project.internal_repository:
      # If we don't have any repositories for this project, then that
      # means the project hasn't been properly set up. In particular, it
      # needs to note an equivalence. Give it the form template.
      template_values = {
        'project_name': project_name,
        }
      self.response.out.write(
          base.RenderTemplate('forms.html', template_values))
      return

    recent_history = GetRecentHistory(project)
    recent_history_for_json = {}
    for k, v in recent_history.iteritems():
      recent_history_for_json[k] = [i.DictForJson() for i in v]

    pending_migrations = GetPendingMigrations(project)
    project_config = self.PrettyPrintProjectConfigJson(
        simplejson.loads(project.config))

    template_values = {
        'debug': base.DEBUG_MODE,
        'project_name' : project_name,
        'project_config' : project_config,
        'internal_revisions': recent_history['internal_revisions'],
        'public_revisions': recent_history['public_revisions'],
        'equivalences' : recent_history['equivalences'],
        'exports': recent_history['exports'],
        'imports': recent_history['imports'],
        'pending_migrations' : pending_migrations,
        'recent_history': simplejson.dumps(recent_history_for_json),
        }
    self.response.out.write(
        base.RenderTemplate('project.html', template_values))
    MaybePrintProfilingData(self.response)


  def PrettyPrintProjectConfigJson(self, config):
    return ('<pre>' +
            self.PrettyPrintProjectConfigJsonHelper(config) +
            '</pre>')

  def PrettyPrintProjectConfigJsonHelper(self, json, key_stack=None):
    if not key_stack:
      key_stack = []

    result = []

    if isinstance(json, list):
      # Format an Array
      result.append('[')
      for value in json:
        result.append(
            self.PrettyPrintProjectConfigJsonHelper(value, key_stack) + ',')
      result.append(']')
    elif isinstance(json, dict):
      # Format an object
      result.append('{')
      for key, value in json.iteritems():
        new_key_stack = key_stack + [key]
        result.append(
           key + ': ' + self.PrettyPrintProjectConfigJsonHelper(
               value, new_key_stack) + ',')
      result.append('}')
    else:
      value = cgi.escape(str(json))

      # Check for values with special formatting.
      if 'url' in key_stack:
        value = '<a href="%s">%s</a>' % (value, value)


      return value

    return '\n'.join(result).replace('\n', '\n  ')



class PendingMigrationsPage(webapp.RequestHandler):
  def get(self, project_name):
    project = GetProject(project_name)
    if not project:
      self.response.out.write(
          base.RenderTemplate('no-such-project.html',
                              {'project_name' : project_name}))
      self.error(404)
      return

    migrations = GetPendingMigrations(project)

    template_values = {
        'debug': base.DEBUG_MODE,
        'project_name': project_name,
        'migrations': migrations
        }
    self.response.out.write(
        base.RenderTemplate('pending_migrations.html', template_values))


class MigrationPage(webapp.RequestHandler):
  def get(self, migration_id):
    migration = LookupMigrationByMigrationId(int(migration_id))
    if not migration:
      self.response.out.write(
          base.RenderTemplate('no-such-migration.html',
                              {'migration_id' : migration_id}))
      self.error(404)
      return

    template_values = {
        'debug': base.DEBUG_MODE,
        'migration': migration,
        'comments': GetCommentsByMigration(migration),
        'result': self.request.get('result', '')
        }
    self.response.out.write(
        base.RenderTemplate('migration.html', template_values))


class MoeApiRequestHandler(webapp.RequestHandler):
  """Base class for implementing MOE API functions.

  These are not for human browsing on the webapp, but instead for consumption
    by a tool calling us. Thus, they return useful JSON information.

  One feature is that all calls return a dictionary in JSON, with the key
    (among others) 'succeeded' mapping to a boolean.
  """
  def _WriteJsonResult(self, error=None, error_message='', data=None,
                       redirect=None):
    """Write the result of an operation out."""
    if error:
      self.response.out.write(error_message)
      self.response.set_status(error)
      return

    output = {'data': data}
    json = simplejson.dumps(output).encode('utf-8')

    if self.request.get('out') == 'html':
      if redirect:
        self.redirect(redirect)
      else:
        self.response.out.write(
          base.RenderTemplate('main.html',
                              {'names': GetProjectNames(),
                               'json': json}))
    else:
      self.response.out.write(json)


  def _RequireProject(self):
    """Loads the project specified in the request's "project_name" param.

    Writes a JSON error and returns None on failure."""
    project_name = self.request.get('project_name')
    project = GetProject(project_name)
    if not project:
      message = 'No such project: %s' % project_name
      self._WriteJsonResult(error=404, error_message=message)

    return project


  def _RequireMigration(self):
    """Loads the migration object specified in the "migration_id" param.

    Writes a JSON error and returns None on failure."""
    migration_id = int(self.request.get('migration_id'))
    migration = LookupMigrationByMigrationId(migration_id)
    if not migration:
      message = 'Invalid migration id: %s' % migration_id
      self._WriteJsonResult(error=400, error_message=message)
      return None
    return migration


  def _RequireComment(self):
    """Loads the comment object specified in the "comment_id" param.

    Writes a JSON error and returns None on failure."""
    comment_id = int(self.request.get('comment_id'))
    q = db.Query(models.Comment).filter('comment_id =', comment_id)
    comment = q.get()
    if not comment:
      message = 'Invalid comment id: %s' % comment_id
      self._WriteJsonResult(error=400, error_message=message)
      return None
    return comment


  def _SetMigration(self, status):
    """Set data on a migration, creating a new migration object if necessary.

    Args:
      status: one of models.STATUS_VALUES, the migration status

    Args from http request:
      project_name: the name of the project
      changelog: the content of the migration's changelog
      diff: the content of the diff for the migration
      link: a (URL) link to the migration's diff content
      up_to_revision: The id of the change being migrated
      submitted_as: The id of the submitted migration
      direction: one of {export, import}, the direction of the migration
    """
    project = self._RequireProject()
    if not project:
      return

    direction = self.request.get('direction')
    if direction == 'export':
      source_repository = project.internal_repository
      dst_repository = project.public_repository
      direction_int = models.DIRECTION_EXPORT
    elif direction == 'import':
      source_repository = project.public_repository
      dst_repository = project.internal_repository
      direction_int = models.DIRECTION_IMPORT
    else:
      self._WriteJsonResult(
          error=400,
          error_message='Invalid migration direction: %s' % direction)

    up_to_revision = GetRevisionFromRequest(self.request,
                                            project, 'up_to_revision',
                                            repository=source_repository)

    submitted_as = GetRevisionFromRequest(self.request,
                                          project, 'submitted_as',
                                          repository=dst_repository)

    # Lookup Migration
    m = LookupMigrationByRevision(up_to_revision)
    if m and m.IsActive():
      m.submitted_as = submitted_as
      info = 'Edited'
    else:
      revisions_json = self.request.get('migrated_revisions')
      if revisions_json:
        revisions = NoteRevisions(revisions_json)
      else:
        revisions = []

      keyname = MigrationKeynameFromRevisionObj(up_to_revision)
      m = models.Migration(
          key_name=keyname,
          project=project,
          direction=direction_int,
          up_to_revision=up_to_revision,
          submitted_as=submitted_as,
          status=status,
          migrated_revisions=revisions,
          migration_id=models.NextId(),
          )
      info = 'Created'

    changelog = self.request.get('changelog', '')
    diff = self.request.get('diff', '')
    link = self.request.get('link', '')
    m.changelog = db.Text(changelog)
    if diff:
      m.diff = db.Text(diff)
    if link:
      m.link = db.Link(link)

    m_key = m.put()

    for revision in m.MigratedRevisions():
      if m_key not in revision.migrations:
        revision.migrations.append(m_key)
        revision.put()

    # TODO(dbentley): need a better way of doing this.
    # It's trying to record what migrations are new.
    # Instead, we're now moving to having it per-project, not per-process.
    # if info == 'Created':
    #   process = GetLastSeenProcess(project)
    #   if process:
    #     process.new_migrations.append(m.key().id())
    #     process.put()

    logging.info('%s migration. ID: %s', info, str(m.migration_id))

    self._WriteJsonResult(redirect='/project/%s' % m.project.name,
                          data={'migration_id': m.migration_id})


class UpdateProject(MoeApiRequestHandler):
  def post(self):
    project_name = self.request.get('project_name')
    project = GetProject(project_name)
    if not project:
      project = models.Project(name=project_name, default=None)
    if self.request.get('project_config'):
      project.config = db.Blob(str(self.request.get('project_config')))

    internal_r_info = self.request.get('internal_repository_info')
    if internal_r_info:
      info = simplejson.loads(internal_r_info)
      project.internal_repository = UpdateRepository(info=info)

    public_r_info = self.request.get('public_repository_info')
    if public_r_info:
      info = simplejson.loads(public_r_info)
      project.public_repository = UpdateRepository(info=info)

    project.put()

    # TODO(dbentley): remove this in 2010
    # Because of the major refactoring that landed in 11/2010, we have
    # some equivalences in the old schema but not the new one. In order to
    # move them to the new schema, though, we need the repository infos
    # in the new style that are computed on the client. Thus, for now, every
    # time we update a project, we try to copy the most recent old-style
    # equivalence into a new-style equivalence.
    q = (QueryProject(models.Equivalence, project)
         .order('-sequence'))
    e = q.get()
    if e and e.internal_revision and e.public_revision:
      internal_revision_obj = EnsureRevisionExists(e.internal_revision,
                                                   project.internal_repository)
      public_revision_obj = EnsureRevisionExists(e.public_revision,
                                                 project.public_repository)
      e2 = FindEquivalences(project,
                            internal_revision_obj=internal_revision_obj,
                            public_revision_obj=public_revision_obj)
      if not e2:
        e3 = models.Equivalence(project=project,
                                internal_revision_obj=internal_revision_obj,
                                public_revision_obj=public_revision_obj)
        e3.put()

    self._WriteJsonResult(data=project.DictForJson())


class ProjectApi(MoeApiRequestHandler):
  def get(self, project_name):
    project = GetProject(project_name)
    if not project:
      message = 'No such project: %s' % project_name
      self._WriteJsonResult(error=404, error_message=message)
      return

    self._WriteJsonResult(data=project.DictForJson())


class NoteEquivalence(MoeApiRequestHandler):
  def post(self):
    project = self._RequireProject()
    if not project:
      return

    internal_revision_obj = GetRevisionFromRequest(
        self.request, project, 'internal_revision')
    if not internal_revision_obj:
      self._WriteJsonResult(error=400, error_message='No internal_revision')
      return

    public_revision_obj = GetRevisionFromRequest(
        self.request, project, 'public_revision')
    if not public_revision_obj:
      self._WriteJsonResult(error=400, error_message='No public_revision')
      return

    e = FindEquivalences(project,
                         internal_revision_obj=internal_revision_obj,
                         public_revision_obj=public_revision_obj)

    if not e:
      e = models.Equivalence(
          project=project,
          internal_revision_obj=internal_revision_obj,
          public_revision_obj=public_revision_obj)
    else:
      # There should be only one such equivalence, but FindEquivalences has no
      # get() (as opposed to fetch()).
      if len(e) > 1:
        self._WriteJsonResult(
            error=400,
            error_message=
            'More than one equivalence exists. Internal: %s Public: %s' % (
                internal_revision_obj.rev_id, public_revision_obj.rev_id))
      e = e[0]

    verification_status = self.request.get('verification_status')
    if verification_status:
      e.verification_status = int(verification_status)

    e.put()

    self._WriteJsonResult(redirect='/project/%s' % project.name)


class FindEquivalencesPage(MoeApiRequestHandler):
  def get(self):
    project = self._RequireProject()
    if not project:
      return

    internal_revision_obj = GetRevisionFromRequest(
        self.request, project, 'internal_revision')

    public_revision_obj = GetRevisionFromRequest(
        self.request, project, 'public_revision')

    verification_status = self.request.get('verification_status')

    if (not internal_revision_obj and not public_revision_obj and
        verification_status is None):
      self._WriteJsonResult(
          error=400,
          error_message=
          'Must specify at least one of internal or private revision '
          'or verification status.')
      return

    equivalences = FindEquivalences(project,
                                    internal_revision_obj=internal_revision_obj,
                                    public_revision_obj=public_revision_obj,
                                    verification_status=verification_status)

    data = {
        'equivalences': [e.DictForJson() for e in equivalences],
        }
    self._WriteJsonResult(data=data)


class MigrationForRevision(MoeApiRequestHandler):
  def get(self):
    project = self._RequireProject()
    if not project:
      return

    r = GetRevisionFromRequest(self.request, project, 'revision')
    if not r:
      self._WriteJsonResult(data={'migration': None})
      return

    # then, query the DB
    q = (QueryProject(models.Migration, project)
         .filter('up_to_revision =', r))
    result = q.get()
    if result:
      result = result.DictForJson()

    # TODO(dbentley): should we also include when a revision is not the
    # up_to_revision, but instead just in migrated_revisions?

    self._WriteJsonResult(data={'migration': result})


class StartMigration(MoeApiRequestHandler):
  def post(self):
    self._SetMigration(status=models.STATUS_ACTIVE)


class NoteMigration(MoeApiRequestHandler):
  """Note a migration that happened.

  This is useful for when a user does a fix, and needs to describe to the
  MOE tools what he did. We have less information than in the case that MOE
  tools create a migration.
  """

  def post(self):
    self._SetMigration(status=models.STATUS_SUBMITTED)


class ApproveMigration(MoeApiRequestHandler):
  def post(self):
    migration = self._RequireMigration()
    if not migration:
      return
    migration_id = str(migration.migration_id)

    if migration.status != models.STATUS_ACTIVE:
      self._WriteJsonResult(error=400, error_message='migration %s is '
                            'not pending' % migration_id)
      return

    # If we got a changelog update, commit that.
    changelog = self.request.get('changelog', default_value=None)
    if changelog is not None:
      migration.AddChangelog(changelog)

    migration.status = models.STATUS_APPROVED
    migration.put()

    # If we got comment updates, commit them as well.
    comment_specs = self.GetCommentSpecs()
    if comment_specs:
      self.CommitCommentSpecs(comment_specs)

    redirect = self.request.get('redirect', '/project/%s'
                                % migration.project.name)
    self._WriteJsonResult(redirect=redirect)

  def GetCommentSpecs(self):
    """Returns a list of (id, text) tuples in the request"""
    comment_specs = []
    index = 0
    comment_id = self.TryGetCommentId(index)
    while comment_id is not None:
      comment_specs.append(
          (comment_id,
           self.request.get('comment_text_%d' % index)))
      index = index + 1
      comment_id = self.TryGetCommentId(index)

    return comment_specs

  def CommitCommentSpecs(self, comment_specs):
    """Commits a bunch of comment changes to the database.

    Tries to minimize the number of database calls.

    Args:
      comment_specs: A list of (id, text) pairs. All strings."""
    comment_ids = [int(spec[0]) for spec in comment_specs]

    # A map from comment ids to text contents.
    comment_dict = {}
    for spec in comment_specs:
      comment_dict[spec[0]] = spec[1]

    q = db.Query(models.Comment).filter('comment_id IN ', comment_ids)
    comments = list(q.fetch(len(comment_ids)))
    for comment in comments:
      new_text = comment_dict[str(comment.comment_id)]
      if comment.text is not new_text:
        comment.text = new_text
        comment.put()

  def TryGetCommentId(self, index):
    """Checks if the request contains a comment ID at the given index."""
    return self.request.get('comment_id_%d' % index, default_value=None)


class UnapproveMigration(MoeApiRequestHandler):
  def post(self):
    migration = self._RequireMigration()
    if not migration:
      return
    id = str(migration.migration_id)

    if migration.status != models.STATUS_APPROVED:
      self._WriteJsonResult(error_message='migration %s is not approved' % id)
      return

    migration.status = models.STATUS_ACTIVE
    migration.put()
    self._WriteJsonResult(redirect='/project/%s' % migration.project.name)


class FinishMigration(MoeApiRequestHandler):
  def post(self):
    migration = self._RequireMigration()
    if not migration:
      return

    project = migration.project
    direction = migration.direction
    if direction == models.DIRECTION_EXPORT:
      repository = models.PUBLIC
    elif direction == models.DIRECTION_IMPORT:
      repository = models.INTERNAL
    else:
      raise Error('Invalid direction: %s', repr(direction))

    submitted_as = GetRevisionFromRequest(
        self.request, project, 'submitted_as')

    if not submitted_as:
      msg = 'Could not determine a submitted_as to finish migration with.'
      self._WriteJsonResult(error=400, error_message=msg)

    migration.status = models.STATUS_SUBMITTED
    migration.submitted_as = submitted_as

    migration.put()

    redirect = self.request.get('redirect', '/project/%s'
                                % migration.project.name)
    self._WriteJsonResult(redirect=redirect)


class CancelMigration(MoeApiRequestHandler):
  def post(self):
    migration = self._RequireMigration()
    if not migration:
      return
    migration.status = models.STATUS_CANCELED
    migration.put()
    redirect = self.request.get('redirect', '/project/%s'
                                % migration.project.name)
    self._WriteJsonResult(redirect=redirect)


class MigrationInfo(MoeApiRequestHandler):
  def get(self):
    migration = self._RequireMigration()
    if not migration:
      return

    abbreviated = self.request.get('abbreviated', u'True') == u'True'
    data = migration.DictForJson(abbreviated=abbreviated)

    self._WriteJsonResult(data=data)


class FindMigration(MoeApiRequestHandler):
  def get(self):
    project = self._RequireProject()
    if not project:
      return

    up_to_revision = GetRevisionFromRequest(
        self.request, project, 'up_to_revision')

    m = LookupMigrationByRevision(up_to_revision)

    abbreviated = self.request.get('abbreviated', u'True') == u'True'
    if m:
      data = m.DictForJson(abbreviated=abbreviated)
    else:
      data = None
    self._WriteJsonResult(data=data)


class UpdateMigrationDiff(MoeApiRequestHandler):
  def post(self):
    migration = self._RequireMigration()
    if not migration:
      return

    diff = self.request.get('diff', '')
    link = self.request.get('link', '')
    if diff:
      migration.diff = db.Text(diff)
    if link:
      migration.link = db.Link(link)
    migration.put()
    self._WriteJsonResult()


class EditChangelog(MoeApiRequestHandler):
  def post(self):
    migration = self._RequireMigration()
    if not migration:
      return
    changelog = self.request.get('changelog')
    migration.AddChangelog(changelog)
    migration.put()
    result = 'Changelog%20saved.'
    self._WriteJsonResult(redirect='/migration/%s?result=%s' %
                          (str(migration.migration_id), result))


class StartProcess(MoeApiRequestHandler):
  def post(self):
    project = self._RequireProject()
    if not project:
      return

    require_lock = self.request.get('require_lock') == u'True'

    last = GetLastSeenProcess(project)
    if require_lock and last and last.IsRunning():
      message = ('Project already has a running process at %s, which '
                 'was last seen at %s' % (last.process_id, last.last_seen))
      self._WriteJsonResult(error=400, error_message=message)
      return

    process = models.Process(project=project,
                             process_id=self.request.get('process_id'),
                             running=True)
    process.put()
    self._WriteJsonResult()


class UpdateProcess(MoeApiRequestHandler):
  def post(self):
    project = self._RequireProject()
    if not project:
      return

    project_name = project.name
    process_id = self.request.get('process_id')
    process = GetProcess(project, process_id)
    if not process:
      message = 'No process %s for project %s' % (process_id, project_name)
      self._WriteJsonResult(error=404, error_message=message)
      return
    if not process.running:
      message = 'Process %s no longer running' % process_id
      self._WriteJsonResult(error=400, error_message=message)
      return

    process.put()
    self._WriteJsonResult()


class EndProcess(MoeApiRequestHandler):
  def post(self):
    project = self._RequireProject()
    if not project:
      return

    project_name = project.name
    process_id = self.request.get('process_id')
    process = GetProcess(project, process_id)
    if not process:
      message = 'No process %s for project %s' % (process_id, project_name)
      self._WriteJsonResult(error=404, error_message=message)
      return

    if process.running:
      process.end_time = datetime.datetime.utcnow()
      if process.new_migrations:
        SendPendingMigrationEmail(project)
    process.running = False
    process.put()
    self._WriteJsonResult()


class GetLastProcess(MoeApiRequestHandler):
  def get(self):
    project = self._RequireProject()
    if not project:
      return

    last = GetLastSeenProcess(project)

    if last:
      data = last.DictForJson()
    else:
      data = None
    self._WriteJsonResult(data=data)


def GetRecentRevisions(repository, project=None, num_revisions=20):
  """Get Recent Revisions.

  Args:
    repository: models.Repository, the repository whose revisions to get
      we ought.
    project: models.Project, restrict the query to a given project.
    num_revisions: int, maximum number of revisions to fetch.

  Returns:
    list of models.Revisions
  """
  q = db.Query(models.Revision).filter('repository_name =', repository.name)
  # TODO(nicksantos): filter by project once the revisions have projects.
  # But talk to dbentley to make sure that we really want to do this.
  # if project:
  #    q.filter('project =', project)

  # TODO(dbentley): eventually, it would be great to use the partial
  # order implied in the actual VCS.
  q.order('-time')
  q.order('-first_seen')
  return list(q.fetch(num_revisions))


class GetRevisions(MoeApiRequestHandler):
  def get(self):
    repository_name = self.request.get('repository')
    repository = GetRepository(repository_name)
    if not repository:
      message = 'No such repository: %s' % repository_name
      self._WriteJsonResult(error=404, error_message=message)
      return

    num_revisions = int(self.request.get('num_revisions', 100))
    results = [r.DictForJson() for r in
               GetRecentRevisions(repository, num_revisions=num_revisions)]
    self._WriteJsonResult(data={'revisions': results})


class AddComment(MoeApiRequestHandler):
  def post(self):
    migration = self._RequireMigration()
    if not migration:
      return

    req = self.request
    comment = models.Comment(
        comment_id=models.NextId(),
        migration=migration,
        file=req.get('file'),
        date=req.get('date'),
        lineno=req.get('lineno'),
        author=req.get('author'),
        text=req.get('text'))
    comment.put()

    self._WriteJsonResult(
        redirect='/migration/%s' % str(migration.migration_id),
        data={'comment_id': comment.comment_id})


class EditComment(MoeApiRequestHandler):
  def post(self):
    comment = self._RequireComment()
    if not comment:
      return

    comment.text = self.request.get('comment_text')
    comment.put()

    self._WriteJsonResult(
        redirect='/migration/%s' %
        str(comment.migration.migration_id))


class GetComments(MoeApiRequestHandler):
  def get(self):
    migration = self._RequireMigration()
    if not migration:
      return

    comments = GetCommentsByMigration(migration)
    self._WriteJsonResult(
        redirect='/migration/%s' % str(migration.migration_id),
        data={'comments': [c.DictForJson() for c in comments]})


class NoteRevisionsPage(MoeApiRequestHandler):
  def post(self):
    revisions_json = self.request.get('revisions')
    NoteRevisions(revisions_json)
    self._WriteJsonResult(data={})


def NoteRevisions(revisions_json):
  """Note these revisions in the database.

  Args:
    revisions_json: str, a json string that loads to an array of dictionaries
                    that contain information about the revision.

  Returns:
    seq of strings of revision ids
  """
  rev_infos = simplejson.loads(revisions_json)
  result = []
  for rev_info in rev_infos:
    r = EnsureRevisionExists(
        rev_id=rev_info['rev_id'],
        repository=GetRepository(rev_info['repository_name']))
    r.author = rev_info['author']
    if 'time' in rev_info:
      r.time = datetime.datetime.strptime(rev_info['time'],
                                          '%Y-%m-%d %H:%M:%S')
    r.info = rev_info
    result.append(r.put())
  return result


class RecentHistoryPage(MoeApiRequestHandler):
  def get(self):
    project_name = self.request.get('project_name')
    project = GetProject(project_name)
    history = GetRecentHistory(project)

    result = {}
    for k, v in history.iteritems():
      result[k] = [i.DictForJson() for i in v]

    self._WriteJsonResult(data=result)


def GetRecentHistory(project):
  """Get the recent history of a project."""
  internal_revisions = GetRecentRevisions(
      project.internal_repository, project=project)
  public_revisions = GetRecentRevisions(
      project.public_repository, project=project)

  equivalences = set()
  exports = set()
  imports = set()
  if internal_revisions:
    equivalences.update(
        FindEquivalencesList(project, internal_revisions=internal_revisions))
    exports = set(LookupMigrationsByRevisions(project, internal_revisions))

  if public_revisions:
    equivalences.update(
        FindEquivalencesList(project, public_revisions=public_revisions))
    imports = set(LookupMigrationsByRevisions(project, public_revisions))

  return {'internal_revisions': internal_revisions,
          'public_revisions': public_revisions,
          'equivalences': equivalences,
          'exports': exports,
          'imports': imports,
          }
