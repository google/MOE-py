#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""Scrubber scrubs.

Usage:
  scrubber [DIRECTORY]

Args:
  directory: a directory to scan
"""

__author__ = 'dbentley@google.com (Dan Bentley)'

import locale
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

from google.apputils import app
from google.apputils import file_util
import gflags as flags
from google.apputils import resources
from google.apputils import stopwatch

from moe import config_utils

from moe.scrubber import base
from moe.scrubber import comment_scrubber
from moe.scrubber import gwt_xml_scrubber
from moe.scrubber import java_scrubber
from moe.scrubber import line_scrubber
from moe.scrubber import python_scrubber
from moe.scrubber import renamer
from moe.scrubber import replacer
from moe.scrubber import sensitive_string_scrubber
from moe.scrubber import usernames
from moe.scrubber import whitelist


FLAGS = flags.FLAGS

flags.DEFINE_bool('modify', False, 'Modify files to scrub information')
flags.DEFINE_bool('stopwatch', True, 'Detail where time went (for debugging)')
flags.DEFINE_string('output_tar', '',
                    'Path of where to write a tar of scrubbed codebase')
flags.DEFINE_string('config_file', '',
                    'Path to config file')
flags.DEFINE_string('config_data', '',
                    'Text of the scrubber config')

DIFFS_DIR = 'diffs'
ORIGINAL_DIR = 'originals'
OUTPUT_DIR = 'output'
MODIFIED_DIR = 'modified'


class ScrubberConfig(object):
  """The config for a run of the scrubber.

  ScrubberConfig holds all immutable config, so the only members in
    ScrubberContext should be mutated or derived data. This allows
    other scrubbing-binaries to replace all the configuration.
  """

  def __init__(self, codebase, extension_to_scrubber_map, default_scrubbers,
               modify, output_tar):
    # Other object state.
    self.codebase = os.path.abspath(codebase)
    self.modify = modify
    self.output_tar = output_tar
    self._comment_scrubbers = None
    self._sensitive_string_scrubbers = None

    # General options.
    # If no ignore_files_re given, then we want to ignore no files, which means
    # matching no strings. '$a' is a regex that matches no strings.
    self.ignore_files_re = re.compile('$a')
    self.extension_map = []
    self.sensitive_words = []
    self.sensitive_res = []
    self.whitelist = whitelist.Whitelist([])
    self.scrub_sensitive_comments = True
    self.rearranging_config = {}
    self.string_replacements = []

    # Username options.
    self.scrubbable_usernames = None
    self.publishable_usernames = None
    self.usernames_file = None
    self.scrub_unknown_users = False
    self.scrub_authors = True
    self.scrub_proto_comments = False

    # Java-specific options.
    self.scrub_java_testsize_annotations = False
    self.maximum_blank_lines = 0
    self.empty_java_file_action = base.ACTION_IGNORE
    self.java_renames = []

    # Javascript-specific options.
    self.js_directory_renames = []

    # Python-specific options.
    self.python_module_renames = []
    self.python_module_removes = []
    self.python_shebang_replace = None

    # GWT-specific options.
    self.scrub_gwt_inherits = []

    # TODO(dborowitz): Make this a config option.
    self.known_filenames = set([
        '.gitignore',
        'AUTHORS',
        'CONTRIBUTORS',
        'COPYING',
        'LICENSE',
        'Makefile',
        'README'])

    self.ResetScrubbers(extension_to_scrubber_map, default_scrubbers)

  def ResetScrubbers(self, extension_to_scrubber_map, default_scrubbers):
    """Reset scrubbers in this config given the arguments."""
    self._sensitive_string_scrubbers = None
    self._comment_scrubbers = None
    self.username_filter = usernames.UsernameFilter(
        usernames_file=self.usernames_file,
        publishable_usernames=self.publishable_usernames,
        scrubbable_usernames=self.scrubbable_usernames,
        scrub_unknown_users=self.scrub_unknown_users)

    if extension_to_scrubber_map is not None:
      self.extension_to_scrubber_map = extension_to_scrubber_map
    else:
      self._comment_scrubbers = None
      go_and_c_scrubbers = [
          comment_scrubber.CommentScrubber(
              comment_scrubber.CLikeCommentExtractor(),
              self._CommentScrubbers())
      ] + self._PolyglotFileScrubbers()

      self.extension_to_scrubber_map = {
          '.go': go_and_c_scrubbers,
          '.h': go_and_c_scrubbers,
          '.c': go_and_c_scrubbers,
          '.cc': go_and_c_scrubbers,
          '.java': self._MakeJavaScrubbers(),
          '.js': self._MakeJsScrubbers(),
          '.html': self._MakeHtmlScrubbers(),
          '.l': go_and_c_scrubbers,
          '.php': self._MakePhpScrubbers(),
          '.php4': self._MakePhpScrubbers(),
          '.php5': self._MakePhpScrubbers(),
          '.proto': self._MakeProtoScrubbers(),
          '.protodevel': self._MakeProtoScrubbers(),
          '.py': self._MakePythonScrubbers(),
          '.css': self._PolyglotFileScrubbers(),
          '.yaml': self._PolyglotFileScrubbers(),
          '.sh': self._MakeShellScrubbers(),
          '.json': self._PolyglotFileScrubbers(),
          # Jars often have short sensitive strings in them based only on the
          # byte sequences these are. We might still like to scan jars, but a
          # way to reduce the false-positive rate is needed.
          '.jar': [],
          '.gif': [],
          '.png': [],
          '.jpg': [],
          '.xml': self._MakeGwtXmlScrubbers(),
          }

    if default_scrubbers is not None:
      self.default_scrubbers = default_scrubbers
    else:
      self.default_scrubbers = self._PolyglotFileScrubbers()

  def _SensitiveStringScrubbers(self):
    if not self._sensitive_string_scrubbers:
      self._sensitive_string_scrubbers = [
          sensitive_string_scrubber.SensitiveWordScrubber(self.sensitive_words),
          sensitive_string_scrubber.SensitiveReScrubber(self.sensitive_res),
          ]
    return self._sensitive_string_scrubbers

  def _PolyglotFileScrubbers(self):
    result = []
    if self.string_replacements:
      r = replacer.ReplacerScrubber(
          (r['original'], r['replacement']) for r in self.string_replacements)
      result.append(r)

    result += self._SensitiveStringScrubbers()
    return result

  def _CommentScrubbers(self):
    if not self._comment_scrubbers:
      self._comment_scrubbers = []
      self._comment_scrubbers.append(
          comment_scrubber.TodoScrubber(self.username_filter))
      if self.scrub_authors:
        self._comment_scrubbers.append(
            comment_scrubber.AuthorDeclarationScrubber(self.username_filter))
      if self.scrub_sensitive_comments:
        for s in self._SensitiveStringScrubbers():
          scrubber = comment_scrubber.SensitiveStringCommentScrubber(
              self.whitelist, s)
          self._comment_scrubbers.append(scrubber)
    return self._comment_scrubbers

  def _PolyglotLineOrientedScrubbers(self):
    scrubbers = []
    return scrubbers

  def _MakeGwtXmlScrubbers(self):
    gwt_scrubbers = []
    if self.scrub_gwt_inherits:
      to_scrub = set(self.scrub_gwt_inherits)
      gwt_scrubbers.append(gwt_xml_scrubber.GwtXmlScrubber(to_scrub))
    return gwt_scrubbers

  def _MakeHtmlScrubbers(self):
    html_scrubbers = []
    html_scrubbers.append(
        comment_scrubber.CommentScrubber(
            comment_scrubber.HtmlCommentExtractor(),
            self._CommentScrubbers()))
    line_scrubbers = self._PolyglotLineOrientedScrubbers()
    for js_directory_rename in self.js_directory_renames:
      line_scrubbers.append(js_directory_rename)
    html_scrubbers.append(line_scrubber.LineScrubber(line_scrubbers))
    html_scrubbers.extend(self._PolyglotFileScrubbers())
    return html_scrubbers

  def _MakeJavaScrubbers(self):
    java_scrubbers = [
        comment_scrubber.CommentScrubber(
            comment_scrubber.CLikeCommentExtractor(),
            self._CommentScrubbers()),
        ]
    line_scrubbers = self._PolyglotLineOrientedScrubbers()
    java_scrubbers.append(line_scrubber.LineScrubber(line_scrubbers))

    java_scrubbers.extend(self.java_renames)
    if self.scrub_java_testsize_annotations:
      java_scrubbers.append(java_scrubber.TestSizeAnnotationScrubber())
    java_scrubbers.append(java_scrubber.UnusedImportStrippingScrubber())

    if self.maximum_blank_lines:
      java_scrubbers.append(
          java_scrubber.CoalesceBlankLinesScrubber(self.maximum_blank_lines))
    if self.empty_java_file_action != base.ACTION_IGNORE:
      java_scrubbers.append(
          java_scrubber.EmptyJavaFileScrubber(self.empty_java_file_action))
    java_scrubbers.extend(self._PolyglotFileScrubbers())
    return java_scrubbers

  def _MakeJsScrubbers(self):
    js_scrubbers = []
    js_scrubbers.append(
        comment_scrubber.CommentScrubber(
            comment_scrubber.CLikeCommentExtractor(),
            self._CommentScrubbers()))
    line_scrubbers = self._PolyglotLineOrientedScrubbers()
    for js_directory_rename in self.js_directory_renames:
      line_scrubbers.append(js_directory_rename)
    js_scrubbers.append(line_scrubber.LineScrubber(line_scrubbers))
    js_scrubbers.extend(self._PolyglotFileScrubbers())
    return js_scrubbers

  def _MakePhpScrubbers(self):
    php_scrubbers = []
    php_scrubbers.append(
        comment_scrubber.CommentScrubber(
            comment_scrubber.CLikeCommentExtractor(),
            self._CommentScrubbers()))
    php_scrubbers.append(line_scrubber.LineScrubber(
        self._PolyglotLineOrientedScrubbers()))
    php_scrubbers.extend(self._PolyglotFileScrubbers())
    return php_scrubbers

  def _MakePythonScrubbers(self):
    py_scrubbers = []
    py_scrubbers.append(
        comment_scrubber.CommentScrubber(
            comment_scrubber.PythonCommentExtractor(),
            self._CommentScrubbers()))

    line_scrubbers = []
    line_scrubbers.extend(self.python_module_renames)
    line_scrubbers.extend(self.python_module_removes)
    if self.scrub_authors:
      line_scrubbers.append(
          line_scrubber.PythonAuthorDeclarationScrubber(self.username_filter))

    if self.python_shebang_replace:
      py_scrubbers.append(self.python_shebang_replace)

    line_scrubbers += self._PolyglotLineOrientedScrubbers()
    py_scrubbers.append(line_scrubber.LineScrubber(line_scrubbers))
    py_scrubbers.extend(self._PolyglotFileScrubbers())
    return py_scrubbers

  def _MakeProtoScrubbers(self):
    proto_scrubbers = []
    if self.scrub_proto_comments:
      proto_scrubbers.append(
          comment_scrubber.CommentScrubber(
              comment_scrubber.CLikeCommentExtractor(),
              self._CommentScrubbers()))
    proto_scrubbers.append(
        line_scrubber.LineScrubber(self._PolyglotLineOrientedScrubbers()))
    proto_scrubbers.extend(self._PolyglotFileScrubbers())
    return proto_scrubbers

  def _MakeShellScrubbers(self):
    shell_scrubbers = []
    shell_scrubbers.append(
        comment_scrubber.CommentScrubber(
            comment_scrubber.ShellLikeCommentExtractor(),
            comment_scrubbers=self._CommentScrubbers()))
    shell_scrubbers.extend(self._PolyglotFileScrubbers())
    return shell_scrubbers


class ScrubberContext(object):
  """The ScrubberContext collects the context for a scrub.

  Right now, this only includes errors. In the next iteration, it will
    also be possible to add a revision. At the end of the run, based on a flag,
    the revisions will either be applied in-place or just have their diffs
    saved somewhere.
  """

  def __init__(self, scrubber_config):
    locale.setlocale(locale.LC_ALL, 'en_US.utf-8')
    os.environ['LANG'] = 'en_US.UTF-8'
    self.config = scrubber_config
    self._errors = []
    self.CreateTempDir()
    self.files = self.FindFiles(scrubber_config)
    self._unscrubbed_file_extensions = set()
    self._unscrubbed_files = set()

  def CreateTempDir(self):
    self._temp_dir = tempfile.mkdtemp(prefix='scrubber')

  def AddError(self, error):
    """Add base.ScrubberError or str error to the list of errors."""

    # First, check if it's in our whitelist
    if self.config.whitelist.Allows(error):
      return

    self._errors.append(error)

  def Report(self):
    """Report on this run of scrubber to stdout."""
    print 'Scanned %d files' % len(self.files)
    print 'Found %d files to modify' % len(self.ModifiedFiles())

    username_to_count_map = {}
    unknown_username_instances = 0
    for error in self._errors:
      if isinstance(error, comment_scrubber.TodoError):
        username_to_count_map[error.username] = username_to_count_map.get(
            error.username, 0) + 1
        unknown_username_instances += 1
      else:
        if isinstance(error, str):
          report_string = str
        else:
          report_string = (
              'ERROR[entry:<filter:"%s" trigger:"%s" filename:"%s">]: %s' % (
                  error.filter, error.trigger, error.file_obj.relative_filename,
                  error.ReportText()))
        print report_string
    if unknown_username_instances:
      print 'Found unknown usernames %d times' % unknown_username_instances
      for username, count in username_to_count_map.iteritems():
        print u'  %s %d' % (username, count)
    print 'Wrote results into %s' % self._temp_dir

    if self._unscrubbed_file_extensions:
      print 'Did not know how to scan the following extensions:'
      for extension in self._unscrubbed_file_extensions:
        print ' ', extension

    if self._unscrubbed_files:
      print 'Did not know how to scan the following files:'
      for filename in self._unscrubbed_files:
        print ' ', filename

  def Status(self):
    """Return a status code suitable for process exit status."""
    if self._errors:
      return 1
    return 0

  def ModifiedFiles(self):
    return [f for f in self.files if f.is_modified]

  def WriteOutput(self):
    """Write out the output of this ScrubberContext.

    Side Effects:
      Always:
        output, original, and modified files are written to temporary directory
      If self.config.modify
        Files are scrubbed in place.
      If self.config.output_tar:
        Modified output is written into output_tar (as a tar file)
    """
    stopwatch.sw.start('write_output')
    base.MakeDirs(os.path.join(self._temp_dir, OUTPUT_DIR))
    base.MakeDirs(os.path.join(self._temp_dir, MODIFIED_DIR))

    for file_obj in self.files:
      # We want to be able to show all the modifications in one place.
      # Therefore, each file shows up in mutliple places.
      # 0) the output tree
      # 1) the tree of original copies (if modified)
      # 2) the tree of modified versions (if modified)
      # 3) the diff between original and modified (if modified)
      # 4) the initial source tree we were asked to modify (if modify in place)
      # 5) the tarball of the output

      # 0: write the possibly-modified file to output tree
      if file_obj.is_deleted:
        modified_filename = '/dev/null'
      else:
        output_filename = os.path.join(
            self._temp_dir,
            OUTPUT_DIR,
            file_obj.output_relative_filename)
        base.MakeDirs(os.path.dirname(output_filename))
        file_obj.WriteToFile(output_filename)

      if file_obj.is_modified:
        # 1: write the original file to the originals tree
        original_filename = os.path.join(
            self._temp_dir,
            ORIGINAL_DIR,
            file_obj.relative_filename)
        base.MakeDirs(os.path.dirname(original_filename))
        file_obj.WriteToFile(original_filename, original=True)

        # 2: write the modified file to the modified tree
        if file_obj.is_deleted:
          modified_filename = '/dev/null'
        else:
          modified_filename = os.path.join(
              self._temp_dir,
              MODIFIED_DIR,
              file_obj.output_relative_filename)
          base.MakeDirs(os.path.dirname(modified_filename))
          file_obj.WriteToFile(modified_filename)

        # 3: write the diff
        diff_filename = os.path.join(
            self._temp_dir,
            DIFFS_DIR,
            file_obj.relative_filename)
        base.MakeDirs(os.path.dirname(diff_filename))
        p = subprocess.Popen(
            ['diff', original_filename, modified_filename],
            stdout=open(diff_filename, 'w'),
            stderr=open('/dev/null', 'w'))
        p.wait()

        if self.config.modify:
          # 4: write the modified file to the initial tree
          if file_obj.is_deleted:
            os.remove(file_obj.filename)
            print 'Deleted', file_obj.filename
          else:
            tmp_filename = file_obj.filename + '.tmp'
            file_obj.WriteToFile(tmp_filename)
            os.rename(tmp_filename, file_obj.filename)
            print 'Modified', file_obj.filename

    # 5: create output tar
    if self.config.output_tar:
      # Calling out to tar instead of using python's tarfile is 400x faster.
      p = subprocess.Popen(
          ['tar', '-cf', self.config.output_tar,
           '-C', os.path.join(self._temp_dir, OUTPUT_DIR), '.'])
      p.wait()
      if p.returncode:
        self.AddError('tar finished unsuccessfully')
    stopwatch.sw.stop('write_output')

  def CleanUp(self):
    shutil.rmtree(self._temp_dir, ignore_errors=True)

  def RelativeFilename(self, filename):
    result = os.path.abspath(filename).replace(
        self.config.codebase, '', 1)
    if result[0] == '/':
      result = result[1:]
    return result

  def FindFiles(self, config):
    """Find all files to scrub in the codebase.

    Args:
      config: ScrubberConfig

    Returns:
      seq of ScannedFile, the filenames to scan
    """
    if not os.path.isdir(config.codebase):
      self.AddError('%s is not a directory' % config.codebase)
    result = []
    stopwatch.sw.start('find')
    if config.rearranging_config:
      file_renamer = renamer.FileRenamer(config.rearranging_config)
    else:
      file_renamer = None
    for (dirpath, _, filenames) in os.walk(config.codebase):
      for filename in filenames:
        full_filename = os.path.join(dirpath, filename)
        relative_filename = self.RelativeFilename(full_filename)
        if self.config.ignore_files_re.search(relative_filename):
          continue
        if file_renamer:
          output_relative_filename = file_renamer.RenameFile(relative_filename)
        else:
          output_relative_filename = relative_filename
        result.append(ScannedFile(
            full_filename, relative_filename, self._temp_dir,
            output_relative_filename=output_relative_filename))
    stopwatch.sw.stop('find')
    return result

  def _GetExtension(self, filename):
    basename = os.path.basename(filename)
    for filename_re, extension in self.config.extension_map:
      if filename_re.search(filename):
        return extension
    _, extension = os.path.splitext(basename)
    return extension

  def ScrubbersForFile(self, file_obj):
    """Return a seq of base.FileScrubber's appropriate for file_obj."""
    if file_obj.IsBinaryFile():
      return []
    extension = self._GetExtension(file_obj.relative_filename)

    scrubbers = self.config.extension_to_scrubber_map.get(extension, None)
    if scrubbers is not None:
      return scrubbers

    if os.path.basename(file_obj.filename) not in self.config.known_filenames:
      self._unscrubbed_file_extensions.add(extension)
    return self.config.default_scrubbers

  def Scan(self):
    for file_obj in self.files:
      scrubbers = self.ScrubbersForFile(file_obj)
      for scrubber in scrubbers:
        if file_obj.is_deleted:
          # No need to further scrub a deleted file
          break
        scrubber.ScrubFile(file_obj, self)

      sys.stdout.write('.')
      sys.stdout.flush()

    sys.stdout.write('\n')


