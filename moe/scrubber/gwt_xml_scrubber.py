#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Strips the specified GWT XML inherit lines from the given files."""

__author__ = 'arb@google.com (Anthony Baxter)'

from xml.dom import minidom
from google.apputils import stopwatch
from moe.scrubber import base


class GwtXmlScrubber(base.FileScrubber):
  """Scrubs specified inherits clauses from .gwt.xml files."""

  def __init__(self, scrub_inherits):
    """Constructor.

    Args:
      scrub_inherits: a set of inherit names to scrub.
    """
    self.scrub_inherits = scrub_inherits

  def ScrubFile(self, file_obj, unused_context):
    """Performs the actual scrubbing."""
    filename = file_obj.ContentsFilename()
    if not filename.endswith('.gwt.xml'):
      return
    removed = False
    stopwatch.sw.start('scrub_gwt_inherits')

    # The XML parsing does not appreciate the formatting whitespace, so it
    # needs to be stripped out before parsing to prevent the insertion of
    # extra TEXT nodes.
    sanitized_input = ' '.join(line.strip()
                               for line in file_obj.Contents().splitlines())
    dom = minidom.parseString(sanitized_input)

    for inherit in dom.getElementsByTagName('inherits'):
      if inherit.getAttribute('name') in self.scrub_inherits:
        dom.documentElement.removeChild(inherit)
        removed = True

    stopwatch.sw.stop('scrub_gwt_inherits')
    if removed:
      dom.normalize()
      file_obj.WriteContents(dom.toprettyxml(indent='  ', newl='\n',
                                             encoding='utf-8'))
