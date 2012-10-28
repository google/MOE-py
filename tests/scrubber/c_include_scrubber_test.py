#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""Sanity check for c_include_scrubber.py."""



from google.apputils import basetest

from moe.scrubber import base
from moe.scrubber import c_include_scrubber


class FakeScannedFile(object):
  def __init__(self, contents, fake_filename):
    """The fake-filename is used to match glob patterns in the config file."""
    self._contents = contents
    # TODO(user): should we try to distinguish between these filenames?
    self._contents_filename = fake_filename
    self.filename = fake_filename
    self.output_relative_filename = fake_filename
    self.new_contents = contents

  def Contents(self):
    return self._contents.decode('utf-8')

  def ContentsFilename(self):
    return self._contents_filename

  def WriteContents(self, new_contents):
    self.new_contents = new_contents


class CIncludeScrubberTestBase(basetest.TestCase):
  """Unittests for the c-includes-scrubber.

  All tests run the full include-scrubber.  They take as input a
  json config file (specifying how to scrub include lines), and
  a source file that is edited.  The source file text includes
  both the input and output text in 'unified diff' format.  Lines
  that start with '///+' are taken to be in the post-scrubbed
  version of the file but not pre-scrubbed.  Lines that end with
  '///-' are taken to be in the pre-scrubbed version but not the
  post-scrubbed.  All other lines are assumed to be in both.
  """

  def ApplyDiffs(self, file_contents_with_diff_markup):
    """Parse ///+ and ///- lines and return 'pre-text' and 'post-text'."""
    before = []
    after = []
    for line in file_contents_with_diff_markup.splitlines():
      if line.startswith('///+'):
        after.append(line[len('///+'):])
      elif line.endswith('///-'):
        # Also get rid of the spaces before the ///-
        before.append(line[:-len('///-')].rstrip())
      else:
        before.append(line)
        after.append(line)
    return ('\n'.join(before), '\n'.join(after))

  def RunIncludeScrubber(self, config_contents, file_contents_with_diff_markup,
                         filename):
    (file_contents, expected_rewritten_contents) = self.ApplyDiffs(
        file_contents_with_diff_markup)

    scanned_file = FakeScannedFile(file_contents, filename)
    scrubber = c_include_scrubber.IncludeScrubber(
        c_includes_config_string=config_contents)
    scrubber.ScrubFile(scanned_file, unused_context=None)
    self.assertEqual(expected_rewritten_contents, scanned_file.new_contents)


class CIncludeScrubber_ParseConfigTest(CIncludeScrubberTestBase):
  def RunParse(self, config_contents, should_raise=False):
    """If should_raise is True, parsing should raise a value-error."""
    if should_raise:
      self.assertRaises(base.Error, c_include_scrubber.IncludeScrubber,
                        None, config_contents)
    else:
      _ = c_include_scrubber.IncludeScrubber(None, config_contents)

  def testParseSimpleConfig(self):
    config = r'{ "#include <stdio.h>": "#include <google_stdio.h>" }'
    self.RunParse(config)

  def testParseComplexConfig(self):
    config = r"""
{
  "#include \"util/gtl/([^\"]*)\"": "#include \"\\1\"",
  "#include \"base/([^\"]*)\"": "#include <google/\\1>",
  "#include <unistd.h>": [
     "#ifdef HAVE_UNISTD_H",
     "# include <unistd.h>",
     "#endif"
  ],
  "#": "test",
  "insert first": "// Includes follow here.",
  "tests/*": {
    "#include <malloc.h>": [
       "#ifdef HAVE_MALLOC_H",
       "# include <malloc.h>",
       "#endif"
     ],
    "#include \"testing/[^\"]*\"": "#include \"testing/foo.h\"",
    "insert first": [
      "// Needed for all testing files",
      "#include \"config_for_testing.h\""
    ],
    "tests/subdir/*": {
      "#include \"(subdir/[^\"]*)\"": "#include \"\\1.h\""
    }
  }
}
"""
    self.RunParse(config)

  def testParseIllegalGlobKey(self):
    """If you're not an #include or 'insert first', value must be a dict."""
    config = r'{ "random text": "more random text" }'
    self.RunParse(config, should_raise=True)

  def testParseComment(self):
    """# is a comment, and everything starting with # except #include."""
    config = r'{ "# random text": "more random text", "#": "even more text" }'
    self.RunParse(config)


class CIncludeScrubber_RewriteTest(CIncludeScrubberTestBase):
  def testSimpleRewrite(self):
    config = r'{ "#include <stdio.h>": "#include <google_stdio.h>" }'
    source_file = """
// Copyright 2011

#include <stdlib.h>
#include <stdio.h>     ///-
///+#include <google_stdio.h>
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testRewriteWithComment(self):
    config = r'{ "#include <stdio.h>": "#include <google_stdio.h>" }'
    source_file = """
