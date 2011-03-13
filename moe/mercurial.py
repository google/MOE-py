#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.

"""Code to interact with mercurial."""

__author__ = 'dbentley@google.com (Dan Bentley)'

import os
import re
import shutil
import tempfile

from google.apputils import app
from google.apputils import file_util

from moe import base
from moe import codebase_utils
from moe import moe_app


class MercurialClient(base.CodebaseClient):
  """Implementation for codebases stored in Mercurial (Hg)."""

  def __init__(self, temp_dir, repository_url, username='', password='',
               branch='default', revision=''):
    """Create MercurialClient.

    Args:
      temp_dir: temporary directory to use for our client.
      repository_url: url to check out
      username: hg repository username
      password: hg repository password
      branch: hg named branch
    """
    self.repository_url = repository_url
    self.username = username
    self.password = password
    self._branch = branch
    self._revision = revision
    self.checked_out = False

    # TODO(dbentley): use the code in svn.py:SvnClient.__init__
    # in the case of an existing clone

    # We add 'clone' because hg can't clone into an existing directory.
    # So, we create a tempdir, then designate a non-existent directory
    # in there as where we will put the clone.
    checkout = os.path.join(tempfile.mkdtemp(dir=temp_dir, prefix='hg_'),
                            'clone')

    self.checkout = os.path.abspath(checkout)

  def Checkout(self):
    """Check out code."""
    if not self.checked_out:
      print 'Checking out mercurial at %s into %s' % (self.repository_url,
                                                      self.checkout)
      # See comment in __init__. This is where we check into clone
      # in the directory.
      print 'Checking out; you may have to enter username and password'
      self.checked_out = True
      if self._revision:
        RunHg(['clone', self.repository_url, 'clone'],
              cwd=os.path.dirname(self.checkout), unhook_stdout_and_err=True)
        self.RunHg(['checkout', self._revision])
      else:
        RunHg(['clone', '-b', self._branch, self.repository_url, 'clone'],
              cwd=os.path.dirname(self.checkout), unhook_stdout_and_err=True)
      print 'Checked out.'
    else:
      # TODO(user): update hg client here
      # see svn.py for how it is similarly implemented
      # raise NotImplementedError
      pass

  def RunHg(self, args, **kwargs):
    self.Checkout()
    kwargs['cwd'] = self.checkout
    # TODO(user): try to use username/password
    return RunHg(args, **kwargs)

  def MakeEditor(self, migration_strategy, revisions=None):
    """Make an editor for this client."""
    return MercurialEditor(self, migration_strategy=migration_strategy,
                           revisions=revisions)


