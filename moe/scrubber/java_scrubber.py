#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.

"""Java-related scrubbers."""

__author__ = 'dbentley@google.com (Dan Bentley)'

import re

from moe.scrubber import base
from moe.scrubber import comment_scrubber

# A file is unmeaningful if it contains only package declarations, import
# declarations, and whitespace (after scrubbing).
JAVA_UNMEANINGFUL_RE = re.compile(r'^(\s|package.*?;|import.*?;)*$')


class RemoveCommentsScrubber(comment_scrubber.CommentOrientedScrubber):
  """Removes all comments. Useful to scrub a file of comments."""

  def ScrubComment(self, unused_comment_text, unused_file_obj):
    return base.Revision('', 'Scrubbing to determine Java meaningfulness')


class EmptyJavaFileScrubber(base.BatchFileScrubber):
  """Error on java files that contain no class or interface.

  Some files are entirely @GoogleInternal. Thus, after scrubbing, they're
  a package statement. Maybe some comments? (license headers, e.g.)

  These aren't worth publishing.

  We would like to scrub them completely. We could just not emit the file.
  BUT, that would break other parts of MOE: the part that figures out how
  to merge in changes would get confused. We'd need to edit the fileset that's
  generated. Of course, that involves editing BUILD files, which can't be done
  by hand. This is another vote in favor of giving up on using Fileset and
  just having a file to generate this.

  That would mean moving to having a file that specifies these mappings,
  and a tool that generates Fileset-like-maps.
  """

  def __init__(self, action):
    """Initialize.

    Args:
      action: base.ACTION_* constant, what to do to an unmeaningful file.
    """
    base.FileScrubber.__init__(self)
    # Use a separate extractor and scrubber. We don't want the scrubber to
    # actually scrub, but we need to extract comments to pass to
    # _comment_scrubber.DetermineNewContents.
    self._extractor = comment_scrubber.CLikeCommentExtractor()
    self._comment_scrubber = comment_scrubber.CommentScrubber(
        extractor=None,
        comment_scrubbers=[RemoveCommentsScrubber()])
    self._action = action

  def BatchScrubFiles(self, file_objs, context):
    comments_by_filename = self._extractor.BatchExtractComments(file_objs)
    for file_obj in file_objs:
      if not self.IsMeaningfulJavaFile(file_obj, comments_by_filename, context):
        if self._action == base.ACTION_ERROR:
          context.AddError(
              base.ScrubberError('EMPTY_JAVA', 'no class', '', file_obj))
        elif self._action == base.ACTION_DELETE:
          file_obj.Delete()
        else:
          # NB: if action is IGNORE, this will never be created at all.
          raise base.Error('unknown file action: %s' % repr(self._action))

  def IsMeaningfulJavaFile(self, file_obj, comments_by_filename, context):
    if file_obj.filename.endswith('/package-info.java'):
      # "a package-info.java file is barely a java file at all"
      #   -kevinb@google.com, 5/4/2010
      return True
    contents = self._comment_scrubber.DetermineNewContents(
        file_obj, comments_by_filename[file_obj.filename], context)
    return not JAVA_UNMEANINGFUL_RE.match(contents)


# TODO(dbentley): handle the case of lines that are just whitespace
REPEATED_BLANK_LINES_RE_TEMPLATE = '\n{%d,}'


# TODO(dbentley): move this to a more general place when desired by
# another langugage.
class CoalesceBlankLinesScrubber(base.FileScrubber):
  """Repeated blank lines in a java file are meaningless. Fix this.

  2 blank lines can be a stylistic choice. More than that is probably
    a sign that scrubbing left newline detritus.
  """

  def __init__(self, maximum_blank_lines):
    base.FileScrubber.__init__(self)
    self._maximum_blank_lines = maximum_blank_lines
    self._re = re.compile(REPEATED_BLANK_LINES_RE_TEMPLATE % (
        maximum_blank_lines + 2))

  def ScrubFile(self, file_obj, unused_context):
    contents = file_obj.Contents()
    new_contents = self._re.sub('\n' * (self._maximum_blank_lines+1), contents)
    file_obj.WriteContents(new_contents)


