#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""Using a config file, rewrites C and C++ #include lines.

#include lines are one of the key differences between
internal-to-google code and the opensource version.  For instance,
internal code might include "my/project/main.h" while the opensource
version includes just "main.h".  Or, internal code might #include
<unistd.h>, while the opensource version has
   #ifdef HAVE_UNISTD_H
   # include <unistd.h>
   #else
     ...
   #endif

All these rewrites are embedded in a config file.  This scrubber uses
the config file to rewrite include lines in C/C++ files.
"""



import re
import json as simplejson

from google.apputils import stopwatch

from moe import config_utils
from moe.scrubber import base


_WHITESPACE_LINE_RE = re.compile(r'^\s*$')
# These are written to only catch lines that are comment-only:
_CXX_COMMENT_LINE = re.compile(r'^\s*//')
_C_COMMENT_LINE = re.compile(r'^\s*/\*.*\*/\s*$')
_C_COMMENT_START_LINE = re.compile(r'^\s*/\*')
_C_COMMENT_END_LINE = re.compile(r'\*/\s*$')
_C_COMMENT_END_IN_MIDDLE_OF_LINE = re.compile(r'\*/\S')
# Simple test for header guards for .h files ('#ifndef FOO_H\n#define FOO_H')
# This is not precise: folks can use '#if !defined(...)' for header guards too.
_HEADER_GUARD_LINE = re.compile(r'^\s*#\s*(ifndef|define)\s+')

# This is a string that matches the beginning of an include-line
_INCLUDE_TEXT = r'^#\s*include\s+'


def _GlobMatch(s, globs):
  """Returns True iff s matches any given glob, which can have * and **."""
  for glob in globs:
    # First, convert the glob into an re.  Only need to handle * and **
    glob_as_re = re.escape(glob)
    glob_as_re = glob_as_re.replace(r'\*', '[^/]*')           # *
    glob_as_re = glob_as_re.replace(r'[^/]*[^/]*', '.*')      # **
    if re.match('(%s)$' % glob_as_re, s):
      return True
  return False


class IncludeScrubber(base.FileScrubber):
  """Scrubber that fixes up #include lines in C/C++ files for opensource."""

  def __init__(self, c_includes_config_filename=None,
               c_includes_config_string=None):
    """Parse the input config file, which is a json file or json_text."""
    assert not (c_includes_config_filename and c_includes_config_string), \
        'Cannot specify both c_includes_config_filename and c_includes_config'
    # If a filename, read the contents into the string
    if c_includes_config_filename:
      c_includes_config_string = open(c_includes_config_filename, 'rb').read()
    if c_includes_config_string:
      config_dict = self.ParseConfigString(c_includes_config_string)
    else:
      config_dict = {}
    self.config = IncludeConfig(config_dict)

  def ParseConfigString(self, config_string):
    """Parse a json configuration (as a string) into a dict and return it.

    Normally, we'd just call config_utils.LoadConfig(), but it treats
    "#include XXX" entries as comments.  We want to rewrite them to
    a more accurate regexp anyway: "^#\s*include\s+XXX".  Luckily, this
    is not treated as a comment.

    Argument:
      config_string: a json map, as a string

    Returns:
      A parsed version of the json map (as a map), with #include entries
      rewritten.
    """
    def RewriteInclude(json_obj):
      """For map keys, rewrite #include entries and remove comments."""
      if isinstance(json_obj, dict):
        newdict = {}
        for k, v in json_obj.iteritems():
          if k.startswith('#include '):
            # Since the value associated with an include-key can't be
            # a dict, we don't need to recurse on v here.
            newdict[_INCLUDE_TEXT + k[len('#include '):]] = v
          elif k.startswith('#'):
            pass
          else:
            newdict[k] = RewriteInclude(v)
        return newdict
      if isinstance(json_obj, list):
        return [RewriteInclude(v) for v in json_obj]
      return json_obj

    try:
      config_dict = simplejson.loads(config_string)
    except ValueError:
      # *Now* use config_utils, just so it reports a better error message
      config_utils.LoadConfig(config_string)
      raise    # just in case the LoadConfig didn't

    return RewriteInclude(config_dict)

  def ScrubFile(self, file_obj, unused_context):
    """Scrub a file all at once."""
    timer = self._TimerName()
    stopwatch.sw.start(timer)
    scrubbed_contents = self.config.RewriteFileContents(
        file_obj.output_relative_filename, file_obj.Contents())
    file_obj.WriteContents(scrubbed_contents)
    stopwatch.sw.stop(timer)

  def _TimerName(self):
    """The name of the stopwatch timer for a specific subclass."""
    return self.FilterName().lower() + 's'

  def FilterName(self):
    """The name of the filter for a specific subclass."""
    return 'C_INCLUDE_SCRUBBER'