# Top-level scrubber config keys.
_SCRUBBER_CONFIG_KEYS = [
    # General options
    u'ignore_files_re',
    u'extension_map',
    u'sensitive_string_file',
    u'sensitive_words',
    u'sensitive_res',
    u'whitelist',
    u'scrub_sensitive_comments',
    u'rearranging_config',
    u'string_replacements',

    # User options
    u'usernames_to_scrub',
    u'usernames_to_publish',
    u'usernames_file',
    u'scrub_unknown_users',
    u'scrub_authors',

    # Java options
    u'empty_java_file_action',
    u'maximum_blank_lines',
    u'scrub_java_testsize_annotations',
    u'java_renames',

    # Javascript options
    # Note: js_directory_rename is deprecated in favor of js_directory_renames,
    # which supports multiple rename requests.
    # TODO(user): Remove the old one after all config files have been changed.
    u'js_directory_rename',
    u'js_directory_renames',

    # Python options
    u'python_module_renames',
    u'python_module_removes',
    u'python_shebang_replace',

    # GWT options
    u'scrub_gwt_inherits',

    # proto options
    u'scrub_proto_comments',
    ]


def ScrubberConfigFromJson(codebase,
                           config_json,
                           extension_to_scrubber_map=None,
                           default_scrubbers=None,
                           modify=False,
                           output_tar='',
                           **unused_kwargs):
  """Generate a ScrubberConfig object from a ScrubberConfig JSON object."""

  def SetOption(key, func=None):
    """Set an option in the config from JSON, using the enclosing scope.

    Args:
      key: unicode; the key in the JSON config and corresponding config
           attribute name.
      func: An optional transformation to apply to the JSON value before storing
            in the config.
    """
    if key in config_json:
      value = config_json[key]
      if func is not None:
        value = func(value)
      setattr(config, str(key), value)

  config_utils.CheckJsonKeys('scrubber config', config_json,
                             _SCRUBBER_CONFIG_KEYS)
  config = ScrubberConfig(codebase, extension_to_scrubber_map,
                          default_scrubbers, modify, output_tar)

  # General options.
  SetOption(u'ignore_files_re', func=re.compile)
  SetOption(u'sensitive_words')
  config.sensitive_words = config_json.get(u'sensitive_words', [])
  SetOption(u'extension_map', func=lambda m: [(re.compile(r), e) for r, e in m])
  SetOption(u'sensitive_res')
  sensitive_string_file = config_json.get(u'sensitive_string_file')
  if sensitive_string_file:
    sensitive_string_json = config_utils.ReadConfigFile(sensitive_string_file)
    config_utils.CheckJsonKeys('sensitive string config', sensitive_string_json,
                               [u'sensitive_words', u'sensitive_res'])
    config.sensitive_words.extend(
        sensitive_string_json.get(u'sensitive_words', []))
    config.sensitive_res.extend(sensitive_string_json.get(u'sensitive_res', []))

  whitelist_entries = []
  for entry in config_json.get(u'whitelist', []):
    config_utils.CheckJsonKeys('whitelist entry', entry,
                               [u'filter', u'trigger', u'filename'])
    whitelist_entries.append((entry.get(u'filter', ''),
                              entry.get(u'trigger', ''),
                              entry.get(u'filename', '')))
  config.whitelist = whitelist.Whitelist(whitelist_entries)
  SetOption(u'scrub_sensitive_comments')
  SetOption(u'rearranging_config')
  SetOption(u'string_replacements')

  # User options.
  # TODO(dborowitz): Make the scrubbers pass unicode to the UsernameFilter.
  # TODO(dborowitz): Make these names consistent so we can use SetOption.
  strs = lambda us: [str(u) for u in us]
  if u'usernames_to_publish' in config_json:
    config.publishable_usernames = strs(config_json[u'usernames_to_publish'])
  if u'usernames_to_scrub' in config_json:
    config.scrubbable_usernames = strs(config_json[u'usernames_to_scrub'])
  SetOption(u'usernames_file')
  SetOption(u'scrub_unknown_users')
  SetOption(u'scrub_authors')
  SetOption(u'scrub_proto_comments')

  # Java-specific options.
  action_map = {
      'IGNORE': base.ACTION_IGNORE,
      'DELETE': base.ACTION_DELETE,
      'ERROR': base.ACTION_ERROR,
      }
  SetOption(u'empty_java_file_action', func=lambda a: action_map[a])
  SetOption(u'maximum_blank_lines')
  SetOption(u'scrub_java_testsize_annotations')
  config.java_renames = []
  for rename in config_json.get(u'java_renames', []):
    config_utils.CheckJsonKeys(
        'java rename', rename,
        [u'internal_package', u'public_package'])
    config.java_renames.append(java_scrubber.JavaRenameScrubber(
        rename[u'internal_package'], rename[u'public_package']))

  # Javascript-specific options.
  # TODO(user): Remove js_directory_rename after all config files have been
  # migrated to use js_directory_renames.
  js_directory_rename = config_json.get(u'js_directory_rename')
  if js_directory_rename is not None:
    config_utils.CheckJsonKeys('JS directory rename', js_directory_rename,
                               [u'internal_directory', u'public_directory'])
    config.js_directory_renames.append(line_scrubber.JsDirectoryRename(
        js_directory_rename[u'internal_directory'],
        js_directory_rename[u'public_directory']))

  js_directory_renames = config_json.get(u'js_directory_renames', [])
  for js_directory_rename in js_directory_renames:
    config_utils.CheckJsonKeys('JS directory rename', js_directory_rename,
                               [u'internal_directory', u'public_directory'])
    config.js_directory_renames.append(line_scrubber.JsDirectoryRename(
        js_directory_rename[u'internal_directory'],
        js_directory_rename[u'public_directory']))

  # Python-specific options.
  config.python_module_renames = []
  for rename in config_json.get(u'python_module_renames', []):
    config_utils.CheckJsonKeys(
        'python module rename', rename,
        [u'internal_module', u'public_module', u'as_name'])
    config.python_module_renames.append(python_scrubber.PythonModuleRename(
        rename[u'internal_module'], rename[u'public_module'],
        as_name=rename.get(u'as_name')))

  # TODO(dborowitz): Find out why these are singleton protobufs; possibly
  # flatten them.
  config.python_module_removes = []
  for remove in config_json.get(u'python_module_removes', []):
    config_utils.CheckJsonKeys('python module removal', remove,
                               [u'import_module'])
    config.python_module_removes.append(
        python_scrubber.PythonModuleRemove(remove[u'import_module']))

  python_shebang_replace = config_json.get(u'python_shebang_replace')
  if python_shebang_replace is not None:
    config_utils.CheckJsonKeys('python shebang replacement',
                               python_shebang_replace, [u'shebang_line'])
    config.python_shebang_replace = python_scrubber.PythonShebangReplace(
        python_shebang_replace[u'shebang_line'])

  # GWT-specific options.
  SetOption(u'scrub_gwt_inherits')

  config.ResetScrubbers(extension_to_scrubber_map, default_scrubbers)
  return config


