#!/usr/bin/env python
# Copyright 2011 Google Inc. All Rights Reserved.

"""Code to interact with git."""



import os
import re
import shutil
import tempfile

from google.apputils import file_util

from moe import base
from moe import codebase_utils
from moe import moe_app

ID_LENGTH = 12


class GitClient(base.CodebaseClient):
  """Implementation for Git-stored codebases."""

  def __init__(self, temp_dir, repository_url, branch='',
               gerrit_autoapprove=False):
    """Create GitClient.

    Git supports several transports: ssh:// is used with an ssh-agent and the
    http/ftp transports expect a ~/.netrc file, whence username and password
    are obtained. So we shouldn't need user/pass here.

    rsync protocol is deprecated and I don't know what git:// URLs need.

    Args:
      temp_dir: directory in which to create git client
      repository_url: url to check out from
      branch: branch to work with, if not the default
      gerrit_autoapprove: true to approve via gerrit, otherwise git push should
                          just work.
    """
    self.repository_url = repository_url
    self.branch = branch
    self.gerrit_autoapprove = gerrit_autoapprove
    if gerrit_autoapprove:
      match = re.match(r'ssh://(.*?):(\d+)/(.*)$', repository_url)
      if not match:
        raise base.Error('Gerrit url (%s) must look like ssh://host:port/...' %
                         repository_url)
      self.gerrit_host = match.group(1)
      self.gerrit_port = match.group(2)
      self.gerrit_path = match.group(3)
    self.checked_out = False

    if gerrit_autoapprove and not branch:
      raise base.Error('Gerrit autoapprove requires a branch.' %
                       self.gerrit_host)

    # TODO(user): use the code in svn.py:SvnClient.__init__
    # in the case of an existing clone

    # We add 'clone' to keep things consistent with Mercurial, but Git
    # could checkout directly into the tempdir since it'll be empty.
    # At least... it will be once we rm -rf it in Checkout()
    checkout = os.path.join(temp_dir, 'git')

    self.checkout = os.path.abspath(checkout)

  def Checkout(self):
    """Obtain a local copy of the code tree."""
    if not self.checked_out:
      print 'Checking out git at %s into %s' % (self.repository_url,
                                                self.checkout)
      # See comment in __init__. This is where we check into clone
      # in the directory.
      # Ensure checkout directory is empty
      base.RunCmd('rm', ['-rf', self.checkout])
      args = ['clone', self.repository_url]
      if self.branch:
        args += ['-b', self.branch]
      args += [self.checkout]
      self.checked_out = True
      try:
        RunGit(args, cwd=os.path.dirname(self.checkout),
               unhook_stdout_and_err=True)
      except base.CmdError, e:
        raise base.Error('Failed to clone git repository: ' + str(e))
      print 'Checked out.'
    else:
      # TODO(user): update git client here
      # see svn.py for how it is similarly implemented
      # raise NotImplementedError
      pass

  def GetHeadRevision(self, highest_rev_id=''):
    """Return the ID of the latest branch revision, or None if unfound."""

    args = ['rev-list', '--max-count=1', '--abbrev-commit',
            '--abbrev=' + str(ID_LENGTH)]
    if highest_rev_id:
      args += [highest_rev_id]
      if highest_rev_id != 'HEAD' and len(highest_rev_id) != ID_LENGTH:
        raise base.Error('Received rev id of "%s", expected length %d.'
                         % (highest_rev_id, ID_LENGTH))
    else:
      args += ['HEAD']
    try:
      log = self.RunGit(args, need_stdout=True)
    except base.CmdError:
      return None
    for line in log.split('\n'):
      if len(line) == ID_LENGTH:
        return line
    return None

  def RunGit(self, args, **kwargs):
    self.Checkout()
    kwargs['cwd'] = self.checkout
    return RunGit(args, **kwargs)

  def MakeEditor(self, migration_strategy, revisions=None):
    """Make an editor for this client."""
    return GitEditor(self, migration_strategy=migration_strategy,
                     revisions=revisions)