// Copyright 2011

#include <stdlib.h>
#include <stdio.h>  // The best kind of io!     ///-
///+#include <google_stdio.h>  // The best kind of io!
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testRewriteWithWeirdlySpacedIncludeLine(self):
    config = r'{ "#include <stdio.h>": "#include <google_stdio.h>" }'
    source_file = """
// Copyright 2011

#include <stdlib.h>
# include    <stdio.h>   ///-
///+#include <google_stdio.h>
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testMultilineRewrite(self):
    config = r"""
{
  "#include <stdio.h>": [ "// An include!", "#include <google_stdio.h>" ]
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>
# include    <stdio.h>   ///-
///+// An include!
///+#include <google_stdio.h>
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testMultilineRewriteWithComment(self):
    config = r"""
{
  "#include <stdio.h>": [ "// An include!", "#include <google_stdio.h>" ]
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>
# include    <stdio.h>  // On the include line ///-
///+// An include!
///+#include <google_stdio.h>  // On the include line
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testMultilineRewriteWithCommentThatCouldBeHandledBetter(self):
    config = r"""
{
  "#include <stdio.h>": [ "#include <google_stdio.h>", "// Next line" ]
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>
# include    <stdio.h>  // On the include line...or is it? ///-
///+#include <google_stdio.h>
///+// Next line  // On the include line...or is it?
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testRegexpRewrite(self):
    config = r'{ "#include <([^>]*)>": "#include <google_\\1>" }'
    source_file = """
// Copyright 2011

#include <stdlib.h>      ///-
# include    <stdio.h>   ///-
///+#include <google_stdlib.h>
///+#include <google_stdio.h>
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')


class CIncludeScrubber_InsertFirstTest(CIncludeScrubberTestBase):
  def testSimpleInsertFirst(self):
    config = r'{ "insert first": "#include <config.h>" }'
    source_file = """
// Copyright 2011

///+#include <config.h>
#include <stdlib.h>

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testMultlineInsertFirst(self):
    config = r'{ "insert first": ["// Need a config", "#include <config.h>"] }'
    source_file = """
// Copyright 2011

///+// Need a config
///+#include <config.h>
#include <stdlib.h>

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testInsertFirstWithIncludeGuard(self):
    config = r'{ "insert first": "#include <config.h>" }'
    source_file = """
// Copyright 2011

#ifndef FOO_H
#define FOO_H

///+#include <config.h>
#include <stdlib.h>

#endif
"""
    self.RunIncludeScrubber(config, source_file, 'foo.h')

  def testInsertFirstWithNoIncludeGuardBecauseFileIsNotAnHFile(self):
    config = r'{ "insert first": "#include <config.h>" }'
    source_file = """
// Copyright 2011

///+#include <config.h>
#ifndef FOO_H
#define FOO_H

#include <stdlib.h>

#endif
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testInsertFirstWithSingleLineCComment(self):
    config = r'{ "insert first": "#include <config.h>" }'
    source_file = """
/* Copyright 2011 */

///+#include <config.h>
#include <stdlib.h>

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testInsertFirstWithTrailingComment(self):
    config = r'{ "insert first": "#include <config.h>" }'
    source_file = """
/* Copyright 2011 */

///+#include <config.h>
const int x = 5;    // This is a contentful line

#include <stdlib.h>

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testInsertFirstWithTrailingCComment(self):
    config = r'{ "insert first": "#include <config.h>" }'
    source_file = """
/* Copyright 2011 */

///+#include <config.h>
const int x = 5;    /* This is a contentful line */

#include <stdlib.h>

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testInsertFirstWithMultilineCComment(self):
    config = r'{ "insert first": "#include <config.h>" }'
    source_file = """
/*
 * Copyright 2011
 */

///+#include <config.h>
#include <stdlib.h>

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')

  def testInsertFirstWithNoContentfulLines(self):
    config = r'{ "insert first": "#include <config.h>" }'
    # Doesn't bother to add any new #include text in this case.
    source_file = """
/*
 * Copyright 2011
 */
"""
    self.RunIncludeScrubber(config, source_file, 'foo.cc')


class CIncludeScrubber_GlobTest(CIncludeScrubberTestBase):
  """Test the functionality of limiting fixes to certain files."""
  def testMatchingGlob(self):
    config = r"""
{
   "test*.cc": { "#include <stdio.h>": "#include <google_stdio.h>" }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>
#include <stdio.h>     ///-
///+#include <google_stdio.h>
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'test.cc')

  def testNonMatchingGlob(self):
    config = r"""
{
   "test*.cc": { "#include <stdio.h>": "#include <google_stdio.h>" }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>
#include <stdio.h>
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'test.h')

  def testMatchingGlobPlusGlobalChange(self):
    config = r"""
{
   "#include <stdlib.h>": "#include <google_stdlib.h>",
   "test*.cc": { "#include <stdio.h>": "#include <google_stdio.h>" }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>  ///-
#include <stdio.h>   ///-
///+#include <google_stdlib.h>
///+#include <google_stdio.h>

#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'test.cc')

  def testNonmatchingGlobPlusGlobalChange(self):
    config = r"""
{
   "#include <stdlib.h>": "#include <google_stdlib.h>",
   "test*.cc": { "#include <stdio.h>": "#include <google_stdio.h>" }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>  ///-
///+#include <google_stdlib.h>
#include <stdio.h>
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'test.h')

  def testInterferingMatchingGlobPlusGlobalChange(self):
    # Because it's not guaranteed what order the rewrites happen,
    # I picked rewrites that are commutative: we get the same
    # end result regardless of which is applied first.
    config = r"""
{
   "#include <([^>]*)>": "#include <google_\\1>",
   "test*.cc": { "#include <(.*)stdio.h>": "#include <google_\\1stdio.h>" }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>  ///-
#include <stdio.h>   ///-
///+#include <google_stdlib.h>
///+#include <google_google_stdio.h>

#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'test.cc')

  def testTwoMatchingGlobs(self):
    # Because it's not guaranteed what order the rewrites happen,
    # I picked rewrites that are commutative: we get the same
    # end result regardless of which is applied first.
    config = r"""
{
   "*.cc": { "#include <stdlib.h>": "#include <google_stdlib.h>" },
   "test*": { "#include <stdio.h>": "#include <google_stdio.h>" }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>  ///-
#include <stdio.h>   ///-
///+#include <google_stdlib.h>
///+#include <google_stdio.h>

#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'test.cc')

  def testMultipleGlobs(self):
    # Because it's not guaranteed what order the rewrites happen,
    # I picked rewrites that are commutative: we get the same
    # end result regardless of which is applied first.
    config = r"""
{
   "*.cc|*.h": { "#include <stdlib.h>": "#include <google_stdlib.h>" },
   "test*|baz*": { "#include <stdio.h>": "#include <google_stdio.h>" }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>  ///-
#include <stdio.h>   ///-
///+#include <google_stdlib.h>
///+#include <google_stdio.h>

#include "google/foo.h"

int main() { return 0; }
"""
    # These all match one or the other of the glob choices above in each rule.
    self.RunIncludeScrubber(config, source_file, 'test.cc')
    self.RunIncludeScrubber(config, source_file, 'baz.cc')
    self.RunIncludeScrubber(config, source_file, 'baz.h')
    self.RunIncludeScrubber(config, source_file, 'test.h')

  def testTwoMatchingNestedGlobs(self):
    # Because it's not guaranteed what order the rewrites happen,
    # I picked rewrites that are commutative: we get the same
    # end result regardless of which is applied first.
    config = r"""
{
   "test*": {
     "#include <stdio.h>": "#include <google_stdio.h>",
     "*.cc": { "#include <stdlib.h>": "#include <google_stdlib.h>" }
   }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>  ///-
#include <stdio.h>   ///-
///+#include <google_stdlib.h>
///+#include <google_stdio.h>

#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'test.cc')

  def testOnlyOneMatchingNestedGlob(self):
    # Because it's not guaranteed what order the rewrites happen,
    # I picked rewrites that are commutative: we get the same
    # end result regardless of which is applied first.
    config = r"""
{
   "test*": {
     "#include <stdio.h>": "#include <google_stdio.h>",
     "*.h": { "#include <stdlib.h>": "#include <google_stdlib.h>" }
   }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>
#include <stdio.h>   ///-
///+#include <google_stdio.h>

#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'test.cc')

  def testSingleStarAndSlashSuccess(self):
    config = r"""
{
   "test/*.cc": { "#include <stdio.h>": "#include <google_stdio.h>" }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>
#include <stdio.h>     ///-
///+#include <google_stdio.h>
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'test/foo.cc')

  def testSingleStarAndSlashFailure(self):
    config = r"""
{
   "test/*.cc": { "#include <stdio.h>": "#include <google_stdio.h>" }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>
#include <stdio.h>
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'test/foo/bar.cc')

  def testDoubleStarAndSlashSuccess(self):
    config = r"""
{
   "test/**.cc": { "#include <stdio.h>": "#include <google_stdio.h>" }
}
"""
    source_file = """
// Copyright 2011

#include <stdlib.h>
#include <stdio.h>     ///-
///+#include <google_stdio.h>
#include "google/foo.h"

int main() { return 0; }
"""
    self.RunIncludeScrubber(config, source_file, 'test/foo/bar.cc')

if __name__ == '__main__':
  basetest.main()
