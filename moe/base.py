#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.

"""Utilities handy for dealing with codebases."""

__author__ = 'dbentley@google.com (Dan Bentley)'


import errno
import os
import re
import stat
import subprocess
import sys
import tarfile
import tempfile

import pytz

from google.apputils import datelib
import gflags as flags
import logging

FLAGS = flags.FLAGS

flags.DEFINE_string('project', '', 'Name of the MOE project')
flags.DEFINE_string('project_config_file', '',
                    'Path to the MOE project configuration file')
flags.DEFINE_string('public_username', '',
                    'Username for public repository client')
flags.DEFINE_string('public_password', '',
                    'Password for public repository client')


flags.DEFINE_boolean('debug_dry_run', False,
                     "Show what would be done, but don't make any changes to "
                     'the DB or any VCS. NOTE: this is only for debugging; do '
                     'not use if you just want to avoid automatically pushing '
                     'to your external repo')


# Commit strategy enumeration
LEAVE_PENDING = 'leave_pending'
COMMIT_LOCALLY = 'commit_locally'
COMMIT_REMOTELY = 'commit_remotely'

COMMIT_STRATEGIES = [LEAVE_PENDING, COMMIT_LOCALLY, COMMIT_REMOTELY]


# Merge strategy enumeration
ERROR = 'error'
OVERWRITE = 'overwrite'
MERGE = 'merge'

MERGE_STRATEGIES = [ERROR, OVERWRITE, MERGE]

# Note: this section must be kept in sync with MOE db's models.py

# Different ways to refer to elements and the set of repositories
INTERNAL = 0
PUBLIC = 1
INTERNAL_STR = 'internal'
PUBLIC_STR = 'public'
REPOSITORIES = [INTERNAL_STR, PUBLIC_STR]
PROJECT_SPACES = [INTERNAL_STR, PUBLIC_STR]


# enum for Equivalence Verification
# Equivalences start as unverified. Then we can either verify them, or find
# that they are invalid.
VERIFICATION_UNVERIFIED = 0
VERIFICATION_VERIFIED = 1
VERIFICATION_INVALID = 2

VERIFICATION_NAMES = ['Unverified', 'Verified', 'Invalid']


class Error(Exception):
  """Base class for MOE exceptions."""


class CodebaseCreationError(Error):
  """There was an error attempting to create a codebase."""
  pass


class InvalidClientError(Error):
  """A SourceControlClient could not be set up because it was invalid."""
  pass


class HttpError(Error):
  """Error in making an http request."""
  def __init__(self, s, contents=''):
    Error.__init__(self, s)
    self.contents = contents


class Correspondence(object):
  """A Correspondence is a relation between an internal and public revision."""

  # TODO(dbentley): should probably take base.Revision's; not str's
  def __init__(self, internal_revision, public_revision):
    self.internal_revision = internal_revision
    self.public_revision = public_revision

  def __eq__(self, other):
    return (self.internal_revision == other.internal_revision and
            self.public_revision == other.public_revision)

  def __str__(self):
    return 'Correspondence("%s", "%s")' % (self.internal_revision,
                                           self.public_revision)

  def __hash__(self):
    return hash(str(self))

  def __repr__(self):
    return '<MOE Correspondence: %s, %s>' % (
        self.internal_revision, self.public_revision)


