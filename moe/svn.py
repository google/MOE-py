#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.

"""Code to interact with subversion."""

__author__ = 'dbentley@google.com (Dan Bentley)'

import getpass
import mimetypes
import os
import re
import shutil
import tempfile

from compat import cElementTree as ElementTree
import pytz

from google.apputils import app
from google.apputils import file_util
import gflags as flags
from google.apputils.datelib import Timestamp
from google.apputils.datelib import UTC

from moe import base
from moe import codebase_utils
from moe import moe_app

FLAGS = flags.FLAGS

SVN_VERSION_RE = re.compile(r'svn, version 1\.(.)')


class SvnClient(base.CodebaseClient):
  """Implementation for Subversion-stored codebases."""

  def __init__(self, repository, temp_dir, username='', password='',
               existing_checkout=''):
    """Create SvnClient.

    Args:
      repository: SvnRepository from which this client is checked out.
      temp_dir: temporary directory to use for our client.
      username: svn client username
      password: svn client password
      existing_checkout: an existing checkout we can use. (NB: if this
                         directory is not actually an existing checkout,
                         results will be wonky. But this can save much time.
                         Recommended for debugging.)
    """
    self.repository_url = repository.Url()
    self.username = username
    self.password = password
    self.checked_out = False
    self.authenticated = False

    self._CheckSvnVersion()

    if existing_checkout:
      if not os.path.isdir(os.path.join(existing_checkout, '.svn')):
        raise app.UsageError('%s does not appear to be an svn checkout' %
                             existing_checkout)
      self.checkout = existing_checkout
      self.checked_out = True
    else:
      self.checkout = tempfile.mkdtemp(dir=temp_dir, prefix='svn_')

    self.checkout = os.path.abspath(self.checkout)
    self._repository = repository

  # NOTE(dbentley): ghardy still comes with svn 1.4. svn 1.5 is 2 years old,
  # and useful. So we're going to use it.
  def _CheckSvnVersion(self):
    """MOE requires svn 1.5 or higher. Check that."""
    version_info = RunSvn(['--version'], need_stdout=True)
    v = SVN_VERSION_RE.match(version_info)
    try:
      if v and int(v.group(1)) >= 5:
        return
    except ValueError:
      pass
    raise base.Error(
        'MOE requires at least svn 1.5. '
        'To determine your version, run svn --version .\n'
        'Upgrade with: "sudo apt-get install -t hardy-backports '
        'subversion python-subversion"')

  _DRY_RUN_OK = object()

  def RunSvn(self, args, **kwargs):
    """Run an svn command, using a given username and password if supplied.

    Args:
      args: seq of str, the arguments to pass
      kwargs: optional args as for base.RunCmd

    Returns:
      str or None, the stdout if requested

    Raises:
      base.Error: if SVN returns non-zero.
    """
    if FLAGS.debug_dry_run:
      result = self._DryRunSvn(args)
      if result is not self._DRY_RUN_OK:
        return result
    kwargs['cwd'] = self.checkout
    args += ['--no-auth-cache']
    if self.username:
      args += ['--username', self.username, '--password', self.password]
    return RunSvn(args, **kwargs)

  def _DryRunSvn(self, args):
    cmd = args[0]
    if cmd in ['ci', 'commit']:
      # This won't work well in general, but isn't bad for just one commit.
      next_revision = int(self._repository.GetHeadRevision()) + 1
      return 'Committed revision %i' % next_revision
    elif cmd == 'propset' and '--revprop' in args:
      return None
    return self._DRY_RUN_OK

  def EnsureOverHttps(self):
    """Make sure the user is running over https."""
    if self.repository_url.startswith('http:'):
      old_url = self.repository_url
      self.repository_url = self.repository_url.replace('http:', 'https:')
      self.RunSvn(['switch', '--relocate', old_url, self.repository_url])

  def TestAuthentication(self):
    """Test if the user's authentication cache is valid.

    This is done by attempting to do an unversioned propset of an arbitrary
    revision-specific property 'moe:auth' to the empty string.
    """
    if self.authenticated:
      return
    try:
      self.EnsureOverHttps()
      self.RunSvn(['propset', 'moe:auth', '', '--non-interactive',
                   '--revprop', '-r', '1'], need_stdout=True)
    except base.CmdError:
      if self.username:
        raise base.Error('Incorrect username/password: %s' % self.username)
      else:
        # NB(dbentley): sometimes svn decides it knows our username/pw
        # better than we do.
        # Cf. https://bugs.launchpad.net/ubuntu/+source/subversion/+bug/473139
        # Try searching for [gnome-keyring svn] for more info.
        self.username = raw_input('SVN Username: ')
        self.password = getpass.getpass(prompt='SVN Password: ')
        self.TestAuthentication()
        return
    self.RunSvn(['propdel', 'moe:auth', '--revprop', '-r', '1'])
    self.authenticated = True

  def Checkout(self):
    """Ensure this client is at the right revision for this repository.

    If it does not already exist, check it out.
    If it does, update it.
    """
    if not self.checked_out:
      print 'Checking out svn at %s into %s' % (self.repository_url,
                                                self.checkout)
      self.RunSvn(['co', self.repository_url, '.'])
      self.checked_out = True
      print 'Checked out.'
    else:
      status = self.RunSvn(['status', '--xml'], need_stdout=True)
      status_tree = ElementTree.XML(status)
      if status_tree.find('entry'):
        raise base.Error(
            'svn checkout in %s has pending modifications; revert or commit '
            'them to proceed.' % self.checkout)
      print 'Updating SVN'
      self.RunSvn(['up'])
      print 'Updated'

  def MakeEditor(self, migration_strategy, revisions=None):
    """Make an editor for this client."""
    return SvnEditor(self, migration_strategy=migration_strategy,
                     revisions=revisions)