class ScannedFile(object):
  """A ScannedFile is a file to be scrubbed.

  Instance members:
    filename: str, the full path to the file to be scanned
    relative_filename: str, the filename relative to the codebase
    output_relative_filename: str, the relative filename this file should have
                              in the output codebase. This allows us to
                              rearrange codebases during scrubbing.
    is_modified: bool, whether this file has been modified during scrubbing
    _contents: str, the file's current contents
    _in_unicode: True if the file's contents is unicode text, False if it's
                 a binary file
    _temp_dir: str, a temporary directory to use
    is_deleted: bool, if the file has been deleted during scrubbing
  """

  def __init__(self, filename, relative_filename, temp_dir,
               output_relative_filename):
    self.filename = filename
    self.relative_filename = relative_filename
    self.output_relative_filename = output_relative_filename
    self.is_modified = False
    self._contents = None
    self._in_unicode = None
    self._temp_dir = temp_dir
    self.is_deleted = False

  def _ReadContents(self, filename):
    """Read the contents of filename.

    Args:
      filename: str, the string to read the contents of

    Returns:
      (contents (as unicode or str), bool (whether the contents are unicode))

    NB(dbentley): Here's as good a place as any to discuss scrubber's
    handling of unicode.

    The scrubber handles two kinds of files: those in UTF-8, and those not.
    For those not in UTF-8, we believe that they're binary. This is
    sufficient for our interests, because all our source files are in UTF-8.
    We determine this by trying to read a file as UTF-8, and if it works we
    keep it as UTF-8. Otherwise, we consider it binary.

    We then have the contents as unicodes (not strs). We have to be careful
    that we don't handle them as strings. Luckily, if we ever do handle them
    as strings, they will not be able to encode to ascii and we will get an
    exception. I.e., a rather loud boom.
    """
    try:
      return open(filename).read().decode('utf-8'), True
    except UnicodeDecodeError:
      # It's a binary file
      return open(filename).read(), False

  def _PossiblyEncode(self, contents, in_unicode):
    """Encode contents if necessary."""
    if in_unicode:
      return contents.encode('utf-8')
    else:
      return contents

  def IsBinaryFile(self):
    self.Contents()  # make sure it's loaded
    return not self._in_unicode

  def Contents(self):
    """Returns the contents of the file as a unicode."""
    if not self._contents:
      self._contents, self._in_unicode = self._ReadContents(self.filename)
    return self._contents

  def RewriteContent(self, old_text, new_text):
    self._contents = self._contents.replace(old_text, new_text)
    self.is_modified = True

  def WriteContents(self, new_text):
    if self._contents == new_text:
      return
    self._contents = new_text
    self.is_modified = True

  def WriteToFile(self, filename, original=False):
    """Write (possibly original) contents to filename, properly encoded.

    Args:
      filename: str, the filename to write to
      original: bool, whether to write the original file
    """
    self.Contents()   # make sure it's loaded
    if original:
      encoded_contents = self._PossiblyEncode(
          *self._ReadContents(self.filename))
    else:
      encoded_contents = self._PossiblyEncode(self._contents, self._in_unicode)
    file_util.Write(filename, encoded_contents, mode=self.Mode())

  def ContentsFilename(self):
    """Return a name of a file containing the current contents of the file."""
    # We need to make sure our file is read first
    self.Contents()
    if not self.is_modified:
      return self.filename
    filename = os.path.join(self._temp_dir, 'scratch', self.relative_filename)
    base.MakeDirs(os.path.dirname(filename))
    self.WriteToFile(filename)
    return filename

  def Mode(self):
    """Return an idealized mode for the file.

    Returns:
      int
    """
    # By default, files are readable and writeable.
    temp = 6
    statinfo = os.stat(self.filename)
    if statinfo.st_mode & stat.S_IEXEC:
      # if it is executable, make the temp also executable
      temp |= 1
    # now we set the same mode for user, group, and world
    result = temp + (temp << 3) + (temp << 6)
    return result

  def Delete(self):
    """Delete this file."""
    self.is_deleted = True
    self._contents = ''
    self.is_modified = True