class Migration(object):
  """A Migration is an attempt to move code from one repository to another."""
  # enum for direction (matches models.Migration)
  IMPORT = 'import'
  EXPORT = 'export'
  DIRECTION_VALUES = [IMPORT, EXPORT]

  # enum for status (matches models.Migration)
  ACTIVE = 'Pending'
  SUBMITTED = 'Submitted'
  CANCELED = 'Canceled'
  APPROVED = 'Approved'
  STATUS_VALUES = [ACTIVE, SUBMITTED, CANCELED, APPROVED]

  def __init__(self, migration_id, direction, status,
               up_to_revision, submitted_as=None,
               changelog='', diff='', link='',
               revisions=None,
               **unused_kwargs):
    """Construct.

    Args:
      migration_id: str, the unique string identifying this migration
      direction: str in DIRECTION_VALUES, the direction of migration
      status: str in STATUS_VALUES, the current status of the migration
      up_to_revision: Revision, the revision migrated
      submitted_as: Revision, the revision the migration has been submitted
                         as, or None if it has not yet been submitted
      changelog: str, the changelog describing this CL/commit
      diff: str, the diff of the changes in the migration
      link: str, a URL link to the changes in the migration
      revisions: seq of (base.Revision or dict of str->str)
    """
    self.migration_id = migration_id
    self.direction = direction
    self.status = status
    self.up_to_revision = self._Revision(up_to_revision)
    self.submitted_as = self._Revision(submitted_as)
    self.changelog = changelog or ''
    self.diff = diff or ''
    self.link = link or ''
    self.revisions = [self._Revision(r) for r in revisions or []]

  def _Revision(self, data):
    """Turn possibly-a-dictionary/possibly-a-revision into a revision."""
    if isinstance(data, dict):
      return Revision(data['rev_id'],
                      repository_name=data.get('repository_name'),
                      author=data.get('author'))
    else:
      return data

  def Dict(self):
    """Return a dictionary representation of this migration."""
    return dict(
        migration_id=self.migration_id,
        direction=self.direction,
        status=self.status,
        up_to_revision=self.up_to_revision.Dump(),
        submitted_as=(self.submitted_as and self.submitted_as.Dump() or None),
        changelog=self.changelog,
        diff=self.diff,
        link=self.link,
        revisions=[r.Dump() for r in self.revisions],
        )

  def __eq__(self, other):
    if not isinstance(other, Migration):
      return False
    return self.Dict() == other.Dict()

  def __hash__(self):
    return hash(str(self.up_to_revision))

  def __repr__(self):
    return '<MOE Migration: up_to_revision "%s">' % (
        self.up_to_revision.rev_id)


def MakeDir(path):
  """Make dir, succeed if it already exists."""
  try:
    os.makedirs(path)
  except OSError, e:
    if e.errno != errno.EEXIST:
      raise


def PossiblyExpandCodebase(codebase, base_temp_dir, cache=None):
  """Turn possibly-compressed codebase into a directory.

  Args:
    codebase: str, path to the codebase pre-expansion
    base_temp_dir: str, path to temporary directory
    cache: dict of str->str, cache of path->expanded path

  Returns:
    string, the location of the codebase after expansion

  Raises:
    Error: if error occurred.
  """
  if cache is None:
    cache = {}
  if os.path.isdir(codebase):
    return os.path.abspath(codebase)
  if codebase.endswith('.tar'):
    if codebase in cache:
      return cache[codebase]
    if not base_temp_dir:
      raise Error('No temp_dir specified, but needed')
    temp_dir = tempfile.mkdtemp(dir=base_temp_dir, prefix='codebase_')
    # expand tar into temporary directory, return that.
    codebase_tar = tarfile.TarFile(codebase)
    codebase_tar.errorlevel = 2
    members = codebase_tar.getmembers()
    for m in members:
      codebase_tar.extract(m, path=temp_dir)
      # make sure file is writeable
      os.chmod(os.path.join(temp_dir, m.name), m.mode | stat.S_IWUSR)
    codebase_tar.close()
    cache[codebase] = os.path.abspath(temp_dir)
    return cache[codebase]
  if codebase.endswith('.zip'):
    if codebase in cache:
      return cache[codebase]
    if not base_temp_dir:
      raise Error('No temp_dir specified, but needed')
    temp_dir = tempfile.mkdtemp(
        dir=base_temp_dir,
        prefix=os.path.splitext(os.path.basename(codebase))[0]+'.')
    print 'Unzipping %s into %s' % (codebase, temp_dir)
    p = subprocess.Popen(['unzip', '-qq', codebase, '-d', temp_dir])
    p.wait()
    if p.returncode:
      raise Error('Codebase %s could not be unzipped' % codebase)
    cache[codebase] = os.path.abspath(temp_dir)
    return cache[codebase]
  # TODO(dbentley): it's also easy to add support for gz and bz2, but
  # these have not been needed yet.
  raise Error('Codebase %s is not a directory, .tar, or .zip' %
              codebase)