class SvnEditor(base.CodebaseEditor):
  """An editor for making one push in a svn client."""

  def __init__(self, client, migration_strategy, revisions=None):
    """Construct.

    Args:
      client: SvnClient, the svn client to use
      migration_strategy: base.MigrationStrategy
      revisions: list of base.Revision, the list of revisions to migrate,
                 if known
    """
    base.CodebaseEditor.__init__(self)
    self.client = client
    self.revisions = revisions or []

    self.commit_strategy = migration_strategy.commit_strategy
    self.copy_metadata = migration_strategy.copy_metadata

    if self.commit_strategy == base.COMMIT_LOCALLY:
      raise base.Error('Commit strategy COMMIT_LOCALLY is invalid for svn.')
    if self.commit_strategy not in base.COMMIT_STRATEGIES:
      raise base.Error(
          'Commit strategy "%s" not in base.COMMIT_STRATEGIES ("%s")' %
          (self.commit_strategy, base.COMMIT_STRATEGIES))

    self._modified = None
    self._diff = None

  def Checkout(self):
    """Check out code and test if we're authenticated."""
    self.client.Checkout()

    if self.commit_strategy == base.COMMIT_REMOTELY:
      self.client.TestAuthentication()

  def Walk(self):
    """Walks the client for existent files. Returns a list of str's."""
    # TODO(dbentley): obey additional_files_re
    return base.ListFiles(self.client.checkout, re.compile(r'\.svn'))

  def PutFile(self, relative_dest, src):
    """Make relative_dest be src.

    Args:
      relative_dest: str, relative path in our source control for destination
      src: str, path to source file.

    NB: Copies the file, and also important metadata (e.g. the execute bit).
    If src doesn't exist, then to make destination be source, we delete it.
    """
    abs_dest = os.path.join(self.client.checkout, relative_dest)
    src_exists = os.path.exists(src)
    src_executable = base.IsExecutable(src)
    dest_exists = os.path.exists(abs_dest)
    dest_executable = base.IsExecutable(abs_dest)

    if not src_exists and not dest_exists:
      raise base.Error(
          'Neither src nor dest exists. Unreachable code:\n%s\n%s\n%s' %
          (relative_dest, src, abs_dest))
    if not src_exists:
      # We need to delete this file.
      self.RunSvn(['rm', relative_dest])

      # TODO(dbentley): handle newly-empty directories
      return

    # Update/create the file
    base.MakeDir(os.path.dirname(abs_dest))
    shutil.copyfile(src, abs_dest)

    if not dest_exists:
      self.RunSvn(['add', '--parents', relative_dest])

      # Add mime-types for new files.
      mimetype, _ = mimetypes.guess_type(relative_dest)
      if mimetype:
        # force this
        if mimetype in ['application/x-javascript', 'application/javascript']:
          mimetype = 'text/javascript'

        self.RunSvn(['propset', 'svn:mime-type', mimetype, relative_dest])

    if dest_executable != src_executable:
      if src_executable:
        self.RunSvn(['propset', 'svn:executable', '*', relative_dest])
      else:
        self.RunSvn(['propdel', 'svn:executable', relative_dest])

  def ChangesMade(self):
    if self._modified is None:
      raise RuntimeError('Called ChangesMade before FinalizeChange')
    return self._modified

  def FinalizeChange(self, commit_message, report):
    """Describe the state we're in."""
    # TODO(dbentley): refactor into _IsWorkingDirectoryDirty for svn.
    msg_filename = os.path.join(self.client.checkout, 'svn-commit.tmp')
    if os.path.exists(msg_filename):
      raise RuntimeError('%s exists, but I want to put commit message there' %
                         os.path.abspath(msg_filename))
    status = self.RunSvn(['status', '--xml'], need_stdout=True)
    status_tree = ElementTree.XML(status)
    if not status_tree.find('target').find('entry'):
      self._modified = False
      return
    else:
      self._modified = True

    self._diff = self.RunSvn(['diff'], need_stdout=True)
    file_util.Write(msg_filename, commit_message)

    patches_message = ('Patches applied against %s in %s' %
                       (self.client.repository_url, self.client.checkout))
    if self.commit_strategy != base.LEAVE_PENDING:
      report.AddStep(name=patches_message, cmd='')
      return

    report.AddTodo(
        'Refine commit message in %s/svn-commit.tmp '
        '(for code words, brevity, etc.)' %
        self.client.checkout)
    commit_todo_lines = [patches_message]
    if self.client.repository_url.startswith('http:'):
      commit_todo_lines.append(
          '       (Using http: You may https: to submit your change)')
      commit_todo_lines.append(
          '      (to do that, run svn switch --relocate %s %s )' % (
              self.client.repository_url,
              self.client.repository_url.replace('http:', 'https:')))
    commit_todo_lines.append(
        '   To submit, run: (cd %s && svn ci -F svn-commit.tmp '
        '&& rm svn-commit.tmp )' % (self.client.checkout))
    report.AddTodo('\n'.join(commit_todo_lines))

  def CommitChange(self, report):
    """Make a commit with the SVN client.

    Args:
      report: base.MoeReport

    Returns:
      str, the commit id if a commit was made, the recent revision id if
           an attempted commit was a no-op, or None if no commit was attempted
    """
    if self.commit_strategy != base.COMMIT_REMOTELY:
      return None
    if not self.ChangesMade():
      return self.client._repository.GetHeadRevision()

    self.client.EnsureOverHttps()
    report.AddStep(name='Committing svn from %s to %s' %
                   (self.client.checkout, self.client.repository_url), cmd='')
    # NB(ahaven): unfortunatly, svn ci doesn't accept an --xml flag.
    info = self.RunSvn(['ci', '-F', 'svn-commit.tmp'], need_stdout=True)
    base.RunCmd('rm', ['svn-commit.tmp'], cwd=self.client.checkout)

    commit_id = None
    match = COMMIT_INFO_RE.search(info)
    if match:
      commit_id = match.group(1)

    self._CopyMetadata(commit_id)

    return commit_id

  def Diff(self):
    """Return a diff of the changes made in this client."""
    if self._diff is None:
      raise RuntimeError('Called Diff before FinalizeChange')
    return self._diff

  def Link(self):
    """Return a link to the changes made in this client."""
    if self._diff is None:
      raise RuntimeError('Called Link before FinalizeChange')
    # TODO(user): possibly link to rietveld
    return ''

  def Root(self):
    """Return a path that's the conceptual root of the codebase."""
    return self.client.checkout

  def RunSvn(self, args, **kwargs):
    return self.client.RunSvn(args, **kwargs)

  def _CopyMetadata(self, commit_id):
    """Copy metadata into svn, if necessary.

    Args:
      commit_id: str, the commit_id of the change, if any was committed

    Raises:
      hopefully nothing! This function should try to set metadata, but if it
      can't, it's better to not do it quietly then to not do it loudly.
    """
    try:
      if self.copy_metadata and commit_id and len(self.revisions) == 1:
        rev = self.revisions[0]
        if rev.time:
          try:
            actual_date = self.RunSvn(['propget', '--revprop', '-r', commit_id,
                                       'svn:date'], need_stdout=True)
            self.RunSvn(['propset', '--revprop', '-r', commit_id,
                         'moe:actual_date', actual_date])

            tz = pytz.timezone('US/Pacific')  # srcrr uses pacific time
            tz = tz.normalize(rev.time).tzinfo  # fix for DST
            ts = rev.time.astimezone(tz=UTC)
            svntime = ts.strftime('%Y-%m-%dT%H:%M:%S.000000Z')
            self.RunSvn(['propset', '--revprop', '-r', commit_id, 'svn:date',
                         svntime])
          except OverflowError:
            print 'Invalid time given for revision %s: %s' % (rev.rev_id,
                                                              rev.time)
        if rev.author:
          svnauthor = '%s@google.com' % rev.AuthorName()
          self.RunSvn(['propset', '--revprop', '-r', commit_id, 'svn:author',
                       svnauthor])
    except base.Error:
      # If this fails, we don't want to bring MOE down
      pass


