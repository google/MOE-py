#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""A library for scrubbing text that appears in comments of code."""

import re
import StringIO
import subprocess
import tokenize

import json as simplejson

import logging
from google.apputils import resources
from google.apputils import stopwatch

from moe import config_utils

from moe.scrubber import base
from moe.scrubber import usernames


class Comment(object):
  """Class encapsulating a comment in a file."""

  def __init__(self, filename, line, char_index, text):
    self.filename = filename
    self.line = line
    self.char_index = char_index
    self.text = text

  def __eq__(self, other):
    if not isinstance(other, Comment):
      return False
    return (self.filename == other.filename and self.line == other.line and
            self.char_index == other.char_index and self.text == other.text)

  def __repr__(self):
    return '<Comment %s:%s:%s:%r>' % (self.filename, self.line, self.char_index,
                                      self.text)


def CommentsFromJson(comments_json):
  """Generate a list of Comment objects from a JSON list."""
  result = []
  for comment_json in comments_json:
    config_utils.CheckJsonKeys('comment', comment_json,
                               [u'filename', u'line', u'text', u'char_index'])
    result.append(Comment(comment_json.get(u'filename', ''),
                          comment_json.get(u'line', 0),
                          comment_json.get(u'char_index', 0),
                          comment_json.get(u'text', '')))
  return result


class Error(Exception):
  """Base class for comment scrubber errors.

  Note that CommentError below is *not* a subclass of this class; see
  ScrubberError in base.py for why not.
  """


class _CommentScrubberError(Error):
  """Error in the comment scrubber that should result in a ScrubberError.

  This is essentially an implementation detail of CommentScrubber and should not
  be thrown outside this module.
  """

  def __init__(self, trigger, reason):
    Error.__init__(self, trigger, reason)
    self.trigger = trigger
    self.reason = reason


