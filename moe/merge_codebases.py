#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.

"""Merges codebases.

When a change is made to either the generated or public codebase, and you want
to fold that into the other, you want to bring in that change, but *not* the
changes that made them different codebases to begin with. This is merging
the codebases. Merging takes a previous codebase, and the two current codebases
(generated and public), and creates the merged codebase. If the previous
codebase is public, the merged will be generated, and vice versa.

Usage:
  merge_codebases --generated_codebase=<DIR>
    --previous_codebase=<DIR> --public_codebase=<DIR>

Codebases may be either a directory, or a .tar or .zip file containing
  the codebase.

Returns non-zero if unsuccessful merges.
"""

__author__ = 'dbentley@google.com (Dan Bentley)'

import os
import shutil
import subprocess
import sys
import tempfile

from google.apputils import app
import gflags as flags
import logging

from moe import base
from moe import moe_app

FLAGS = flags.FLAGS


class MergeCodebasesConfig(object):
  """Configuration to use for an examination of codebases."""

  def __init__(
      self,
      generated_codebase, public_codebase,
      previous_codebase):
    """Construct.

    Args:
      generated_codebase: codebase_utils.Codebase
      public_codebase: codebase_utils.Codebase
      previous_codebase: codebase_utils.Codebase
    """
    self.generated_codebase = generated_codebase
    self.public_codebase = public_codebase
    self.previous_codebase = previous_codebase
    self._Check()

  def _Check(self):
    """Perform argument checking and expansion."""
    if not self.generated_codebase:
      raise app.UsageError('generated_codebase not set')
    if not self.public_codebase:
      raise app.UsageError('public_codebase not set')
    if not self.previous_codebase:
      raise app.UsageError('previous_codebase not set')
    self.merged_codebase = tempfile.mkdtemp(
        dir=moe_app.RUN.temp_dir, prefix='merged_codebase')
    print ('Writing merged codebase to %s' %
           self.merged_codebase)