COMMIT_INFO_RE = re.compile('Committed revision (\d+)\.$')


class SvnRepository(base.SourceControlRepository):
  """Subversion repository-related utilities."""

  def __init__(self, url, repository_name):
    self._url = url
    self._repository_name = repository_name

  def Export(self, directory, revision=''):
    """Export repository at revision (or head) into directory."""
    if not revision:
      revision = 'HEAD'
    args = ['export', self._url, '-r', str(revision), directory]
    print 'Exporting %s to %s at revision %s' % (self._url, directory,
                                                 str(revision))
    RunSvn(args)

  def MakeClient(self, directory, username='', password=''):
    """Make a client for editing this codebase."""
    return SvnClient(self, directory, username, password)

  def GetHeadRevision(self, highest_rev_id=''):
    info = RunSvn(
        ['log', '--xml', '-r', '%s:1' % (highest_rev_id or 'HEAD'), self._url],
        need_stdout=True)
    info_tree = ElementTree.XML(info)
    log = info_tree.find('logentry')
    i = int(log.get('revision'))
    return str(i)

  def MakeRevisionFromId(self, id):
    return base.Revision(rev_id=id, repository_name=self._repository_name)

  def RevisionsSinceEquivalence(self, head_revision, which_repository, db):

    # NB(dbentley): returns newest first
    limit = 50
    while True:
      head_revision_int = int(head_revision)

      text = RunSvn(['log', '--xml', '-l', str(limit), '-r',
                     '%s:1' % str(head_revision_int),
                     self._url], need_stdout=True)
      revisions = ParseRevisions(text, self._repository_name)
      result = []
      for r in revisions:
        equivalences = db.FindEquivalences(r, which_repository)
        moe_app.RUN.ui.Debug("equivalences for revision %s: %s" %
                             (r.rev_id, str(equivalences)))
        if equivalences:
          return result, equivalences
        result.append(r)
      limit *= 2
      if limit > 400:
        raise base.Error("Could not find equivalence in 400 revisions.")

  def Url(self):
    return self._url