class IncludeConfig(object):
  """Parses the json config file for includes and allows querying of it.

  The json file allows for several types of key/value pairs.  The most
  common just specifies a mapping:
     "#include \"foo/bar\"": "#include \"bar\""

  The keys are interpreted as python-style regexps, and the values can
  use back-references, so you can do:
     "#include \"foo/([^\"]*)\"": "#include \"\\1\""
  (Note backslashes have to be double-escaped because the input is json).

  If a single include maps to multiple lines, the value can be a list of
  lines, rather than a single string:
     "#include <unistd.h>": [
        "#ifdef HAVE_UNISTD_H",
        "# include <unistd.h>",
        "#endif"
      ]

  The keys are matched against prefixes of source file lines, so
  you don't have to worry about end-of-line comments or the like.
  Also, the keys are automatically rewritten to match text like
  '# include   <foo.h>', not just '#include <foo.h>'.

  The key can also be "insert first", in which case the value is
  inserted before the first contentful line seen in the file  (If
  no contentful line is seen, it is not inserted.)  A "contentful"
  line is any line that's not whitespace-only or in a comment.  We
  also ignore '#ifndef' and '#define' lines, assuming they're
  header-guards.
     "insert first": "#include <config.h>"

  As before, the value can be a list if multiple lines should be inserted.

  The key can also be a glob pattern.  In that case, the value should
  be a map containing a valid IncludeConfig object.  These config
  lines are parsed and only apply to files whose names match the glob
  pattern (the filenames are as they will exist in the opensource
  repository).  For instance:
     { "tests/*": { "insert first": "#include \"config_for_tests.h\"" } }
  will insert an #include line for "config_for_tests.h" before all other
  include lines, but only for files in the tests subdirectory.

  If a file matches multiple glob patterns, then the rewrites for
  *each* matching glob pattern is done (including the 'global'
  rewrite rules at the top level).

  And as always in MOE, keys that start with '#' are considered
  comments; they and their values are ignored.  The exception,
  which is unique within MOE, is that keys that start with
  '#include ' are *not* treated as comments.  Also unlike the
  rest of MOE, lines starting with '#' in lists are *not*
  considered comments.

  NOTE: Rewrites are done in an ARBITRARY order!  It is safest if a
  given line of text matches only one rule in the config file.
  """

  def __init__(self, json_config_dict):
    # All of these are lists because we promise to execute them in read-order.
    self._rewrites = {}       # map from regexp to replacement text
    self._insert_first = ''   # text to insert before first #include
    self._glob_map = {}       # map from glob-strings to IncludeConfig
    self.ParseJson(json_config_dict)

  def _StringifyValue(self, value):
    """If value is a string, return it.  Otherwise convert to a string."""
    if isinstance(value, basestring):
      return value
    else:
      try:
        return '\n'.join(value)
      except TypeError:
        raise base.Error('c-includes value "%s" is not a string or list'
                         % value)

  def _IsIncludeKey(self, k):
    """Returns True iff k is the key to an include-rewrite key/value pair."""
    # Above, we rewrote '#include foo' to be '#\s*include\s+foo'
    return k.startswith(_INCLUDE_TEXT)

  def ParseJson(self, json_config_dict):
    """json_config_dict is a parsed json file, per the class __doc__."""
    for k, v in json_config_dict.iteritems():
      if k == 'insert first':
        self._insert_first = self._StringifyValue(v) + '\n'

      elif self._IsIncludeKey(k):
        self._rewrites[re.compile(k)] = self._StringifyValue(v)

      else:
        if not isinstance(v, dict):
          raise base.Error('value for c-includes glob "%s" is not a dict' % k)
        # Can specify multiple globs via 'a|b|c'.
        self._glob_map[tuple(k.split('|'))] = IncludeConfig(v)

  def RewriteLine(self, filename, line, is_first_contentful_line):
    """Rewrite the given line in the given file according to the config.

    If the config does not want to rewrite line (for instance, it's not
    an #include line), then we return the line unchanged.

    If the rewrite is multiple lines long, the return string will have
    embedded newlines.

    Arguments:
      filename: the filename the line occurs in.  This is used to match
         glob entries in the config file.
      line: the line of text to be rewritten, including trailing newline.
      is_first_contentful_line: true if this line is not whitespace only
         and not in a comment and not part of a header #ifndef-guard,
         and all previous lines in the file were.

    Returns:
      string: The rewritten version of the line (or lines), possibly
         with embedded newlines.
    """
    retval = line

    for regex, replacement in self._rewrites.iteritems():
      retval = regex.sub(replacement, retval)

    for globs, sub_config in self._glob_map.iteritems():
      if _GlobMatch(filename, globs):
        retval = sub_config.RewriteLine(filename, retval,
                                        is_first_contentful_line)

    if is_first_contentful_line and self._insert_first:
      retval = self._insert_first + retval

    return retval

  def _IsHeaderGuardLine(self, filename, line):
    """Return true if the line looks like an '#ifndef/#define' starting a .h."""
    # If we're not in a .h file, we're not a header guard line.
    if not (filename.endswith('.h') or filename.endswith('.hpp') or
            filename.endswith('.hxx')):
      return False
    return _HEADER_GUARD_LINE.search(line)

  def _IsInACComment(self, line, is_in_c_comment):
    """Return whether this line is entirely enclosed in a C-style comment.

    A line is entirely enclosed in a C-style comment if, ignoring
    whitespace at the beginning and end of the line:
       a) the previous line was in a C-style comment and didn't terminate
          it, OR the line starts with /*; and
       b) the line ends with */, OR does not contain */ at all.

    NOTE: This is wrong for pathological cases like '/* foo *//* bar */'

    Arguments:
       line: the line to test if it's entirely enclosed in a C comment.
       is_in_c_comment: whether we're in a c-style comment at the
           beginning of this line, because the comment started on a
           previous line and hasn't terminated yet.  That is, if the
           newline at the end of the previous line is inside a c-style
           comment.

    Returns:
       True if we are in 'the middle' of a c-style comment, False else.
    """
    if _C_COMMENT_START_LINE.search(line):
      is_in_c_comment = True
    # NOTE: This doesn't handle pathological cases like '/* foo *//* bar */'
    return is_in_c_comment and not _C_COMMENT_END_IN_MIDDLE_OF_LINE.search(line)

  def _IsContentfulLine(self, filename, line, is_in_multiline_c_comment):
    """Returns true if line is not blank or comment-only, false else."""
    return not (_WHITESPACE_LINE_RE.search(line) or
                _CXX_COMMENT_LINE.search(line) or
                _C_COMMENT_LINE.search(line) or
                self._IsHeaderGuardLine(filename, line) or
                self._IsInACComment(line, is_in_multiline_c_comment))

  def RewriteFileContents(self, filename, file_contents):
    """Given a filename and its contents (string), return rewritten version."""
    retval = []
    is_in_c_comment = False
    previous_lines_not_contentful = True
    for line in file_contents.splitlines(True):   # True: keep line endings
      is_contentful_line = self._IsContentfulLine(filename, line,
                                                  is_in_c_comment)
      is_first_contentful_line = (is_contentful_line and
                                  previous_lines_not_contentful)
      retval.append(self.RewriteLine(filename, line, is_first_contentful_line))

      if not is_in_c_comment:
        is_in_c_comment = '/*' in line
      if is_in_c_comment:
        # NOTE: This doesn't handle pathological cases like '/* foo *//* bar */'
        is_in_c_comment = '*/' not in line
      if previous_lines_not_contentful:
        previous_lines_not_contentful = not is_contentful_line

    return ''.join(retval)
