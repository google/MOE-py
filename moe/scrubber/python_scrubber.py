#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.
#

"""Scrubbers that are specific to Python."""



import re

from google.apputils import stopwatch

from moe.scrubber import base
from moe.scrubber import line_scrubber


RE_IMPORT = re.compile((r'^(\s*)(?:(?P<from>from)\s+(?P<from_from>\S+)\s+'
                        'import\s+(?P<from_import>\S+)'
                        '(?P<from_as>\s+as\s+\S+)?'
                        '|'
                        '(?P<import>import)\s+(?P<import_module>\S+)'
                        '(?P<import_as>\s+as\s+\S+)?'
                        ')$'))


def ParseImportLine(line):
  """Parse a line potentially containing an import.

  Note that this function does NOT properly handle:
      from foo.bar import FooClass

  It's too expensive to code for and against Python style anyway.

  Args:
    line: string, like "from x import y" or "import x.y"
  Returns:
    None: if the line does not contain an import

    if the line does contain an import, a tuple, either:
      ('from' or 'import', 'fully qualified module', 'indent characters',
      'as characters')

    tuple arg 0 hints whether an absolute or relative name was used
    tuple arg 2 may be used to re-indent the import at the same level
    tuple arg 3 specifies the "as xxx" suffix for the import
  """
  if not line:
    return

  new_line = line.rstrip()
  match = RE_IMPORT.search(new_line)

  if not match:
    return

  if match.group('from') == 'from':
    import_type = 'from'
    module_name = '%s.%s' % (match.group('from_from'),
                             match.group('from_import'))
  elif match.group('import') == 'import':
    import_type = 'import'
    module_name = match.group('import_module')
  else:
    return

  indent = match.group(1)
  if match.group('from_as'):
    as_suffix = match.group('from_as')
  elif match.group('import_as'):
    as_suffix = match.group('import_as')
  else:
    as_suffix = ''

  return (import_type, module_name, indent, as_suffix)


class PythonModuleRename(line_scrubber.LineOrientedScrubber):
  """Scrubs a module name in Python by renaming it."""

  def __init__(self, internal_module, public_module, as_name=None):
    line_scrubber.LineOrientedScrubber.__init__(self)
    self._internal_module = internal_module
    self._public_module = public_module
    self._as_name = as_name

    # replace module name only if it's at the start of the line or preceded by
    # a non-word symbol, and only if it's at the end of the line or followed by
    # a non-word symbol.
    self._replace_import_re = re.compile(
        '(^|(?<=\W))%s($|(?=\W))' % internal_module)
    self._line_replacement = self._public_module
    # Special case when we're replacing "import foo" with "from bar import baz"
    if '.' not in self._internal_module and '.' in self._public_module:
      self._line_replacement = (
          self._public_module[self._public_module.rfind('.') + 1:])
    if self._as_name:
      self._line_replacement = self._as_name

  def ScrubLine(self, line, unused_file_obj):
    """Rename Python modules on a single line."""
    import_line = ParseImportLine(line)
    new_text = None

    if import_line:
      import_type, module_name, indent, as_suffix = import_line

      if not as_suffix and self._as_name:
        as_suffix = ' as %s' % self._as_name

      if as_suffix and as_suffix.rsplit(' ', 1)[-1] == self._public_module:
        as_suffix = ''

      if import_type == 'from':
        if module_name.startswith(self._internal_module):
          module_name = self._ReplaceImport(module_name)
          module_name_parts = module_name.rsplit('.', 1)

          if len(module_name_parts) > 1:
            package_name, module_name = module_name_parts
            new_text = '%sfrom %s import %s%s' % (
                indent,
                package_name, module_name,
                as_suffix)
          else:
            new_text = '%simport %s%s' % (
                indent, module_name, as_suffix)
        else:
          return
      elif import_type == 'import':
        old_module_name = module_name
        module_name = self._ReplaceImport(old_module_name)
        if module_name == old_module_name:
          return
        if '.' not in old_module_name and '.' in module_name:
          new_text = '%sfrom %s import %s%s' % (
              indent,
              module_name[:module_name.rfind('.')],
              module_name[module_name.rfind('.') + 1:],
              as_suffix)
        else:
          new_text = '%simport %s%s' % (
              indent, module_name, as_suffix)
      else:
        return  # shouldn't occur
    else:
      new_text = self._ReplaceLine(line)

    if new_text != line:
      return base.Revision(new_text, 'Rename Python module %s to %s' % (
          self._internal_module, self._public_module))

  def _ReplaceImport(self, s):
    return self._replace_import_re.sub(self._public_module, s)

  def _ReplaceLine(self, s):
    return self._replace_import_re.sub(self._line_replacement, s)


class PythonModuleRemove(line_scrubber.LineOrientedScrubber):
  """Scrubs Python code by removing portions of it.

  Given different arguments, it can remove:
    import_module:  remove import statements for a module
  """

  def __init__(self, import_module):
    line_scrubber.LineOrientedScrubber.__init__(self)
    self._import_module = import_module

  def ScrubLine(self, line, unused_file_obj):
    """Remove Python imports from a single line."""
    new_text = None
    revision = None

    import_line = ParseImportLine(line)
    if not import_line:
      return

    module_name = import_line[1]

    if (module_name == self._import_module or
        (self._import_module.endswith('.') and
         module_name.startswith(self._import_module))):
      new_text = None
      revision = 'Remove import of %s' % module_name

    if revision:
      return base.Revision(new_text, revision)


class PythonShebangReplace(base.FileScrubber):
  """Scrubber which replaces (or adds) shebang line."""

  def __init__(self, shebang_line):
    """Init.

    Args:
      shebang_line: shebang line to use.
    """
    self._shebang = shebang_line
    self._shebang_re = re.compile('^#!.*\n')

  def ScrubFile(self, file_obj, unused_context):
    """Scrub a file."""
    stopwatch.sw.start('python_shebang_scrubber')
    contents = file_obj.Contents()
    contents = self._shebang_re.sub('', contents)
    contents = self._shebang + '\n' + contents
    file_obj.WriteContents(contents)
    stopwatch.sw.stop('python_shebang_scrubber')