class MergeCodebasesContext(object):
  """Context to examine codebases."""

  def __init__(self, config):
    """Initialize MergeCodebasesContext.

    Args:
      config: MergeCodebasesConfig, configuration
    """
    self.config = config
    self.files = []
    self.merged_files = []
    self.failed_merges = []

  def GenerateFiles(self):
    """Determine all the files to examine."""
    file_list = []
    file_set = set()

    generated_files = self.config.generated_codebase.Walk()
    for generated_file in generated_files:
      file_list.append(generated_file)
      file_set.add(generated_file)

    public_files = self.config.public_codebase.Walk()
    for public_file in public_files:
      if public_file in file_set:
        continue
      file_list.append(public_file)

    return file_list

  def Update(self):
    """Entry point to examine codebases."""
    files_to_merge = self.GenerateFiles()
    self.files = files_to_merge

    print 'COMPARING %d FILES:' % len(self.files)
    print ' Generated Codebase:        ', self.config.generated_codebase.Path()
    print ' Public Codebase:          ', self.config.public_codebase.Path()
    print ' Previous Codebase: ', self.config.previous_codebase.Path()
    print ' Merged Codebase:', self.config.merged_codebase
    for f in files_to_merge:
      self.GenerateMergedFile(f)
    sys.stdout.write('\n')
    sys.stdout.flush()

    self.Report()

    return bool(self.failed_merges)

  def Report(self):
    """Print the final report."""
    print ('Examined %d generated/public/previous files.' %
           len(self.files))
    if self.merged_files:
      print ('%d required updating. First (up to) 10:' %
             len(self.merged_files))
      for f in self.merged_files[:10]:
        print ' ', f
      if self.failed_merges:
        print ('%d were unsuccessful. First (up to) 5:' %
               len(self.failed_merges))
        for f in self.failed_merges[:5]:
          print ' ', f
    else:
      print 'No merges required'

  def GenerateMergedFile(self, f):
    """Generate the merged file for f."""
    sys.stdout.write('.')
    sys.stdout.flush()

    generated_file = self.config.generated_codebase.FilePath(f)
    public_file = self.config.public_codebase.FilePath(f)
    previous_file = self.config.previous_codebase.FilePath(f)
    merged_file = os.path.join(self.config.merged_codebase, f)
    base.MakeDir(os.path.dirname(merged_file))

    different = base.AreFilesDifferent(generated_file, public_file)
    if not different:
      shutil.copyfile(public_file, merged_file)
      if base.IsExecutable(public_file):
        base.SetExecutable(merged_file)
      return

    # TODO(dbentley): I probably need to think about executability
    # So far, I've handled it in push_codebase but not here at all.
    # This is probably a bug.
    self.PerformMerge(public_file, previous_file, generated_file,
                      merged_file, f)

    self.merged_files.append(f)

  def PerformMerge(self, mod1_file, orig_file, mod2_file, output_file, f):
    """Merge changes.

    Args:
      mod1_file: str, path to the first modified file
      orig_file: str, path to the original file
      mod2_file: str, path to the second modified file
      output_file: str, path to a file to write the file to.
      f: str, relative filename of file being merged

    Raises:
      base.Error: if neither mod1_file nor mod2_file exists.
    """

    # First, we deal with merging deleted files.
    # merge(1) does not deal with this.
    orig_exists = os.path.exists(orig_file)
    mod1_exists = os.path.exists(mod1_file)
    mod2_exists = os.path.exists(mod2_file)
    orig_file = (orig_exists and orig_file) or '/dev/null'
    mod1_file = (mod1_exists and mod1_file) or '/dev/null'
    mod2_file = (mod2_exists and mod2_file) or '/dev/null'

    if not (mod1_exists or mod2_exists):
      raise base.Error('Neither %s nor %s exists' % (mod1_file, mod2_file))

    if not orig_exists:
      # the file was added
      pass
    else:
      if not (mod1_exists and mod2_exists):
        # the file previously existed, and now was deleted in one branch
        existing_file = (mod1_exists and mod1_file) or mod2_file
        if base.AreFilesDifferent(existing_file, orig_file):
          # one branch wants to delete; another to modify.
          # This is a failed merge. We note that it's a failed merge, and let
          # it continue. This will call merge(1) with the previous file,
          # an empty file, and the current, existing, modified file. This will
          # create a merge error that we want, so the user can fix it.
          self.failed_merges.append(f)
        else:
          # we want to delete the file; so we just don't output it
          return

    # NB(dbentley): merge takes the original file in the middle. Yes it looks
    # weird, but it is correct.
    process = subprocess.Popen(['merge', '-p', mod1_file, orig_file, mod2_file],
                               stdout=open(output_file, 'wb'))

    # Handle executable bit
    orig_exec = base.IsExecutable(orig_file)
    mod1_exec = base.IsExecutable(mod1_file)
    mod2_exec = base.IsExecutable(mod2_file)
    if mod1_exec == mod2_exec:
      output_exec = mod1_exec
    else:
      # This is clever. Explanation:
      # The executable bits of the modified files differ.
      # We should pick the one that differs from the original.
      # Because these are booleans, we get that by negating the original.
      output_exec = not orig_exec
    if output_exec:
      base.SetExecutable(output_file)

    # From merge(1)'s man page:
    # Exit status is 0 for no conflicts, 1 for some conflicts, 2 for trouble.
    process.wait()
    if process.returncode != 0:
      self.failed_merges.append(f)
      if process.returncode == 1:
        logging.error('FAILED MERGE %s', output_file)
        logging.debug(
            'FAILED MERGE command: merge -p %s %s %s',
            mod1_file, orig_file, mod2_file)
      elif process.returncode == 2:
        logging.error('Merge found "trouble" when merging: %s %s %s',
                      (mod1_file, orig_file, mod2_file))
      elif process.returncode != 0:
        logging.error('Merge returned status %d (outside of 0, 1, 2).',
                      process.returncode)


def main(unused_args):
  print 'merge_codebases has no standalone mode'
  print 'email moe-team@ if this is a problem'
  sys.exit(1)


if __name__ == '__main__':
  app.run()