def IsExecutable(path):
  """Determine whether path is executable."""
  return os.access(path, os.X_OK)


def SetExecutable(path):
  """Make path (an absolute path) executable."""
  mode = os.stat(path).st_mode
  if mode & stat.S_IRUSR:
    mode |= stat.S_IXUSR
  if mode & stat.S_IRGRP:
    mode |= stat.S_IXGRP
  if mode & stat.S_IROTH:
    mode |= stat.S_IXOTH
  os.chmod(path,mode)


def FindBinaryOnPath(binary_name, path):
  """Find a binary on a path, a la which(1).

  Args:
    binary_name: str, the (relative) name of the binary to invoke
    path: list of str, the path to resolve against

  Returns:
    str
  """
  for p in path:
    potential = os.path.join(p, binary_name)
    if IsExecutable(potential):
      return potential
  return ''


def EnvironPath():
  """Return, as list of str, the path from the environment."""
  return os.environ.get('PATH', '').split(':')


class MoeReport(object):
  """A report for a run of a MOE tool.

  This is useful so that a human may quickly digest what happened in the run.

  During execution, MOE code may add:
    1) Step, indicating work the program did.
    2) Todo, indicating action items the user must take care of.

  As an example of the difference:
    1) Step would be creating a change
    2) Todo would be to submit the change
  """

  class Step(object):
    """A step represents a step in the execution of a MOE tool."""

    def __init__(self, name, cmd=''):
      self.name = name
      self.cmd = cmd
      self.result = ''
      self._return_code = 0

    def Output(self, step_num=None):
      """Generate the output for this step, as if it were step 'step_num'."""
      lines = []
      if step_num is None:
        lines.append('==== BEGINNING: %s' % self.name)
      else:
        lines.append('==== %d) %s' % (step_num, self.name))
      if self.cmd:
        lines.append('[ %s ]' % self.cmd)
      if self.result:
        lines.append('RESULTS: %s' % self.result)
      lines.append('')
      return '\n'.join(lines)

    def SetResult(self, result):
      """Set the result of this step.

      This is useful so we can report on beginning a step (which is before
        the result is known).

      Args:
        result: str, the result
      """
      self.result = result

  class Todo(object):
    """Represents work the user should do before proceeding."""

    def __init__(self, text):
      self.text = text

    def Output(self):
      lines = []
      lines.append('*) %s' % self.text)
      return '\n'.join(lines)

  def __init__(self):
    self._steps = []
    self._todos = []
    self._return_code = 0

  def GetReturnCode(self):
    return self._return_code

  def SetReturnCode(self, return_code):
    self._return_code = return_code

  def AddStep(self, name, cmd, cmd_args=None):
    """Create and add a step of a MOE tool run. Returns the step.

    Args:
      name: str, a short, human-readable name for the step
      cmd: str, the short name for the MOE tool being invoked
      cmd_args: dict of str->str, the flags to the command

    Returns:
      Step; the created step
    """
    if cmd_args:
      cmd = cmd + ' ' + ' '.join([
          '--%s=%s' % (k, str(v)) for (k, v) in cmd_args.iteritems()])
    step = self.Step(name, cmd)
    self._steps.append(step)
    print step.Output()
    return step

  def AddTodo(self, text):
    """Create and add a TODO of a MOE tool run."""
    self._todos.append(self.Todo(text))

  def PrintSummary(self):
    """Print a report of this MOE tool run."""
    print
    print '|||| RUN COMPLETE. RECAP:'
    for n, step in enumerate(self._steps):
      print step.Output(n+1)

    if self._todos:
      print '|||| ACTION ITEMS'
      for todo in self._todos:
        print todo.Output()


class CodebaseClient(object):
  """The client which interfaces with a codebase.

  Can be used to make several editors.
  """

  def Checkout(self):
    """Ensure this client is at the right revision for this repository.

    If it does not already exist, check it out.
    If it does, update it.
    """
    raise NotImplementedError

  def MakeEditor(self, migration_strategy, revisions=None):
    """Make an editor for this client.

    Args:
      migration_strategy: base.MigrationStrategy
      revisions: list of Revision, the revisions for the editor to migrate
                 if known

    Returns:
      CodebaseEditor
    """
    raise NotImplementedError


