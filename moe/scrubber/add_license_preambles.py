#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""A binary to add license preambles to files.

Currently works only with the Apache license.

TODO(dbentley): work with more licenses as needed.
"""

__author__ = 'dbentley@google.com (Dan Bentley)'

import datetime
import re

from google.apputils import app
import gflags as flags
from google.apputils import resources
from google.apputils import stopwatch

from moe.scrubber import base
from moe.scrubber import scrubber

FLAGS = flags.FLAGS


GOOGLE_RE = re.compile('copyright.*google', re.I)
APACHE_LINE_ONE_RE = re.compile('Licensed under the Apache License', re.I)
APACHE_LINE_TWO_RE = re.compile('You may obtain a copy of the License at', re.I)
APACHE_SHORT_RE = re.compile('Governed by an Apache 2.0 License.', re.I)
BEGINNING_OF_LINE_RE = re.compile('^', re.M)
WHOLE_LINE_RE = re.compile('^.*?$', re.M)

DATA_PREFIX = base.ResourceName('data/')
LICENSE_TEXT = resources.GetResource(
    DATA_PREFIX + 'apache_preamble.txt').rstrip()
LICENSE_TEXT_SHORT = resources.GetResource(
    DATA_PREFIX + 'apache_preamble_short.txt').rstrip()


def ContainsApacheLicense(text):
  """Determines if text contains a copy of the Apache preamble."""
  return ((APACHE_LINE_ONE_RE.search(text) and
           APACHE_LINE_TWO_RE.search(text)) or
          APACHE_SHORT_RE.search(text))


# TODO(dnadasi): Factor out languages into their own classes. This will get rid
# of these awful switches.
def CreateLicenseText(extension, year):
  """Creates the license preamble for a file."""
  preamble = ('Copyright %d Google Inc. All Rights Reserved.\n\n' % year)

  if extension in ('c', 'cc', 'go', 'java', 'scala'):
    preamble += LICENSE_TEXT
    return '/**\n' + BEGINNING_OF_LINE_RE.sub(' * ', preamble) + '\n */\n\n'

  if extension in ('py', 'sh'):
    preamble += LICENSE_TEXT
    return BEGINNING_OF_LINE_RE.sub('# ', preamble) + '\n\n'

  if extension == 'css':
    preamble += LICENSE_TEXT_SHORT
    preamble = WHOLE_LINE_RE.sub(' * \g<0>', preamble)
    return '/*\n%s\n */\n\n' % preamble

  if extension == 'ejs':
    preamble += LICENSE_TEXT
    return '<% /* ' + preamble + ' */ %>'

  if extension == 'html':
    preamble += LICENSE_TEXT_SHORT
    return '<!--\n' + preamble + '\n-->\n'

  if extension == 'js':
    preamble += LICENSE_TEXT
    preamble = BEGINNING_OF_LINE_RE.sub('// ', preamble)
    return preamble + '\n'

  raise NotImplementedError(
      'Can\'t format license text for filetype: %s' % extension)


def CleanCommonNits(contents, extension):
  """Cleans some common artifacts left from the scrubbing process."""
  if extension in ('css', 'js'):
    new_contents = contents.replace(' \n', '\n')
    new_contents = new_contents.replace('/*\n *\n', '/*\n')
    return new_contents.replace('*\n */', '*/')

  if extension == 'html':
    return contents.replace('<!--\n-->\n', '')

  if extension == 'py':
    new_contents = contents.replace(' \n', '\n')
    return new_contents.replace('\n#\n\n', '\n\n')

  return contents


class LicensePreambleAdder(base.FileScrubber):
  """Adds license preambles to files as necessary and possible.

  Args:
    extension: The file extension of the file being scrubbed.
  """

  def __init__(self, extension):
    self._extension = extension

  def ScrubFile(self, file_obj, unused_context):
    """Examine the file and modify it if a license preamble is needed.

    Args:
      file_obj: ScannedFile, the file to scrub
    """
    contents = ''
    copyright_year = datetime.date.today().year
    # search for lines with copyright in them
    for line in file_obj.Contents().splitlines(True):
      if GOOGLE_RE.search(line):
        copyright_year = int(re.search('[0-9]{4}', line).group(0))
      else:
        contents += line
    if ContainsApacheLicense(file_obj.Contents()):
      # This file already has the appropriate license
      return

    # Special case for HTML, since DOCTYPE must come first
    preamble = CreateLicenseText(self._extension, copyright_year)
    preamble_start = 0
    if self._extension == 'html':
      # First '\n' after '<html>'
      preamble_start = contents.find('\n', contents.find('<html>')) + 1
    if self._extension in ('sh', 'py'):
      # First '\n' after '#!'
      preamble_start = contents.find('\n', contents.find('#!')) + 1

    contents = contents[:preamble_start] + preamble + contents[preamble_start:]
    file_obj.WriteContents(CleanCommonNits(contents, self._extension))
    return


def main(args):
  stopwatch.sw.start()
  if not len(args) == 2:
    app.usage(detailed_error='Must list exactly one directory to scrub.',
              exitcode=3)
  codebase = args[1]

  # TODO(dborowitz): put this in a json file in data/.
  ignore_files = ['/.git/', 'infrastructure/rhino1_7R1',
                  'infrastructure/yuicompressor', 'jsmin', '' 'BUILD', 'CONFIG',
                  'CORE', 'OWNERS', 'PRESUBMIT.py', 'QUEUE', 'README', '/bin/',
                  '/docs/']
  ignore_files_re = '|'.join(re.escape(f) for f in ignore_files)

  config = scrubber.ScrubberConfigFromJson(
      codebase,
      {'ignore_files_re': ignore_files_re},
      extension_to_scrubber_map={
          '.c': [LicensePreambleAdder('c')],
          '.cc': [LicensePreambleAdder('cc')],
          '.css': [LicensePreambleAdder('css')],
          '.ejs': [LicensePreambleAdder('ejs')],
          '.gif': [],
          '.go': [LicensePreambleAdder('go')],
          '.html': [LicensePreambleAdder('html')],
          '.ico': [],
          '.jar': [],
          '.java': [LicensePreambleAdder('java')],
          '.jpg': [],
          '.js': [LicensePreambleAdder('js')],
          '.png': [],
          '.py': [LicensePreambleAdder('py')],
          '.scala': [LicensePreambleAdder('scala')],
          '.sh': [LicensePreambleAdder('sh')],
          '.swf': [],
          '.txt': [],
          '.xml': [],
      },
      modify=FLAGS.modify)

  context = scrubber.ScrubberContext(config)

  # TODO(dbentley): refactor further so that this boilerplate
  # is folded in to ScrubberContext's run method.
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
