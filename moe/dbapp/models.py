#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved

from google.appengine.ext import db

import datetime


def _ModelToDictForJson(model_obj):
  """Return the data of an app engine model as a dict.

  Args:
    model_obj: a model object to be serialized

  Returns:
    an object suitable for simplejson.dumps'ing

  Note:
    this is generic, but if the object has unserializable
    properties this will not be so useful.
  """
  result = {}
  for key in model_obj.properties():
    value = getattr(model_obj, key)
    if hasattr(value, 'DictForJson'):
      value = value.DictForJson()
    result[key] = value
  return result

class Repository(db.Model):
  name = db.StringProperty()
  parent_repository = db.StringProperty()

  def DictForJson(self):
    return {'name': self.name}


class Project(db.Model):
  name = db.StringProperty(required=True)
  config = db.BlobProperty()
  highest_equivalence = db.IntegerProperty(default=0)
  highest_migration = db.IntegerProperty(default=0)
  internal_repository = db.ReferenceProperty(
      Repository, collection_name='project_internal_set')
  public_repository = db.ReferenceProperty(
      Repository, collection_name='project_public_set')

  def DictForJson(self):
    return _ModelToDictForJson(self)


PROCESS_TIMEOUT = datetime.timedelta(minutes=20)
TIME_FORMAT = '%X %x'


class Process(db.Model):
  project = db.ReferenceProperty(Project, required=True)
  process_id = db.StringProperty(required=True)
  running = db.BooleanProperty(required=True)
  start_time = db.DateTimeProperty(auto_now_add=True)
  last_seen = db.DateTimeProperty(auto_now=True)
  end_time = db.DateTimeProperty()
  new_migrations = db.ListProperty(int)

  def IsTimedOut(self):
    return (datetime.datetime.utcnow() - self.last_seen >
            PROCESS_TIMEOUT)

  def IsRunning(self):
    return self.running and not self.IsTimedOut()

  def StartTimeString(self):
    return self.start_time.strftime(TIME_FORMAT)

  def LastSeenString(self):
    return self.last_seen.strftime(TIME_FORMAT)

  def EndTimeString(self):
    if self.running:
      return 'Process still running'
    return self.end_time.strftime(TIME_FORMAT)

  def ElapsedTime(self):
    if self.running:
      return self.last_seen - self.start_time
    return self.end_time - self.start_time

  def ElapsedTimeString(self):
    return str(self.ElapsedTime())

  def DictForJson(self):
    return { 'project_name': self.project.name,
             'process_id': self.process_id,
             'running': self.running,
             'start_time': str(self.start_time),
             'last_seen': str(self.last_seen),
             'new_migrations': self.new_migrations }


# enum for direction
DIRECTION_EXPORT = 0
DIRECTION_IMPORT = 1
DIRECTION_VALUES = [DIRECTION_EXPORT, DIRECTION_IMPORT]
DIRECTION_NAMES = ['export', 'import']

# enum for status
STATUS_ACTIVE = 0
STATUS_SUBMITTED = 1
STATUS_CANCELED = 2
STATUS_APPROVED = 3
STATUS_VALUES = [STATUS_ACTIVE, STATUS_SUBMITTED, STATUS_CANCELED,
                 STATUS_APPROVED]
STATUS_NAMES = ['Pending', 'Submitted', 'Canceled', 'Approved']


INTERNAL=0
PUBLIC=1

class Revision(db.Model):
  repository_name = db.StringProperty()
  rev_id = db.StringProperty()
  author = db.StringProperty()
  time = db.DateTimeProperty()
  migrations = db.ListProperty(db.Key)
  first_seen = db.DateTimeProperty(auto_now_add=True)

  def DictForJson(self):
    data = {'rev_id': self.rev_id,
            'author': self.author or '',
            'repository_name': self.repository_name
            }
    if self.time:
      data['time'] = self.time.strftime('%Y-%m-%d %H:%M:%S')
    return data