class ScrubberError(object):
  def __init__(self, line_number, line_text, file_obj):
    self.line_number = line_number
    self.line_text = line_text
    self.file_obj = file_obj


def ParseConfigFile(filename, codebase):
  """Parse a config file that may be ASCII protobuf or JSON."""
  return ScrubberConfigFromJson(
      codebase,
      config_utils.ReadConfigFile(filename),
      **FLAGS.FlagValuesDict())


def main(args):
  stopwatch.sw.start()
  if not len(args) == 2:
    app.usage(detailed_error='Must list exactly one directory to scrub.',
              exitcode=3)
  codebase = args[1]

  if FLAGS.config_data and FLAGS.config_file:
    raise app.UsageError(
        'Specify at most one of --config_data and --config_file')

  if FLAGS.config_file:
    context = ScrubberContext(ParseConfigFile(FLAGS.config_file, codebase))
  else:
    if FLAGS.config_data:
      json_obj = config_utils.LoadConfig(FLAGS.config_data)
    else:
      json_obj = {}
    config_obj = ScrubberConfigFromJson(
        codebase, json_obj, **FLAGS.FlagValuesDict())
    context = ScrubberContext(config_obj)

  print 'Found %d files' % len(context.files)
  context.Scan()

  context.WriteOutput()
  context.Report()

  stopwatch.sw.stop()
  if FLAGS.stopwatch:
    print stopwatch.sw.dump(verbose=True)

  return context.Status()


if __name__ == '__main__':
  app.run()
