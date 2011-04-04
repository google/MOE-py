#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Translator (and related tools) to undo the process of scrubbing."""

__author__ = 'dbentley@google.com (Daniel Bentley)'


from moe import logic
from moe import moe_app
from moe.translators import translators


# # # # # # # # # # # # # # # # # # # # # # # # # # # # #
#
# This code is not yet complete. Do not use.
#
# TODO(dbentley): finish this.
#
# # # # # # # # # # # # # # # # # # # # # # # # # # # # #


class UndoScrubbingTranslator(translators.Translator):
  def __init__(self, from_project_space, to_project_space, project,
               forward_translator):
    """Initialize.

    Args:
      from_project_space: str
      to_project_space: str
      project: moe_project.MoeProjectContext
      forward_translator: translators.Translator, the translator that
        performs the translation that this translator reverses.
    """
    self._from_project_space = from_project_space
    self._to_project_space = to_project_space
    self._project = project
    self._forward_translator = forward_translator

  def FromProjectSpace(self):
    return self._from_project_space

  def ToProjectSpace(self):
    return self._to_project_space

  def Translate(self, codebase):
    if not codebase.ProjectSpace() == self._from_project_space:
      raise base.Error(
          'Cannot translate codebase %s from %s to %s.' %
          (codebase, codebase.ProjectSpace(), self._to_project_space))

    if self._from_project_space == 'internal':
      from_repository = self._project.internal_repository
      to_repository = self._project.public_repository
      def RevisionInToRepositoryAtEquivalence(r):
        return bool(self._project.db.FindEquivalences(r, base.PUBLIC))
    elif self._from_project_space == 'public':
      from_repository = self._project.public_repository
      to_repository = self._project.internal_repository
      def RevisionInToRepositoryAtEquivalence(r):
        return bool(self._project.db.FindEquivalences(r, base.INTERNAL))
    else:
      raise base.Error('Unexpected from_project_space: %s' %
                       self._from_project_space)

    task = moe_app.RUN.ui.BeginIntermediateTask(
        'undo_scrubbing',
        "Translating %s from %s to %s by undo'ing scrubbing" %
        (codebase, self._from_project_space, self._to_project_space))
    with task:

      source_revision_text = codebase.RevId()
      # TODO(dbentley): should we warn if source_revision_text is empty?
      # TODO(dbentley): we should ask the user to specify if they're smarter
      source_revision = from_repository.GetHeadRevision(source_revision_text)

      # TODO(dbentley): finish this code
      1 /0

      t2 = moe_app.RUN.ui.BeginImmediateTask(
          'determine_apply_against',
          'Determining revision to apply %s revision %s against' %
          (self._from_project_space, source_revision.rev_id))
      with t2:
        rs = to_repository.RecurUntilMatchingRevision()

        pass
      apply_against_revision = logic.DetermineRevisionToApplyAgainst(
          source_revision, self._from_project_space)

      apply_against_codebase = to_codebase_creator.Create(
          apply_against_revision)

      if apply_against_codebase.ProjectSpace() != self._to_project_space:
        raise base.Error(
            'Cannot apply against %s. It is in project space %s; expecting %s' %
            (apply_against_codebase, apply_against_codebase.ProjectSpace(),
             self._to_project_space))

      undo_renaming = self._forward_translator.UndoRenaming(codebase)

      unrearranged_dir = UndoRearranging(codebase, undo_renaming)

      scrubbed_codebase = translators.TranslateToProjectSpace(
          to_codebase_creator.Create(),
          from_project_space,
          self._project.translators)

      unrearranged_scrubbed_dir = UndoRearranging(scrubbed_codebase,
                                                  undo_renaming)


      # These are all in the "to" project space.
      merge_context = merge_codebases.MergeContext(
          unrearranged_dir, unrearranged_scrubbed_dir,
          apply_against_codebase)

      result = merge_context.Merge()

      # TODO(dbentley): Report warnings
      # TODO(dbentley): wait for approval for fixed merges

      return result


def UndoRearranging(rearranged_codebase, undo_remapper):
  # That is, we take the codebase in the "from" project space, and we
  # attempt to undo the renaming. Thus, the un-rearranged codebase should
  # have the same paths as the codebase in the "to" project space,
  # modulo deleted/added files. The contents of the files should be
  # different by both edits and results of scrubbing, though.

  temp_dir = tempfile.mkdtemp(moe_app.RUN.temp_dir, SOMETHING_MORE)

  relative_files = rearranged_codebase.Walk()

  for r in relative_files:
    unrearranged_relative_filename = undo_remapper.Rename(r)
    shutil.copyfile(SOMETHING)

  unrearranged = temp_dir