class CommentScrubber(base.FileScrubber):
  """Find the comments in this file and scrub those comments."""

  def __init__(self, extractor, comment_scrubbers=None):
    """Initialize.

    Members:
      _extractor: CommentExtractor
      _scrubbers: seq of CommentOrientedScrubber

    Args:
      extractor: CommentExtractor
      comment_scrubbers: seq of CommentOrientedScrubber
    """
    comment_scrubbers = comment_scrubbers or []
    self._extractor = extractor
    self._scrubbers = comment_scrubbers

  def ScrubFile(self, file_obj, context):
    """Scrub the comments in file_obj in context.

    Args:
      file_obj: ScannedFile, the file in which to scrub comments
      context: ScrubberContext, the context to operate in
    """
    new_contents = self.DetermineNewContents(file_obj, context)
    if new_contents != file_obj.Contents():
      file_obj.WriteContents(new_contents)

  def DetermineNewContents(self, file_obj, context):
    """Determine the new contents of scrubbing a file.

    This method is the functional version of ScrubFile, useful
      when we want to examine what the comments would be if
      scrubbed, but not actually scrub them.

    Args:
      file_obj: ScannedFile, the file in which to scrub comments
      context: ScrubberContext, the context to operate in

    Returns:
      str, the new contents of the file.
    """
    stopwatch.sw.start('extract_comments')
    comments = self._extractor.ExtractComments(file_obj)
    stopwatch.sw.stop('extract_comments')

    contents = file_obj.Contents()
    # We depend on the CPython optimization for string += to happen in constant
    # time, even though maybe we shouldn't, because we may have to strip space
    # from something we've already added to new_contents.
    new_contents = u''
    char_i = 0
    behavior = INCLUDE

    for comment in comments:
      # first we deal with the text before the comment
      if behavior is INCLUDE:
        new_contents += contents[char_i:comment.char_index]

      # Now determine the comment's new text
      old_behavior = behavior
      comment_text = self._ScrubComment(comment, file_obj, context)
      try:
        comment_text, behavior = self._HandleMoeDirectives(comment_text,
                                                           behavior)
      except _CommentScrubberError, e:
        # Add any errors to the context, but keep going.
        context.AddError(CommentError('COMMENT_SCRUBBER_ERROR', e.trigger,
                                      e.reason, file_obj))

      if comment_text and behavior is INCLUDE:
        new_contents += comment_text

      if behavior is INCLUDE and (old_behavior is STRIP or not comment_text):
        # Strip up to and including the last newline if we've just finished a
        # strip block, or we just stripped an entire comment.
        new_contents = _StripTrailingSpaceAndNewline(new_contents)

      # Move char_i to the end of the comment.
      comment_text = comment.text
      char_i = comment.char_index + len(comment_text)

    if behavior is INCLUDE:
      new_contents += contents[char_i:]

    return new_contents

  def _HandleMoeDirectives(self, comment_text, current_behavior):
    """Handle Moe directives in this comment.

    Args:
      comment_text: str, the text of the comment
      current_behavior: {INCLUDE, STRIP} the current behavior

    Returns:
      (new comment text, new behavior)
      (str, {INCLUDE, STRIP})

    Raises:
      _CommentScrubberError: if an error occurred processing this comment.
    """
    directives = list(MOE_DIRECTIVE_RE.finditer(comment_text))
    if not directives:
      return (comment_text, current_behavior)

    if len(directives) > 1:
      directive_names = [d.group(1) for d in directives]
      if not _AllIntracommentDirectives(directive_names):
        raise _CommentScrubberError(
            'multiple directives',
            'Comment %s contains >1 non-intracomment-strip MOE directive' %
            comment_text)
      comment_text = self._HandleIntracommentStripping(comment_text)
      return (comment_text, current_behavior)
    directive_match = directives[0]
    directive = directive_match.group(1)

    if directive == BEGIN_STRIP:
      if current_behavior is STRIP:
        raise _CommentScrubberError(
            directive,
            'Comment %s says to begin stripping, but already doing so' %
            comment_text)
      return ('', STRIP)

    elif directive == END_STRIP:
      if current_behavior is INCLUDE:
        raise _CommentScrubberError(
            directive,
            'Comment %s says to end stripping, but not currently stripping' %
            comment_text)
      return ('', INCLUDE)

    elif directive == END_STRIP_AND_REPLACE:
      if current_behavior is INCLUDE:
        raise _CommentScrubberError(
            directive,
            'Comment %s says to end stripping, but not currently stripping' %
            comment_text)

      new_text = _GetReplacementText(comment_text, self._extractor)
      return (new_text, INCLUDE)

    elif directive == INSERT:
      if current_behavior is STRIP:
        raise _CommentScrubberError(
            directive,
            'Comment %s says to insert, but currently stripping' %
            comment_text)
      new_text = _GetReplacementText(comment_text, self._extractor)
      return (new_text, INCLUDE)

    else:
      raise _CommentScrubberError(
          directive,
          'invalid MOE directive (in comment %s)' % comment_text)

    raise base.Error('unreachable code for comment %s' % comment_text)

  def _HandleIntracommentStripping(self, comment_text):
    """Strip intracomment-wise from comment_text."""
    begin_pos = comment_text.find(BEGIN_INTRACOMMENT_STRIP)
    end_pos = comment_text.find(END_INTRACOMMENT_STRIP)
    if begin_pos == -1 and end_pos == -1:
      return comment_text
    if begin_pos == -1:
      raise _CommentScrubberError(
          comment_text,
          'Comment begins intracomment strip but does not end')
    if end_pos == -1:
      raise _CommentScrubberError(
          comment_text,
          'Comment ends intracomment strip but does not begin')
    if begin_pos > end_pos:
      raise _CommentScrubberError(
          comment_text,
          'Intracomment strip end appears before begin')
    # take out all of the lines of the begin and end strip annotations
    real_begin_pos = comment_text[:begin_pos].rfind('\n')
    real_end_pos = comment_text[end_pos:].find(
        '\n') + end_pos
    return self._HandleIntracommentStripping(
        comment_text[:real_begin_pos] + comment_text[real_end_pos:])

  def _ScrubComment(self, comment, file_obj, context):
    comment_text = comment.text
    revisions = []
    for scrubber in self._scrubbers:
      result = scrubber.ScrubComment(comment_text, file_obj)
      if isinstance(result, base.Revision):
        revision = result
        comment_text = revision.new_text
        revisions.append(revision)
      if isinstance(result, CommentError):
        context.AddError(result)
    if revisions:
      logging.debug('Rewriting comment %s in %s because: %s',
                    comment.text, file_obj.filename,
                    u','.join([r.reason for r in revisions]))
    return comment_text