class MercurialEditor(base.CodebaseEditor):
  """An editor for  making one push in a mercurial client."""

  def __init__(self, client, migration_strategy, revisions=None):
    """Construct.

    Args:
      client: MercurialClient, the hg client to use
      migration_strategy: base.MigrationStrategy
      revisions: list of base.Revision, the list of revisions to migrate,
                 if known
      username: str, the username
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
    return base.ListFiles(self.client.checkout, re.compile(r'\.hg'))

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
      raise base.Error('Neither src nor dest exists. Unreachable code.')
    if not src_exists:
      # We need to delete this file.
      self.RunHg(['rm', relative_dest])

      # TODO(dbentley): handle newly-empty directories
      # NB(dbentley): mercurial doesn't manage directories, so this might
      # already be sufficient.
      return

    # Update/create the file
    base.MakeDir(os.path.dirname(abs_dest))

    # NB(dbentley): copy instead of copyfile to copy permission bits
    # (specifically executable, which mercurial tracks, whereas svn
    #  requires manual property management)
    shutil.copy(src, abs_dest)

    if not dest_exists:
      self.RunHg(['add', relative_dest])

  def ChangesMade(self):
    if self._modified is None:
      raise RuntimeError('Called ChangesMade before FinalizeChange')
    return self._modified

  def FinalizeChange(self, commit_message, report):
    """Describe the state we're in."""
    self._commit_message = commit_message
    msg_filename = os.path.join(self.client.checkout, 'hg-commit.tmp')
    if os.path.exists(msg_filename):
      raise RuntimeError('%s exists, but I want to put commit message there' %
                         os.path.abspath(msg_filename))
    status = self.RunHg(['status'], need_stdout=True)
    if status:
      self._modified = True
    else:
      self._modified = False
      return

    self._diff = self.RunHg(['diff'], need_stdout=True)
    file_util.Write(msg_filename, commit_message)

    patches_message = ('Patches applied against %s in %s' %
                       (self.client.repository_url, self.client.checkout))
    if self.commit_strategy != base.LEAVE_PENDING:
      report.AddStep(name = patches_message, cmd='')
      return

    report.AddTodo(
        'Refine commit message in %s/hg-commit.tmp '
        '(for code words, brevity, etc.)' %
        self.client.checkout)
    commit_todo_lines = [patches_message]
    commit_todo_lines.append(
        '   To submit, run: (cd %s && hg commit -l hg-commit.tmp '
        '&& rm hg-commit.tmp )' % (self.client.checkout))
    report.AddTodo('\n'.join(commit_todo_lines))

  def CommitChange(self, report):
    """Make a commit with the Mercurial client.

    Args:
      base.MoeReport

    Returns:
      str, the commit id if a commit was made, the recent revision id if
           an attempted commit was a no-op, or None if no commit was attempted
    """

    def Heads():
      return filter(None,
                    self.RunHg(['heads', '--template', '{node|short}\n'],
                               need_stdout=True).split('\n'))

    starting_heads = Heads()
    if self.commit_strategy == base.LEAVE_PENDING:
      return None
    hg_args = ['commit', '-m', self._commit_message]
    if self.client.username:
      hg_args += ['--user', self.client.username]
    self.RunHg(hg_args)
    current_heads = Heads()
    revision = self.RunHg(['log', '-l', '1' , '--template', '{node|short}'],
                     need_stdout=True)
    if len(current_heads) == 2 and len(starting_heads) == 1:
      try:
        self.RunHg(['merge'], env={'HGMERGE': 'false'})
        self.RunHg(['commit', '-m', 'Automated merge.'])
      except base.CmdError, e:
        # TODO(augie): print an error here
        self.RunHg(['update', '--clean', '-r', 'tip'])
    if self.commit_strategy == base.COMMIT_REMOTELY:
      task = moe_app.RUN.ui.BeginIntermediateTask(
          'push_changes', 'Pushing changes remotely (may require auth)')
      with task:
        push_args = ['push']
        if self.client.username and self.client.password:
          scheme = ''
          prefix = self.RunHg(['paths', 'default'], need_stdout=True).strip()
          if '://' in prefix:
            scheme, prefix = prefix.split('://', 1)
            if '/' in prefix:
              prefix = prefix.split('/')[0]
          push_args.extend([
            '--config', 'auth.moe-xyzzy.prefix=' + prefix,
            '--config', 'auth.moe-xyzzy.username=' + self.client.username,
            '--config', 'auth.moe-xyzzy.password=' + self.client.password,
                            ])
          if scheme:
            push_args.extend(['--config', 'auth.moe-xyzzy.schemes=' + scheme])
        self.RunHg(push_args, unhook_stdout_and_err=True)
    return revision.strip()

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

  def RunHg(self, args, **kwargs):
    kwargs['cwd'] = self.client.checkout
    return RunHg(args, **kwargs)


class MercurialRepository(base.SourceControlRepository):
  """A Mercurial repository."""

  def __init__(self, repository_url, name, branch='default',
               username='', password=''):
    self._url = repository_url
    self._name = name
    self._branch = branch
    self._username = username
    self._password = password
    self._client = MercurialClient(moe_app.RUN.temp_dir, repository_url,
                                   username=username, password=password,
                                   branch=branch)

  def Export(self, directory, revision=''):
    """Export repository at revision into directory."""
    self._Pull()
    args = ['archive']
    if revision:
      args += ['-r', revision]
    args.append(directory)
    self._client.RunHg(args)
    os.remove(os.path.join(directory, '.hg_archival.txt'))

  def MakeClient(self, directory, username='', password='', revision=''):
    """Make a client for editing this codebase."""
    # TODO(user): rethink creation of client in constructor
    return MercurialClient(moe_app.RUN.temp_dir, self._url,
                           username=self._username, password=self._password,
                           branch=self._branch, revision=revision)

  def GetHeadRevision(self, highest_rev_id=''):
    """Returns the id of the head revision (as a str)."""
    self._Pull()
    args = ['log', '--template', '{node|short}\n',
            '-l', '1', '-b', self._branch]
    if highest_rev_id:
      args += [ '-r', '%s:0' % (highest_rev_id) ]
    try:
      log = self._client.RunHg(args, need_stdout=True)
    except base.CmdError:
      return None
    return log.strip()

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
    self._Pull()
    limit = 400
    # TODO(augie): use --template here to have something easier to parse
    text = self._client.RunHg(
        ['log', '--style', 'default', '-v', '-l', str(limit), '-r',
         '%s:0' % head_revision], need_stdout=True)
    revisions = ParseRevisions(text, self._name)
    result = []
    for r in revisions:
      equivalences = db.FindEquivalences(r, which_repository)
      if equivalences:
        return result, equivalences
      result.append(r)

    # Uh-oh.
    raise base.Error("Could not find equivalence in 400 revisions.")

  def MakeRevisionFromId(self, id):
    self._Pull()
    return base.Revision(rev_id=id, repository_name=self._name)

  def _Pull(self):
    self._client.RunHg(['pull'])