# The arguments to @MediumTest and @LargeTest are optional.
TEST_ANNOTATION_RE = re.compile(
    ' *@((Sequential|SmallTest|Smoke)'
    '|((MediumTest|LargeTest)(\([^\)]*\))?)) *\n')


class TestSizeAnnotationScrubber(base.FileScrubber):
  """Scrub all test annotations."""

  def ScrubFile(self, file_obj, unused_context):
    contents = file_obj.Contents()
    if TEST_ANNOTATION_RE.search(contents):
      new_contents = TEST_ANNOTATION_RE.sub('\n', contents)
      file_obj.WriteContents(new_contents)


class JavaRenameScrubber(base.FileScrubber):
  """Scrubs a package name in Java by renaming it.

  This replaces the package name everywhere it is found. It also replaces
    the package name in file-system paths. If we find that this is undesirable,
    we can change the behavior.
  """

  def __init__(self, internal_package, public_package):
    base.FileScrubber.__init__(self)
    self._internal_package = internal_package
    self._public_package = public_package

    # Also replace file names with the package name in them.
    self._internal_path = internal_package.replace('.', '/')
    self._public_path = public_package.replace('.', '/')

    self._re_scrubber = base.RegexScrubber([
        (re.escape(self._internal_package), self._public_package),
        (re.escape(self._internal_path), self._public_path)
        ])

  def ScrubFile(self, file_obj, context):
    self._re_scrubber.ScrubFile(file_obj, context)


class UnusedImportStrippingScrubber(base.FileScrubber):
  """A scrubber that strips unused imports in java files."""

  def ScrubFile(self, file_obj, unused_context):
    if not file_obj.is_modified:
      return

    import_stripper = ImportStripper(file_obj.Contents())
    if import_stripper.stripping_needed:
      file_obj.WriteContents(import_stripper.PrintWithoutUnusedImports())


# All code from here below is lifted and modified from
# //tools/java/remove_unused_imports.py. It now ignores gxp's, and filenames,
# and does strip whitespace.

JAVA_IMPORT_LINE = re.compile(r'^\s*import\s+(?:[^;]+)\.([^.\s;]+)[\s*;]+\s*$')


class ImportStripper(object):
  """Strips one file's unused imports and unnecessary whitespace."""

  def __init__(self, contents):
    self.lines = []
    self.stripping_needed = False
    lineno = 1
    for line in contents.split('\n'):
      self.lines.append(self.Line(line, lineno, self))
      lineno += 1
    for line in reversed(self.lines):
      # strip empty lines at end of files
      if not line.line:
        line.is_needed = False
      else:
        break
    for line in self.lines:
      # force computation
      if not line.IsNeeded():
        self.stripping_needed = True

  def PrintWithoutUnusedImports(self):
    return '\n'.join(l.line for l in self.lines if l.IsNeeded())+'\n'

  class Line(object):
    """A line in a file that knows if it is an unnecessary import statement."""

    def __init__(self, line, line_no, import_stripper):
      # take off whitespace on the right edge
      self.line = line.rstrip()
      self.line_no = line_no
      self.import_stripper = import_stripper
      self.is_import_only = bool(JAVA_IMPORT_LINE.match(self.line))
      self.is_needed = None

    def IsNeeded(self):
      """Return whether a line is needed."""
      if self.is_needed is not None:
        return self.is_needed

      if not self.IsImportOnly():
        self.is_needed = True
        return True

      # Keep all globs
      type_name = self.GetImportedTypeName()
      if type_name == '*':
        self.is_needed = True
        return True

      type_pattern = re.compile('\\b' + type_name + '\\b')
      for other_line in self.import_stripper.lines:
        # Duplicate imports are not needed.
        if other_line.IsImportOnly():
          if (self.line_no > other_line.line_no
              and self.line == other_line.line):
            self.is_needed = False
            return False
        elif other_line.Contains(type_pattern):
          self.is_needed = True
          return True
      self.is_needed = False
      return False

    def IsImportOnly(self):
      return self.is_import_only

    def GetImportedTypeName(self):
      return JAVA_IMPORT_LINE.match(self.line).group(1)

    def Contains(self, pattern):
      return bool(pattern.search(self.line))
