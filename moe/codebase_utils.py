#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Utilities for creating and dealing with Codebases."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

import os
import re
import shutil
import tempfile

from moe import base
from moe import moe_app


class Codebase(object):
  """A Codebase is a body of code.

  It's the state of a project at some point and location.
  For instance, the state of the project in public subversion at the last
  equivalence. Or the current generated codebase.
  It's a directory and all the directories and files below it. It can exist as
  a directory in a filesystem, or as a tarball, or a zip-file, or perhaps other
  types of distributions.
  """

  def __init__(self, path, expander=None, client_creator=None,
               additional_files_re=None, expanded_path=None,
               metadata=None, rev_id='',
               project_space=base.PUBLIC_STR):
    """Construct.

    Args:
      path: str, the path to the codebase
      expander: CodebaseExpander, an expander to use (DEPRECATED)
      client_creator: function -> CodebaseClient, a way to get
                      a client to modify this codebase
      additional_files_re: str, a regular expression describing files that are
                           extra in this codebase, and should not be Walk'ed
      expanded_path: str, path to an expanded version of this codebase
      metadata: object, metadata that the Codebase Creator can embed for
                usage by the creator
      rev_id: str, the id of the revision this Codebase is created at
      project_space: str, which project space this Codebase is in
    """
    self._path = path
    self._expanded_path = expanded_path
    self._client_creator = client_creator
    self._additional_files_re = (additional_files_re and
                                 re.compile(additional_files_re))
    self._metadata = metadata
    self._rev_id = rev_id
    self._project_space = project_space

  def ProjectSpace(self):
    """Which project space this Codebase is in. (one of base.PROJECT_SPACES)."""
    return self._project_space

  def AdditionalFilesRe(self):
    """RegEx object describing files that are extraneous in this Codebase."""
    return self._additional_files_re

  def Walk(self):
    """Return the files in the Codebase.

    Returns:
      seq of str, the relative filenames in this Codebase
    """
    return base.ListFiles(self.ExpandedPath(), self._additional_files_re)

  def _DebugWalk(self):
    """Debug finding files in this Codebase."""
    lst = base.ListFiles(self.ExpandedPath(), None)

    # TODO(dbentley): don't use print here, once MOE UI is better.
    print '|||||| DEBUGGING REGEX |||||||'
    print 'REGEX', (self._additional_files_re and
                    self._additional_files_re.pattern)
    print '\t', 'FILE PATH', '\t', 'REGEX', '\t', 'MATCHES'
    for f in lst:
      print '\t', f,
      print '\t', ('excluded' if self._additional_files_re and
                   self._additional_files_re.search(f) else 'included')

    print 'Files are excluded if re.search("%s", <filename>) is not None' % (
        self._additional_files_re and self._additional_files_re.pattern)

  def FilePath(self, relative_filename):
    return os.path.join(self.ExpandedPath(), relative_filename)

  def Path(self):
    """Return a str path to the (possibly-tar'ed up) codebase.

    Returns:
      str, path to the codebase

    NB: this should be some path meaningful and comprehensible to a user.
    """
    return self._path

  def ExpandedPath(self):
    """Return a str path to an expanded (i.e., a directory) codebase.

    Returns:
      str, path to the expansion

    NB: this can be an ugly path with /tmp in it.
    """
    if not self._expanded_path:
      # the method is private, but meant for us!
      # pylint: disable-msg=W0212
      self._expanded_path = moe_app.RUN.expander._PossiblyExpandCodebase(
          self._path)
    return self._expanded_path

  def Metadata(self):
    """Return the metadata of this Codebase."""
    return self._metadata

  def RevId(self):
    """Return the id of the revision this Codebase was created at, a str."""
    return self._rev_id

  def MakeEditor(self, migration_strategy, revisions=None):
    return self._client_creator().MakeEditor(migration_strategy, revisions)

  def Client(self):
    """A base.CodebaseClient that created this Codebase."""
    if self._client_creator:
      return self._client_creator()