class CodebaseEditor(object):
  """Allows editing (i.e. both reading and writing) of a codebase.

  To do this requires some knowledge of the current state of the
  codebase, and methods to change the state.

  It may be backed by a simple directory, by a source control client,
  or it may offer a synthesized view of a codebase that is backed by
  part of a source control repository and some generated files.
  """

  def Walk(self):
    """Walks the codebase for existent files. Returns a seq of str."""
    raise NotImplementedError

  def Checkout(self):
    """Check out code as needed."""
    raise NotImplementedError

  def PutFile(self, relative_dest, src):
    """Make relative_dest have contents/properties of src."""
    raise NotImplementedError

  def AbsolutePath(self, relative_path):
    """Returns an absolute path to the file at relative_path."""
    raise NotImplementedError

  # TODO(dbentley): this could be better named.
  def ChangesMade(self):
    """Returns whether any changes been made to this client.

    May not be called before FinalizeChange.
    """
    raise NotImplementedError

  def FinalizeChange(self, commit_message, report):
    """Finalize the change.

    Args:
      commit_message: str, the message to describe the commit
      report: MoeReport, the report to output to
    """
    raise NotImplementedError

  def CommitChange(self, report):
    """Commit the change.

    Args:
      report: MoeReport, the report to output to

    Returns:
      str, the revision id of the new revision, or None if no new
      revision was completed
    """
    raise NotImplementedError

  def Diff(self):
    """Return a diff of the changes made in this client.

    May not be called before FinalizeChange.
    """
    raise NotImplementedError

  def Link(self):
    """Return a link to the changes made in this client.

    May not be called before FinalizeChange.
    """
    raise NotImplementedError

  def Root(self):
    """Return a path that's the conceptual root of the codebase.

    This path should be useful for a user to examine what's happening,
      and has no semantic meaning.
    """
    raise NotImplementedError


class SourceControlRepository(object):
  """An interface for interacting with a Source Control system's metadata."""

  def Export(self, directory, revision):
    """Export repository at revision into directory."""
    raise NotImplementedError

  def MakeClient(self, directory, username='', password=''):
    """Make a client for editing this codebase.

    Args:
      directory: str, the directory to make the client in
      username: str
      password: str

    Returns:
      CodebaseClient
    """
    raise NotImplementedError

  def GetHeadRevision(self, highest_rev_id=None):
    """Returns the id of the head revision (as a str).

    Args:
      highest_rev_id: the rev_id of the maximum revision to allow.

    Returns:
      str, the id of the highest revision <= highest_rev_id, or None if
      highest_rev_id is invalid
    """
    raise NotImplementedError

  def RecurUntilMatchingRevision(self, starting_revision, matcher):
    """Find revisions from head until a predicate is matched.

    For instance, if we wanted to find the current sequence of changes by
    dbentley@, we would call:
      RecurUntilMatchingRevision(lambda r: r.Author() == 'dbentley')

    This is useful because MOE often wants to operate on a range of changes
    "since" some concept. E.g., the revisions from head to the last
    equivalence.

    Returns newest revisions first.

    Inclusive of the matching revision.
    (Corollary: the returned sequence will always have at least one Revision.)

    TODO(dbentley): change this from returning a list to a graph, to better
      support DVCS'es.

    Args:
      matcher: func of Revision -> bool
      starting_revision: str, id of the revision to start at

    Returns:
      seq of Revision

    Raises:
      base.Error if no such revision found in a reasonable history
    """
    raise NotImplementedError

  def MakeRevisionFromId(self, id):
    """Create a Revision for the revision with this ID.

    This is necessary as a placeholder, because we are trying to pass around
      Revision's more and str's less.
    """
    raise NotImplementedError


MOE_MIGRATION_RE = re.compile(r'MOE_MIGRATION=(\w+)')