_HG_BINARY = base.FindBinaryOnPath('hg',
                                   base.EnvironPath() + ['/usr/local/bin'])


def RunHg(args, **kwargs):
  """Run an hg command.

  Args:
    args: seq of str, the arguments to pass
    kwargs: optional args as for base.RunCmd

  Returns:
    str or None, the stdout if requested

  Raises:
    base.Error: if Hg returns non-zero.
  """
  if not _HG_BINARY:
    raise base.Error(
        "Can't find hg; try downloading from source; make install")
  return base.RunCmd(_HG_BINARY, args, **kwargs)


CHANGESET_RE = re.compile('^changeset:\s*(\d+):([0-9a-f]+)$')
TAG_RE = re.compile('^tag:.*$')
USER_RE = re.compile('^user:.*[\s<]([^\s<>]+@[^\s<>]+).*$')
DATE_RE = re.compile('^date:\d*(.*)$')
FILES_RE = re.compile('^files:.*$')
DESCRIPTION_RE = re.compile('^description:\d*(.*)$')


def ParseRevisions(log, repository_name):
  """Extract separate revisions out of the output of a verbose hg log call."""
  # TODO(user): perhaps use a mercurial template to make this job easier
  result = []
  description_lines = []
  rev_id = None
  time = None
  author = None
  in_description = False
  for line in log.splitlines():
    if CHANGESET_RE.match(line):
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
      rev_id = CHANGESET_RE.match(line).group(2)
    elif USER_RE.match(line):
      author = USER_RE.match(line).group(1)
    elif DATE_RE.match(line):
      time = DATE_RE.match(line).group(1).strip()
    elif TAG_RE.match(line):
      pass
    elif FILES_RE.match(line):
      in_description = False
    else:
      if DESCRIPTION_RE.match(line):
        in_description = True
        line = DESCRIPTION_RE.match(line).group(1)
      if in_description:
        description_lines.append(line)
  if rev_id:
    result.append(base.Revision(
        rev_id=rev_id,
        repository_name=repository_name,
        time=time,
        author=author,
        changelog='\n'.join(description_lines)))
  return result


class MercurialRepositoryConfig(base.RepositoryConfig):
  """Config for mercurial repository."""

  def __init__(self, config_json, repository_name='', project_space=''):
    if config_json['type'] != 'mercurial':
      raise base.Error('type %s is not mercurial' % config_json['type'])
    self.url = config_json['url']
    self.username = config_json.get('username')
    self.password = config_json.get('password')
    self.additional_files_re = config_json.get('additional_files_re')
    self._branch = config_json.get('branch', 'default')
    self._config_json = config_json
    if repository_name:
      self._repository_name = repository_name + '_hg'
    else:
      self._repository_name = ''
    self._project_space = project_space

  def MakeRepository(self, translators=None):
    repository = MercurialRepository(self.url,
                                     self._repository_name,
                                     self._branch,
                                     username=self.username,
                                     password=self.password)
    return (repository,
            codebase_utils.ExportingCodebaseCreator(
                repository, self.username, self.password,
                repository_name=self._repository_name,
                additional_files_re=self.additional_files_re,
                translators=translators,
                project_space=self._project_space))

  def Serialized(self):
    return self._config_json

  def Info(self):
    return {'name': self._repository_name}