class CodebaseCreator(object):
  """Creates Codebases a MOE tool might be interested in."""

  def __init__(self, repository_name=None, project_space=None,
               translators=None):
    self._repository_name = repository_name
    self._project_space = project_space
    self._translators = translators or []

  def Create(self, revision=''):
    """Create the Codebase for this source control at a revision.

    Args:
      revision: str, the revision; if empty, use head revision

    Returns:
      Codebase

    Raises:
      base.CodebaseCreationError
    """
    raise NotImplementedError

  def CreateInProjectSpace(self, revision='', project_space=base.PUBLIC_STR):
    """Create a codebase in a project space (translating if necessary).

    Args:
      revision: str, the revision; if empty, use head revision
      project_space: str, the project space to generate in

    Returns:
      Codebase, the created Codebase in the request proejct_space

    Raises:
      base.Error if no suitable translator can be found
    """
    original_codebase = self.Create(revision=revision)
    original_project_space = original_codebase.ProjectSpace()
    if original_project_space == project_space:
      return original_codebase
    for t in self._translators:
      if (t.FromProjectSpace() == original_project_space and
          t.ToProjectSpace() == project_space):
        return t.Translate(original_codebase)
    else:
      # TODO(dbentley): should this be a CodebaseCreationError?
      raise base.Error('Could find no translator from %s to %s' %
                       (repr(original_project_space), repr(project_space)))

  def RepositoryName(self):
    """Return a string describing this repository, or None if N/A."""
    return self._repository_name

  def ProjectSpace(self):
    """Return which project space this creator creates in, or None if N/A."""
    return self._project_space


class ExportingCodebaseCreator(CodebaseCreator):
  """CodebaseCreator that exports revisions to the filesystem."""

  def __init__(self, repository, repository_username='', repository_password='',
               additional_files_re=None, repository_name='',
               project_space=base.PUBLIC_STR, translators=None):
    CodebaseCreator.__init__(self, repository_name=repository_name,
                             project_space=project_space,
                             translators=translators)
    self._repository = repository
    self.client = repository.MakeClient(
        moe_app.RUN.temp_dir, repository_username, repository_password)
    self._additional_files_re = additional_files_re
    self._repository_name = repository_name

  def Create(self, revision):
    """Export a revision of this codebase to the filesystem.

    Args:
      revision: str, the revision of the codebase to export

    Returns:
      Codebase
    """
    task = moe_app.RUN.ui.BeginImmediateTask(
        'export_codebase',
        'Exporting codebase at revision %s' % revision)
    with task:
      is_head = not revision
      path = os.path.join(
          moe_app.RUN.temp_dir, 'public_export', str(revision) or 'head')

      if is_head:
        # TODO(dbentley): remove the existing path
        shutil.rmtree(path, ignore_errors=True)

      if not os.path.exists(path):
        # TODO(dbentley): if something got partially exported (e.g.,
        # an export process was interrupted), this corrupt export will
        # persist. It will be neither detected nor fixed. Instead, the
        # corrupt export will be used which will lead to confusing
        # results. Perhaps fix this by requiring that implementations
        # of export be atomic, e.g. by exporting to a temp place, and
        # then renaming to the desired destination atomically.
        self._repository.Export(path, revision)

      client_creator = lambda: self.client

      result = Codebase(path, None, client_creator=client_creator,
                        additional_files_re=self._additional_files_re,
                        rev_id=revision,
                        project_space=self._project_space)
      return result


def CreateModifiableCopy(codebase):
  """Create a modifiable copy of this codebase_utils.Codebase."""
  new_dir = tempfile.mkdtemp(
      dir=moe_app.RUN.temp_dir,
      prefix='modified_codebase_')

  os.rmdir(new_dir)
  shutil.copytree(codebase.ExpandedPath(), new_dir)

  return Codebase(new_dir, additional_files_re=codebase.AdditionalFilesRe())