class Revision(object):
  """Represents one revision in a codebase, along with associated metadata.

  For internal revisions, the changelog is the scrubbed version.
  """

  def __init__(self, rev_id, repository_name='',
               changelog='', author='', time=None,
               scrubbed_log='', single_scrubbed_log='',
               pre_approved=False):
    """Create a Revision object.

    Args:
      rev_id: str, the identification string/number of the revision
      repository_name: str, the name of the repository this lives in
      changelog: str, the revision's changelog
      author: str, the author of the revision
      time: datelib.Timestamp, the time at which the revision was made, or a
            str representation of this time
      scrubbed_log: str, the revision's log as we think it could appear publicly
      single_scrubbed_log: str, the revision's log as it could appear publicly
                           if this is the only revision in the migration
      pre_approved: bool, whether this revision is pre-approved for migration
    """
    self.rev_id = rev_id
    self.repository_name = repository_name
    self.changelog = changelog
    self.author = author
    if time and isinstance(time, basestring):
      time = datelib.Timestamp.FromString(time)
    self.time = time
    self.migration = None
    moe_migration = MOE_MIGRATION_RE.search(changelog)
    if moe_migration:
      self.migration = moe_migration.group(1)

    self.scrubbed_log = scrubbed_log or changelog
    self.single_scrubbed_log = single_scrubbed_log or self.scrubbed_log
    self.pre_approved = pre_approved

  def __str__(self):
    lines = ['Revision: %s' % self.rev_id]
    if self.scrubbed_log:
      lines.append('Changelog: %s' % self.scrubbed_log)
    elif self.changelog:
      lines.append('Changelog: %s' % self.changelog)
    if self.author:
      lines.append('Author: %s' % self.author)
    if self.time:
      lines.append('Time: %s' % self.time.strftime('%Y-%m-%d %H:%M:%S'))
    return '\n'.join(lines) + '\n'

  def __eq__(self, other):
    return str(self) == str(other)

  def __hash__(self):
    return hash(str(self))

  def __repr__(self):
    return '<MOE Revision: %s>' % self.rev_id

  def Dump(self):
    """Dump the Revision in a format ready for JSON'ing.

    Returns:
      dict of str -> JSON-able object
    """
    data = {'rev_id': self.rev_id,
            'author': self.author,
            }
    if self.repository_name:
      data['repository_name'] = self.repository_name
    if self.time:
      data.update({'time': self.time.strftime('%Y-%m-%d %H:%M:%S')})
    return data

  def AuthorName(self):
    """Get the name of the author.

    Returns:
      The 'name' part of 'name@domain.xyz' if the author is an email address, or
      the whole author if not.
    """
    return self.author.split('@')[0]


def ConcatenateChangelogs(revisions):
  """Concatenate the changelogs of several revisions."""
  if not revisions:
    return ''
  if len(revisions) == 1:
    return revisions[0].single_scrubbed_log
  logs = [rev.scrubbed_log for rev in revisions]
  for i, log in enumerate(logs[:-1]):
    if not log.endswith('\n'):
      logs[i] += '\n'
  return '\n'.join(logs)


class FileDifference(object):
  """Describes how files are different.

  This encapsulates only the info that is interesting to manage_codebases,
    which actually doesn't even care what the differences in text are.

  If the files differ only in text, the FileDifference will have no properties
    set. Its existence is enough to prove they differ.
  """

  def __init__(self, relative_filename):
    self.relative_filename = relative_filename
    self.file1_missing = False
    self.file2_missing = False
    self.reason = None

  def __str__(self):
    if self.reason:
      return self.reason
    return '[Unknown]'