class GitEditor(base.CodebaseEditor):
  """An editor for making one push in a git client."""

  def __init__(self, client, migration_strategy, revisions=None):
    """Construct.

    Args:
      client: GitClient, the git client to use
      migration_strategy: base.MigrationStrategy
      revisions: list of base.Revision, the list of revisions to migrate,
                 if known
    """
    base.CodebaseEditor.__init__(self)
    self.client = client
    self.revisions = revisions or []
    self.commit_strategy = migration_strategy.commit_strategy
    self._modified = None
    self._diff = None
    self._commit_message = ''

  def Checkout(self):
    """Check out code."""
    self.client.Checkout()

  def Walk(self):
    """Walks the client for existent files. Generates str's."""
    # TODO(dbentley): obey additional_files_re
    # TODO(user): Ignore ^\.git$ directory by default, and possibly other
    # .git files.
    return base.ListFiles(self.client.checkout, re.compile(r'/\.git'))

  def PutFile(self, relative_dest, src):
    """Update relative_dest with src.

    Args:
      relative_dest: str, relative path in our source control for destination
      src: str, path to source file.

    NB: Copies the file, and also important metadata (e.g. the execute bit).
    If src doesn't exist, then to make destination be source, we delete it.
    """
    abs_dest = os.path.join(self.client.checkout, relative_dest)
    src_exists = os.path.exists(src)
    dest_exists = os.path.exists(abs_dest)

    # Git handles executable bit automagically
    # src_executable = base.IsExecutable(src)
    # dest_executable = base.IsExecutable(abs_dest)

    if not src_exists and not dest_exists:
      raise base.Error('Neither src nor dest exists. Unreachable code.')
    if not src_exists:
      self.RunGit(['rm', relative_dest])
      # Git considers directories to derive from file-paths: No files under a
      # directory means git doesn't believe that directory exists, so empty
      # directories are 'magically deleted'.
      return

    # Update/create the file
    base.MakeDir(os.path.dirname(abs_dest))

    # NB(dbentley): copy instead of copyfile to copy permission bits
    # (specifically executable, which git tracks, whereas svn
    #  requires manual property management)
    shutil.copy(src, abs_dest)

    # Add both new files and modifications to index
    self.RunGit(['add', relative_dest])

  def ChangesMade(self):
    if self._modified is None:
      raise RuntimeError('Called ChangesMade before FinalizeChange')
    return self._modified

  def FinalizeChange(self, commit_message, report):
    """Describe the state we're in."""
    self._commit_message = commit_message
    # TODO(user): Need export flag for P4 CL number(s) in commit message.
    msg_filename = os.path.join(self.client.checkout, '.git-commit.tmp')
    if os.path.exists(msg_filename):
      raise RuntimeError('%s exists, but I want to put commit message there' %
                         os.path.abspath(msg_filename))
    status = self.RunGit(['status', '--porcelain'], need_stdout=True)
    if status:
      self._modified = True
    else:
      self._modified = False
      return

    self._diff = self.RunGit(['diff', '--cached'], need_stdout=True)

    patches_message = ('Patches applied against %s in %s' %
                       (self.client.repository_url, self.client.checkout))
    if self.commit_strategy != base.LEAVE_PENDING:
      report.AddStep(name=patches_message, cmd='')
      return

    # TODO(user): Mercurial probably needs to move this here too, for
    # separate commits to work.
    file_util.Write(msg_filename, commit_message)
    report.AddTodo(
        'Refine commit message in %s/.git-commit.tmp '
        '(for code words, brevity, etc.)' %
        self.client.checkout)
    commit_todo_lines = [patches_message]
    commit_todo_lines.append(
        '   To submit, run: (cd %s && git commit -F .git-commit.tmp '
        '&& rm .git-commit.tmp )' % (self.client.checkout))
    report.AddTodo('\n'.join(commit_todo_lines))

  def CommitChange(self, unused_report):
    """Make a commit with the Git client.

    Args:
      base.MoeReport

    Returns:
      str, the commit id if a commit was made, the recent revision id if
           an attempted commit was a no-op, or None if no commit was attempted
    """
    if self.commit_strategy == base.LEAVE_PENDING:
      return None
    git_commit_cmd = ['commit', '-m', self._commit_message]
    self.RunGit(git_commit_cmd)
    commit_id = self.client.GetHeadRevision('HEAD')
    if self.commit_strategy == base.COMMIT_REMOTELY:
      task = moe_app.RUN.ui.BeginIntermediateTask(
          'push_changes', 'Pushing changes remotely (may require auth)')
      with task:
        if self.client.gerrit_autoapprove:
          self.RunGit(['push', self.client.repository_url, 'HEAD:refs/for/%s' %
                       self.client.branch], unhook_stdout_and_err=True)
        else:
          self.RunGit(['push', self.client.repository_url],
                      unhook_stdout_and_err=True)
      if self.client.gerrit_autoapprove:
          self.RunGerrit(['review', '--verified=+1', '--code-review=+2',
                          '--submit', '--project=%s' % self.client.gerrit_path,
                          commit_id], unhook_stdout_and_err=True)
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
    # TODO(user): git instaweb?
    return ''

  def Root(self):
    """Return a path that's the conceptual root of the codebase."""
    return self.client.checkout

  def RunGit(self, args, **kwargs):
    kwargs['cwd'] = self.client.checkout
    return RunGit(args, **kwargs)

  def RunGerrit(self, args, **kwargs):
    """Run a ssh/gerrit command.

    Args:
      args: seq of str, the arguments to pass
      kwargs: optional args as for base.RunCmd

    Returns:
      str or None, the stdout if requested

    Raises:
      base.Error: if Gerrit returns non-zero.
    """
    kwargs['cwd'] = self.client.checkout
    args = ['-p', self.client.gerrit_port, self.client.gerrit_host,
            'gerrit'] + args
    return base.RunCmd('ssh', args, **kwargs)