class CommentExtractor(object):
  """An interfact that can extract the comments from a file."""

  def ExtractComments(self, file_obj):
    """Extract comments from file.

    Args:
      file_obj: ScannedFile, the file to get comments from

    Returns:
      seq of Comment objects.
    """
    raise NotImplementedError

  def CommentWithoutDelimiters(self, text):
    """Given the text of a comment, return the text w/o comment delimiters.

    This abstracts language-specific comment delimiter understanding.

    Args:
      text: str, the comment text (including comment delimiters)
    """
    raise NotImplementedError


def ExtractCLikeComments(filename, text, lineno=None, char_index=None):
  """Extract CLike comments from text.

  Args:
    filename: The name of the file containing the text.
    text: The text itself, as a string.
    lineno: The starting line number of this string
    char_index: The starting char_index of this string

  Returns:
    A list of Comment objects.

  NB(dbentley): lineno and char_index are needed for when
    one comment exists within a larger file, and so we need the lineno
    and char_index to be relative not to this text, but to the text of the
    larger file.
  """
  extractor_binary = resources.GetResourceFilename(base.ResourceName('comment'))
  args = [extractor_binary, filename]
  if lineno is not None or char_index is not None:
    args += [str(lineno or 1), str(char_index or 0)]

  extractor = subprocess.Popen(args,
                               stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
  (stdoutdata, stderrdata) = extractor.communicate(text.encode('utf-8'))
  if extractor.returncode:
    logging.error('ERROR EXTRACTING %s', stderrdata)
  return CommentsFromJson(simplejson.loads(stdoutdata))


class CLikeCommentExtractor(CommentExtractor):
  """CLikeCommentExtractor that works on C-like languages.

  (I.e., /* */ or // comments. String literals with "".)
  """

  def ExtractComments(self, file_obj):
    """Call out to comment extractor."""
    return ExtractCLikeComments(file_obj.filename,
                                file_obj.Contents())

  def CommentWithoutDelimiters(self, comment_text):
    if comment_text.startswith('//'):
      return comment_text.replace('//', '', 1)
    if comment_text.startswith('/*'):
      if not comment_text.endswith('*/'):
        raise base.Error('C-like comment beginning with /* does not end with */'
                         % comment_text)
      return comment_text[2:-2]
    raise base.Error('C-like comment starts with neither // nor /*: %s' %
                     comment_text)


class HtmlCommentExtractor(CommentExtractor):
  """HtmlCommentExtractor extracts comments from HTML.

  Looks for "<!-- & -->" pairs
  """
  COMMENT_RE = re.compile('(<!--.*?-->)', re.S)
  SCRIPT_RE = re.compile('<script>(.*?)</script>', re.S)

  def ExtractComments(self, file_obj):
    """Extract comments from file."""
    # Odd indexes are the comments
    parts = HtmlCommentExtractor.COMMENT_RE.split(file_obj.Contents())
    is_comment = False
    lineno = 1
    char_index = 0

    comments = []
    for p in parts:
      char_index_in_p = 0
      lineno_in_p = 0
      if is_comment:
        comments.append(Comment(file_obj.filename, lineno, char_index, p))
      else:
        # This is not a comment. There might be script tags
        # embedded within this html. Within those script tags might be
        # javascript comments. We also want to explore them. This special
        # case is worth contorting ourselves for because it is very common.
        #
        # NOTE(dnadasi): Potentially all of these subprocess calls could slow
        # things down, do some measurement then fix, if necessary.
        for match in HtmlCommentExtractor.SCRIPT_RE.finditer(p):
          lineno_in_p = p.count('\n', char_index_in_p, match.start(0))
          char_index_in_p = match.start(0)
          comments += ExtractCLikeComments(file_obj.filename,
                                           match.group(0),
                                           lineno + lineno_in_p,
                                           char_index + char_index_in_p)

      lineno += p.count('\n')
      char_index += len(p)
      is_comment = not is_comment
    return comments

  def CommentWithoutDelimiters(self, comment_text):
    if comment_text.startswith('<!--'):
      if not comment_text.endswith('-->'):
        raise base.Error(
            'HTML comment beginning with <!-- does not end with -->: %s' %
            comment_text)
      return comment_text[4:-3]
    if comment_text.startswith('//'):
      return comment_text.replace('//', '', 1)
    if comment_text.startswith('/*'):
      if not comment_text.endswith('*/'):
        raise base.Error('C-like comment beginning with /* does not end with */'
                         % comment_text)
      return comment_text[2:-2]
    raise base.Error('Unexpected HTML comment delimiter in comment:\n%s' %
                     comment_text)


INCLUDE = object()
STRIP = object()


class CommentOrientedScrubber(object):
  """Base class for scrubbers that want to deal with comments.

  Implement this interface to scrub comments.
  """

  def ScrubComment(self, comment_text, file_obj):
    """Method that gets called per-comment.

    Args:
      comment_text: str, the text of the comment
      file_obj: ScannedFile, the file the comment appears in

    Returns:
      either base.Revision or CommentError
      revision if it can be scrubbed; error if it cannot.
    """
    raise NotImplementedError


class CommentError(base.ScrubberError):
  """A comment has given rise to an error."""

  def ReportText(self):
    return 'Error in comment in %s: %s' % (self.file_obj.filename,
                                           self.reason)


MOE_DIRECTIVE_PATTERN = 'MOE:([a-z_]+)'
MOE_DIRECTIVE_RE = re.compile(MOE_DIRECTIVE_PATTERN)
MOE_REPLACE_RE = re.compile('^\s*%s( |\n\s*)?' % MOE_DIRECTIVE_PATTERN)
BEGIN_STRIP = 'begin_strip'
END_STRIP = 'end_strip'
END_STRIP_AND_REPLACE = 'end_strip_and_replace'
INSERT = 'insert'

BEGIN_INTRACOMMENT_STRIP = 'begin_intracomment_strip'
END_INTRACOMMENT_STRIP = 'end_intracomment_strip'
INTRACOMMENT_DIRECTIVES = (BEGIN_INTRACOMMENT_STRIP, END_INTRACOMMENT_STRIP)


NOTE_RE = re.compile('(?:HACK|NOTE|TODO|XXX)\(([|,\w]+)', re.I | re.U)


class TodoScrubber(CommentOrientedScrubber):
  """Scrubber of usernames in TODO comments."""

  def __init__(self, username_filter):
    """Create a TodoScrubber.

    Args:
      username_filter: usernames.UsernameFilter
    """
    CommentOrientedScrubber.__init__(self)
    self._username_filter = username_filter

  def ScrubComment(self, comment_text, file_obj):
    """Scrub usernames that should be scrubbed."""
    match = NOTE_RE.search(comment_text)
    if match:
      names = re.split('[|,]', match.group(1))
      names_to_scrub = []
      for username in names:
        if not username:
          # some people put empty usernames
          continue
        action = self._username_filter.DetermineScrubAction(username)
        if action is usernames.PUBLISH:
          continue
        elif action is usernames.SCRUB:
          names_to_scrub.append(username)
        else:
          return TodoError(file_obj, username)

      if not names_to_scrub:
        return None
      else:
        for username in names_to_scrub:
          comment_text = re.sub('([(|,])%s([)|,])' % username,
                                '\\1user\\2',
                                comment_text)

        msg = 'user %s has not opted-in to being published'
        return base.Revision(comment_text, msg)


class TodoError(CommentError):
  def __init__(self, file_obj, username):
    base.ScrubberError.__init__(
        self, 'USERNAME', username,
        'Found unpublishable username "%s"' % username, file_obj)
    self.username = username


class SensitiveStringCommentScrubber(CommentOrientedScrubber):
  """Scrubs comments that have code words.

  In contrast to a normal SensitiveStringScrubber, which scans whole files at a
  time and is only capable of adding errors, this scrubber scans individual
  comments, and will scrub them instead of adding errors.
  """

  def __init__(self, whitelist, string_finder):
    CommentOrientedScrubber.__init__(self)
    self._whitelist = whitelist
    self._string_finder = string_finder

  def ScrubComment(self, comment_text, file_obj):
    for w in self._string_finder.FindSensitiveStrings(comment_text):
      filter_name = self._string_finder.FilterName()
      if self._whitelist.Allows(
          base.ScrubberError(filter_name, w, '', file_obj)):
        continue
      return base.Revision('', 'Found sensitive string "%s"' % w)


class AuthorDeclarationScrubber(CommentOrientedScrubber):
  """A scrubber of @author comments in various formats."""

  def __init__(self, username_filter=None):
    CommentOrientedScrubber.__init__(self)
    self._email_address_filter = usernames.EmailAddressFilter(username_filter)

  # The first group of parentheses must contain the e-mail address(es). The
  # entire contents matched by the regular expression - not just the "Author"
  # part of it - will be removed from the comment text. The closing expression
  # (\n|$) catches any trailing newline, so the entire line is removed from the
  # comment if possible.
  AUTHOR_RE_LIST = [
      re.compile(r'^[ ]*[*][ ]*@author([^\n]*)(\n|$)', re.M),
      re.compile(r'^[ ]*(?://)?[ ]*Author:([^\n]*)(\n|$)', re.M),
      re.compile(r'^[ ]*<!--[ ]*Author:([^\n]*)-->(\n|$)', re.M)]

  def ScrubComment(self, comment_text, unused_file_obj):
    """Scrub author declaration from a single comment."""

    # TODO(user): Do we need to handle multiple author lines per comment?
    for author_re in self.AUTHOR_RE_LIST:
      author = author_re.search(comment_text)
      if author:
        new_text = author_re.sub('', comment_text)
        if self._email_address_filter.CanPublish(author.group(1)):
          return
        return base.Revision(
            new_text,
            'Scrubbing author declaration')


class _TokenizingExtractor(object):

  def __init__(self, file_obj):
    self._file_obj = file_obj
    self._comments = None
    self._last_line_len = 0
    self._last_row = 1
    self._line_char_ofs = 0

  @staticmethod
  def _IsTripleQuotedString(token_tuple):
    token_type, token_str, _, _, _ = token_tuple
    if token_type != tokenize.STRING:
      return False
    return token_str.endswith('"""') or token_str.endswith("'''")

  def _AddComment(self, token_tuple):
    _, token_str, (srow, scol), _, _ = token_tuple
    self._comments.append(
        Comment(self._file_obj.filename, srow, self._line_char_ofs + scol,
                token_str.strip()))

  def _HandleToken(self, token_tuple):
    raise NotImplementedError

  def ExtractComments(self):
    """Extract comments from file."""
    if self._comments is not None:
      return self._comments
    self._comments = []
    stopwatch.sw.start('tokenize')
    input_file = StringIO.StringIO(self._file_obj.Contents())  # ergh
    try:
      for token_tuple in tokenize.generate_tokens(input_file.readline):
        _, token_str, (srow, _), (erow, _), line = token_tuple
        if srow > self._last_row:
          self._line_char_ofs += self._last_line_len
          self._last_row = srow
        self._HandleToken(token_tuple)
        if erow > srow:
          # Some tokens span multiple lines. Worse, if that token is an
          # ERRORTOKEN, the line will only contain up to the last newline, but
          # token_str will eat past the newline. AFAICT, it should end on a
          # newline, so this should be safe.
          self._last_row = erow + 1
          self._line_char_ofs += max(len(line), len(token_str))

        self._last_line_len = len(line)
    except tokenize.TokenError:
      # Premature EOF; there may be a syntax error, but it doesn't affect
      # comment extraction, and it only happens once the entire input has
      # already been tokenized.
      pass
    stopwatch.sw.stop('tokenize')
    return self._comments


class _PythonTokenizingExtractor(_TokenizingExtractor):
  """A _TokenizingExtractor for Python files."""

  def __init__(self, filename):
    _TokenizingExtractor.__init__(self, filename)
    self._last_type = -1

  def _HandleToken(self, token_tuple):
    token_type, _, _, _, _ = token_tuple
    is_comment = False
    if token_type == tokenize.COMMENT:
      is_comment = True
    elif self._IsTripleQuotedString(token_tuple):
      # it's a long string, but is it a doc string?
      if self._last_type != tokenize.OP:
        is_comment = True

    if is_comment:
      self._AddComment(token_tuple)

    self._last_type = token_type


class PythonCommentExtractor(CommentExtractor):
  """Extract comments and docstrings from Python source."""

  def ExtractComments(self, file_obj):
    return _PythonTokenizingExtractor(file_obj).ExtractComments()

  def CommentWithoutDelimiters(self, text):
    """Given a Python comment, return the text without comment delimiters."""
    # This makes the same assumption as above that docstrings are long strings.

    # Strip up to one space after the #.
    if text.startswith('# '):
      return text[2:]
    elif text.startswith('#'):
      return text[1:]

    if text.endswith('"""'):
      quote_start = text.find('"""')
    elif text.endswith("'''"):
      quote_start = text.find("'''")
    else:
      raise base.Error('Unexpected python comment delimiter in comment:\n%s' %
                       text)
    return text[quote_start+3:-3]


class _ShellLikeTokenizingExtractor(_TokenizingExtractor):
  """A _TokenizingExtractor for shell scripts and similar files."""

  def __init__(self, file_obj):
    _TokenizingExtractor.__init__(self, file_obj)
    self._brace_depth = 0

  def _HandleToken(self, token_tuple):
    token_type, _, _, _, _ = token_tuple
    if token_type == tokenize.COMMENT:
      self._AddComment(token_tuple)


class ShellLikeCommentExtractor(CommentExtractor):
  """Comment extractor for shell-like (#) comments.

  This extractor uses the Python tokenizer, since it shares the same comment
  delimiter. Limitations:
   - Won't find comments inside triple-quoted strings.
   - Doesn't handle here-documents.
   - False positives on ${#foo}, ${fo#o}, and ${fo##o}.
  """

  def ExtractComments(self, file_obj):
    """Extract comments from file."""
    return _ShellLikeTokenizingExtractor(file_obj).ExtractComments()

  def CommentWithoutDelimiters(self, text):
    # Strip up to one space after the #.
    if text.startswith('# '):
      return text[2:]
    return text[1:]


def _GetReplacementText(comment_text, extractor):
  new_text = extractor.CommentWithoutDelimiters(comment_text)
  new_text = _StripTrailingSpaceFromLastLines(new_text)
  new_text = MOE_REPLACE_RE.sub('', new_text)
  return new_text


def _StripTrailingSpaceFromLastLines(text):
  """Strip trailing space from a multi-line string.

  This strips all trailing whitespace from the last lines of a string, but does
  not strip newlines, or trailing whitespace from lines in the middle of a
  string. The last lines are defined as all lines at the end of the string that
  contain only whitespace.

  Args:
    text: The string to strip spaces from.

  Returns:
    The string with whitespace stripped from the last lines of a string.
  """
  trailing_space_re = re.compile(ur'[ \t]+(\n|$)')
  # Pylint mistakenly thinks i might be uninitialized.
  # pylint: disable-msg=W0631
  i = -1
  for i in xrange(len(text) - 1, -1, -1):
    if not text[i].isspace():
      break
  if i < 0:
    return text
  return text[:i+1] + trailing_space_re.sub(r'\1', text[i+1:])


def _StripTrailingSpaceAndNewline(text):
  """Strip trailing space and possibly a newline from a string."""
  text = text.rstrip(u' \t')
  if text.endswith(u'\n'):
    text = text[:-1]
  return text


def _AllIntracommentDirectives(directives):
  """Return whether all directives were intracomment directives."""
  for directive in directives:
    if directive not in INTRACOMMENT_DIRECTIVES:
      return False
  return True