def AreFilesDifferent(file1, file2, relative_filename=''):
  """Diff file1 and file2.

  Args:
    file1: str, path to file1
    file2: str, path to file2
    relative_filename: str, the relative filename

  Returns:
    FileDifference (or None, if not different)
  """
  args = {}
  args['stderr'] = open('/dev/null', 'w')
  args['stdout'] = open('/dev/null', 'w')
  difference = FileDifference(relative_filename)
  # We want to generate diffs even if one file doesn't exist.
  if not os.path.exists(file1):
    difference.file1_missing = True
  if not os.path.exists(file2):
    difference.file2_missing = True
  if difference.file1_missing or difference.file2_missing:
    if difference.file1_missing and difference.file2_missing:
      # Both are non-existent, and therefore are equal.
      return None
    # one exists, the other does not, therefore they differ
    difference.reason = 'File missing from one codebase'
    return difference
  if IsExecutable(file1) != IsExecutable(file2):
    difference.reason = 'Executable bit differs'
    return difference
  p = subprocess.Popen(['diff', '-q', file1, file2], **args)
  p.wait()

  if p.returncode:
    difference.reason = 'File contents differ'
    return difference
  return None


class CodebaseDifference(object):
  """Describes how codebases are different.

  Includes only the differences that are interesting.
  """

  def __init__(self):
    # TODO(dbentley): storing only the first difference is a hack
    # to enable short-circuiting. This was premature optimization.
    self.first_difference = None
    self.first_difference_reason = None
    self.codebase1_only = []
    self.codebase2_only = []
    self.differences = []

  def __str__(self):
    message = ''
    if self.codebase1_only:
      message = 'Missing from codebase 1: %s\n' % ','.join(self.codebase1_only)
    if self.codebase2_only:
      message += 'Missing from codebase 2: %s\n' % ','.join(self.codebase2_only)
    if self.first_difference_reason:
      message += '%s\n' % self.first_difference_reason

    if message:
      return message
    return '[Unknown]'

  def HasDifference(self):
    return self.first_difference is not None

  def AddDifference(self, file_difference):
    if not self.first_difference:
      self.first_difference = file_difference.relative_filename
      self.first_difference_reason = '%s: %s' % (
          file_difference.relative_filename, str(file_difference))
    self.differences.append(file_difference)


def AreCodebasesDifferent(codebase1, codebase2, noisy_files_re=None):
  """Determines whether two Codebases are different, and how.

  NB(dbentley): this takes Codebase objects, and replaces an older method
  that had a better name and worse interface.

  Args:
    codebase1: codebase_utils.Codebase
    codebase2: codebase_utils.Codebase
    noisy_files_re: str, regular expression of files that are "noisy", that is,
                    they change so often that we should not consider their
                    differences.

  Returns:
    CodebaseDifference, or None if no difference
  """
  if noisy_files_re:
    noisy_files_re = re.compile(noisy_files_re)

  relative_files = set(codebase1.Walk()).union(codebase2.Walk())
  result = CodebaseDifference()

  for relative_filename in relative_files:
    if noisy_files_re and noisy_files_re.search(relative_filename):
      continue
    file_difference = AreFilesDifferent(
        codebase1.FilePath(relative_filename),
        codebase2.FilePath(relative_filename),
        relative_filename)
    if file_difference:
      result.AddDifference(file_difference)

  if result.HasDifference():
    return result
  return None


def ListFiles(root, files_to_ignore_re):
  """Return the files below root.

  Arguments:
    root: str, the directory.
    files_to_ignore_re: re, a matcher for files to ignore. May be None.

  Returns:
    seq of str, the relative filenames in this directory
  """
  result = []
  for (dirpath, _, filenames) in os.walk(root):
    for f in filenames:
      abs_path = os.path.join(dirpath, f)
      relative_path = abs_path.replace(root, '', 1)
      relative_path = relative_path.lstrip('/')
      if (files_to_ignore_re and
          files_to_ignore_re.search(relative_path)):
        # this file is extraneous; don't list it
        continue
      result.append(relative_path)

  return result


class CmdError(Error):
  """An error occurred while running a command."""

  def __init__(self, message, stdout='', returncode=None, **kwargs):
    Error.__init__(self, message, **kwargs)
    self.returncode = returncode
    self.stdout = stdout
    self._message = message

  def __str__(self):
    message = self._message
    if self.stdout:
      message = message + '\n' + self.stdout
    return message

  def AppendMessage(self, s):
    self._message += '\n' + s