class GitRepository(base.SourceControlRepository):
  """A Git repository."""

  def __init__(self, repository_url, name, branch, gerrit_autoapprove):
    self._url = repository_url
    self._name = name
    self._branch = branch
    self._gerrit_autoapprove = gerrit_autoapprove
    self._client = GitClient(moe_app.RUN.temp_dir, repository_url,
                             branch=branch,
                             gerrit_autoapprove=gerrit_autoapprove)

  def Export(self, directory, revision=''):
    """Export repository at revision into directory."""
    if not os.path.exists(directory):
      os.makedirs(directory)
    tar_file = os.path.join(directory, '.e.git.tar')
    args = ['archive', '-o', tar_file]
    if revision:
      args += [revision]
    else:
      args += ['HEAD']
    self._client.RunGit(args)

    # This would be much better as a pipe.
    base.RunCmd('tar', ['xf', tar_file, '--directory', directory])
    os.remove(os.path.join(directory, tar_file))

  def MakeClient(self, unused_directory, unused_username='',
                 unused_password=''):
    """Make a client for editing this codebase."""
    # TODO(user): rethink lazy creation of client
    return self._client

  def GetHeadRevision(self, highest_rev_id=''):
    """Returns the id of the head revision (as a str)."""

    return self._client.GetHeadRevision(highest_rev_id)

  def GenerateChangeLog(self, start_revision, end_revision):
    """Generate a change log of revisions suitable for migrating.

    Args:
      start_revision: str, the first revision to consider
      end_revision: str, the last revision to consider

    Returns:
      str, the change log

    Huge Caveat:
      this may be somewhat scrubbed, but it is essential that a human read
      and edit this text.
    """
    return base.ConcatenateChangelogs(self.GetRevisions(start_revision,
                                                        end_revision))

  def RevisionsSinceEquivalence(self, head_revision, which_repository, db):
    """Find all revisions in this repository since an equivalence.

    Args:
      head_revision: str, id of the revision to consider head
      which_repository: one of base.[INTERNAL, PUBLIC], which repository this is
      db: db_client.MoeDbClient, the db that stores equivalences

    Returns:
      (seq of base.Revision, seq of equivalences)
    """
    limit = 400
    args = ['log', '--format=medium',
            '-' + str(limit),
            '--no-decorate',  # no branch names
            '--abbrev-commit', '--abbrev=' + str(ID_LENGTH)]
    if head_revision:
      args += [head_revision]
    else:
      args += ['HEAD']
    text = self._client.RunGit(args, need_stdout=True)
    revisions = ParseRevisions(text, self._name)
    result = []
    for r in revisions:
      equivalences = db.FindEquivalences(r, which_repository)
      if equivalences:
        return result, equivalences
      result.append(r)

    # Uh-oh.
    raise base.Error('Could not find equivalence in 400 revisions.')

  def MakeRevisionFromId(self, rev_id):
    return base.Revision(rev_id=rev_id, repository_name=self._name)