def RunSvn(args, **kwargs):
  """Run an svn command.

  Args:
    args: seq of str, the arguments to pass
    kwargs: optional args as for base.RunCmd

  Returns:
    str or None, the stdout if requested

  Raises:
    base.Error: if SVN returns non-zero.
  """
  return base.RunCmd('svn', args, **kwargs)


def ParseRevisions(text, repository_name):
  """Extract separate revisions out of the xml output of an svn log call."""
  # TODO(user): This should always scrub out MOE_MIGRATION lines
  rev_tree = ElementTree.XML(text)
  result = []
  for entry in rev_tree.findall('logentry'):
    rev_id = entry.get('revision')

    changelog = ''
    if entry.find('msg') is not None:
      changelog = entry.find('msg').text or ''

    author = ''
    if entry.find('author') is not None:
      author = entry.find('author').text or ''

    time = ''
    if entry.find('date') is not None:
      time = entry.find('date').text or ''

    result.append(base.Revision(rev_id=rev_id, repository_name=repository_name,
                                changelog=changelog,
                                author=author, time=time))
  return result


class SvnRepositoryConfig(base.RepositoryConfig):
  """Configuration for a repository that lives in Subversion."""

  def __init__(self, config_json, username='', password='', repository_name=''):
    if config_json['type'] != 'svn':
      raise base.Error('type %s is not svn' % config_json['type'])
    self.url = config_json['url']
    self.username = username or config_json.get('username')
    self.password = password or config_json.get('password')
    self.additional_files_re = config_json.get('additional_files_re')
    self._config_json = config_json
    if repository_name:
      self._repository_name = repository_name + '_svn'
    else:
      self._repository_name = ''

  def MakeRepository(self, translators=None):
    repository = SvnRepository(self.url, self._repository_name)
    return (repository,
            codebase_utils.ExportingCodebaseCreator(
                repository, self.username, self.password,
                repository_name=self._repository_name,
                additional_files_re=self.additional_files_re,
                translators=translators))

  def Serialized(self):
    return self._config_json

  def Info(self):
    return {'name': self._repository_name}