def RunCmd(cmd, args, cwd=None, need_stdout=False, print_stdout_and_err=False,
           unhook_stdout_and_err=False,
           stdin_data=None, env=None):
  """Run a command.

  Args:
    cmd: str, the command to run
    args: list, the arguments to pass to cmd
    cwd: str, the directory to run this command in
    need_stdout: bool, whether stdout should be saved and returned to caller
    print_stdout_and_err: bool, whether to have stdout and stderr go to their
                          normal destinations
    unhook_stdout_and_err: bool, whether to unhook these. This is useful for
                            when sub-commands need to interact with the user.
    stdin_data: str, data to pass on stdin
    env: dict, the environment to run the command in

  Returns:
    str or None, the stdout if requested

  Raises:
    base.Error: if cmd returns non-zero.
  """
  logging.debug('>>RUNNING: %s %s', cmd, ' '.join(args))

  if cwd:
    logging.debug('(in %s)', cwd)

  kwargs = {}
  if cwd:
    kwargs['cwd'] = cwd

  kwargs['stdout'] = subprocess.PIPE
  kwargs['stderr'] = subprocess.PIPE
  if unhook_stdout_and_err:
    del kwargs['stdout']
    del kwargs['stderr']
  if stdin_data:
    kwargs['stdin'] = subprocess.PIPE

  if env:
    kwargs['env'] = env
  process = subprocess.Popen([cmd] + args,
                             **kwargs)
  stdout_data, stderr_data = process.communicate(stdin_data)

  if print_stdout_and_err:
    print stdout_data

  logging.debug('>>%s FINISHED', cmd)

  if process.returncode:
    if stderr_data:
      sys.stderr.write(stderr_data)
    message = ('%(cmd)s command %(args)s in %(dir)s returned %(return_code)d' %
               {'cmd': cmd, 'args': args,
                'return_code': process.returncode, 'dir': cwd})
    print message
    if stdout_data:
      print stdout_data
    raise CmdError(
        message,
        returncode=process.returncode,
        stdout=stdout_data)
  if print_stdout_and_err and stderr_data:
    sys.stderr.write(stderr_data)
  if need_stdout:
    return stdout_data


class RepositoryConfig(object):
  """Configuration for a MOE repository."""

  def MakeRepository(self):
    """Make the repository.

    NB: implementations of this function should be safe to run in a test
        (e.g., they should not have to talk to a server just to be constructed.)

    Returns:
      (SourceControlRepository, CodebaseCreator)
    """
    raise NotImplementedError

  def Serialized(self):
    """Serialized form of this config.

    Returns:
      str, in JSON
    """
    raise NotImplementedError

  def Info(self):
    """Serialized info about this config, to be sent to the db.

    Returns:
      Dictionary of string->JSON dumpable object. It should have at least
        "name"-> str.
    """
    raise NotImplementedError


class CodebaseExpander(object):
  """Expands Codebases idempotently."""

  def __init__(self, temp_dir):
    """Constructs.

    Args:
      temp_dir: str, path to a temporary directory
    """
    self._temp_dir = temp_dir
    self._expansion_cache = {}

  def _PossiblyExpandCodebase(self, codebase):
    """Expand (if necessary) a codebase we created.

    Args:
      codebase: str, path to a codebase.

    Returns:
      str, path to an expanded version of this codebase

    NB(dbentley): this is for friends (created Codebase's) only. Hence _-prefix.
    """
    return PossiblyExpandCodebase(codebase, self._temp_dir,
                                  cache=self._expansion_cache)


def GetTimestampFromSrcrrTime(timestamp):
  """Converts a Srcrr timestamp string to a datelib Timestamp object."""
  tz = pytz.timezone('US/Pacific')  # srcrr uses pacific time
  tz = tz.normalize(datelib.Timestamp.utcnow()).tzinfo  # fix for DST
  time = datelib.Timestamp.FromString(timestamp, tz=tz)
  # We do the parsing twice. Once using the current time to figure out
  # whether the revision time is unambiguously in DST/non-DST, and once at
  # the revision time. There may still be problems around the discontinuity,
  # but they're less severe than they would be without this.
  tz = pytz.timezone('US/Pacific')
  tz = tz.normalize(time).tzinfo
  time = datelib.Timestamp.FromString(timestamp, tz=tz)
  return time