def RunGit(args, **kwargs):
  """Run an git command.

  Args:
    args: seq of str, the arguments to pass
    kwargs: optional args as for base.RunCmd

  Returns:
    str or None, the stdout if requested

  Raises:
    base.Error: if git returns non-zero.
  """
  return base.RunCmd('git', args, **kwargs)


COMMIT_RE = re.compile('^commit\s*([0-9a-f]{' + str(ID_LENGTH) + '})$')
AUTHOR_RE = re.compile('^Author:.*[\s<]([^\s<>]+@[^\s<>]+).*$')
DATE_RE = re.compile('^Date:\d*(.*)$')


def ParseRevisions(log, repository_name):
  """Extract separate revisions out of the output of a verbose git log call."""
  result = []
  description_lines = []
  rev_id = None
  time = None
  author = None
  for line in log.splitlines():
    if COMMIT_RE.match(line):
      if rev_id:
        result.append(base.Revision(
            rev_id=rev_id,
            repository_name=repository_name,
            time=time,
            author=author,
            changelog='\n'.join(description_lines)))
        rev_id = None
        time = None
        author = None
        description_lines = []
      rev_id = COMMIT_RE.match(line).group(1)
    elif AUTHOR_RE.match(line):
      author = AUTHOR_RE.match(line).group(1)
    elif DATE_RE.match(line):
      time = DATE_RE.match(line).group(1).strip()
    else:
      description_lines.append(line)
  if rev_id:
    result.append(base.Revision(
        rev_id=rev_id,
        repository_name=repository_name,
        time=time,
        author=author,
        changelog='\n'.join(description_lines)))
  return result


class GitRepositoryConfig(base.RepositoryConfig):
  """Config for git repository."""

  def __init__(self, config_json, repository_name=''):
    if config_json['type'] != 'git':
      raise base.Error('type %s is not git' % config_json['type'])
    self.url = config_json['url']
    self.branch = config_json['branch']
    self.gerrit_autoapprove = config_json['gerrit_autoapprove']
    # TODO(user): Check self.gerrit_autoapprove for booleanness
    self.additional_files_re = config_json.get('additional_files_re')
    self._config_json = config_json
    if repository_name:
      self._repository_name = repository_name + '_git'
    else:
      self._repository_name = ''

  def MakeRepository(self, translators=None):
    repository = GitRepository(self.url,
                               self._repository_name,
                               self.branch,
                               self.gerrit_autoapprove)
    return (repository,
            codebase_utils.ExportingCodebaseCreator(
                repository,
                repository_name=self._repository_name,
                additional_files_re=self.additional_files_re,
                translators=translators))

  def Serialized(self):
    return self._config_json

  def Info(self):
    return {'name': self._repository_name}