class Equivalence(db.Model):
  project = db.ReferenceProperty(Project, required=True)
  internal_revision_obj = db.ReferenceProperty(
      Revision, collection_name='internal_set')
  public_revision_obj = db.ReferenceProperty(
      Revision, collection_name='public_set')

  # Old code
  internal_revision = db.StringProperty()
  public_revision = db.StringProperty()
  sequence = db.IntegerProperty()

  def DictForJson(self):
    data = {
        'internal_revision': self.internal_revision_obj.DictForJson(),
        'public_revision': self.public_revision_obj.DictForJson(),
        }
    return data


class Migration(db.Model):
  project = db.ReferenceProperty(Project, required=True)
  direction = db.IntegerProperty(required=True, choices=DIRECTION_VALUES)
  up_to_revision = db.ReferenceProperty(Revision,
                                        collection_name='up_to_set')
  status = db.IntegerProperty(required=True, choices=STATUS_VALUES)
  submitted_as = db.ReferenceProperty(Revision,
                                      collection_name='submitted_as_set')
  # TODO(dbentley): should there be applied_against

  # Extra metadata that is handy
  migration_id = db.IntegerProperty()
  changelog = db.TextProperty()
  diff = db.TextProperty()
  link = db.LinkProperty()
  last_seen = db.DateTimeProperty(auto_now=True)
  migrated_revisions = db.ListProperty(db.Key, default=None)

  # For backwards compatibility
  equivalence = db.ReferenceProperty(Equivalence)
  start_migrated_revision = db.StringProperty()
  end_migrated_revision = db.StringProperty()
  base_revision = db.StringProperty()
  submitted_revision = db.StringProperty()

  def DirectionAsString(self):
    return DIRECTION_NAMES[self.direction]

  def StatusAsString(self):
    return STATUS_NAMES[self.status]

  def IsActive(self):
    return self.IsPending() or self.IsApproved()

  def IsPending(self):
    return self.status == STATUS_ACTIVE

  def IsSubmitted(self):
    return self.status == STATUS_SUBMITTED

  def IsCanceled(self):
    return self.status == STATUS_CANCELED

  def IsApproved(self):
    return self.status == STATUS_APPROVED

  def MigratedRevisions(self):
    return [Revision.get(key) for key in self.migrated_revisions]

  def AddChangelog(self, changelog):
    """Normalize a changelog and stick it in the migration model."""
    # remove carriage returns which are introduced by windows.
    self.changelog = db.Text(changelog.replace('\r', ''))

  def DictForJson(self, abbreviated=False):
    """Create a dict suitable for returning as JSON."""

    data = {
        'migration_id': self.migration_id,
        'project_name': self.project.name,
        'direction': DIRECTION_NAMES[self.direction],
        'status': self.StatusAsString(),
        'up_to_revision': self.up_to_revision.DictForJson(),
        'submitted_as':
          self.submitted_as.DictForJson() if self.submitted_as else None,
        }

    if not abbreviated:
      data.update({
          'changelog': self.changelog,
          'diff' : self.diff,
          'link' : self.link,
          'revisions': [Revision.get(key).DictForJson()
                        for key in self.migrated_revisions],
          })

    return data


class Comment(db.Model):
  comment_id = db.IntegerProperty()

  # The migration that this comment is associated with.
  migration = db.ReferenceProperty(Migration)

  # The editable text.
  text = db.TextProperty()

  # MOE-db should treat these properties as readonly,
  # and doesn't bother converting them to rich types.
  file = db.StringProperty()
  date = db.StringProperty()
  lineno = db.StringProperty()
  author = db.StringProperty()

  def DictForJson(self, abbreviated=False):
    """Create a dict suitable for returning as JSON."""
    return {
      'comment_id': self.comment_id,
      'migration_id': self.migration.migration_id,
      'file': self.file,
      'date': self.date,
      'lineno': self.lineno,
      'author': self.author,
      'text': self.text
    }


class Counter(db.Model):
  counter = db.IntegerProperty(default=0)


def NextId():
  c = Counter.get_by_key_name('singleton')
  if not c:
    c = Counter(key_name='singleton',
                counter=0)
    c.put()
  result = c.counter
  c.counter += 1
  c.put()
  return result
