#!/usr/bin/env python
# Copyright 2009 Google Inc. All Rights Reserved.

"""Sanity check for the comment_scrubber.py."""

__author__ = ('nicksantos@google.com (Nick Santos)')

import os

import json as simplejson

from google.apputils import file_util
import gflags as flags
from google.apputils import basetest

from moe import config_utils
from moe.scrubber import base
from moe.scrubber import comment_scrubber
from moe.scrubber import scrubber as scrubber_module
from moe.scrubber import sensitive_string_scrubber
import test_util
from moe.scrubber import usernames
from moe.scrubber import whitelist


FLAGS = flags.FLAGS

TEST_DATA_DIR = test_util.TestResourceFilename('comment_scrubber_test/')


class FakeContext(object):

  def __init__(self):
    self.errors = []

  def AddError(self, error):
    self.errors.append(error)


def TestCommentExtractor(test_case, extractor, source_file, expected_file):
  comments = extractor.ExtractComments(test_util.FakeFile(filename=source_file))
  expected_text = file_util.Read(expected_file)
  expected_json = simplejson.loads(expected_text)
  expected_comments = comment_scrubber.CommentsFromJson(expected_json)
  test_case.assertListEqual(expected_comments, comments)


class CLikeCommentExtractorTest(basetest.TestCase):
  """Unittests for the C-style comment extractor."""

  def testCLikeCommentExtraction(self):
    for ext in ['c', 'cc', 'go', 'java', 'js', 'php']:
      test_filename = os.path.join(TEST_DATA_DIR, 'test_file.%s.txt' % ext)
      comments_filename = os.path.join(TEST_DATA_DIR, '%s_comments.txt' % ext)
      TestCommentExtractor(self, comment_scrubber.CLikeCommentExtractor(),
                           test_filename, comments_filename)


class HtmlCommentExtractorTest(basetest.TestCase):
  """Unittests for the Html comment extractor."""

  def testHtmlCommentExtraction(self):
    TestCommentExtractor(
        self, comment_scrubber.HtmlCommentExtractor(),
        os.path.join(TEST_DATA_DIR, 'test_file.html.txt'),
        os.path.join(TEST_DATA_DIR, 'html_comments.txt'))


class PythonCommentExtractorTest(basetest.TestCase):
  def testPythonCommentExtraction(self):
    TestCommentExtractor(
        self, comment_scrubber.PythonCommentExtractor(),
        os.path.join(TEST_DATA_DIR, 'test_file.py.txt'),
        os.path.join(TEST_DATA_DIR, 'py_comments.txt'))

  def testRawDocstringExtraction(self):
    TestCommentExtractor(
        self, comment_scrubber.PythonCommentExtractor(),
        os.path.join(TEST_DATA_DIR, 'raw_docstring.py.txt'),
        os.path.join(TEST_DATA_DIR, 'raw_docstring_comments.txt'))


class ShellLikeCommentExtractorTest(basetest.TestCase):
  def testShellLikeCommentExtraction(self):
    TestCommentExtractor(
        self, comment_scrubber.ShellLikeCommentExtractor(),
        os.path.join(TEST_DATA_DIR, 'test_file.sh.txt'),
        os.path.join(TEST_DATA_DIR, 'sh_comments.txt'))


class CommentPreservedTest(basetest.TestCase):
  def assertContentsPreserved(self, contents, extractor):
    scrubber = comment_scrubber.CommentScrubber(extractor)
    fake_file = test_util.FakeFile(contents=contents)
    scrubber.ScrubFile(fake_file, None)
    self.assertMultiLineEqual(contents, fake_file.new_contents)

  def testSimpleCFile(self):
    self.assertContentsPreserved('printf("Hello World\n");',
                                 comment_scrubber.CLikeCommentExtractor())

  # this string exposed a bug caused by using += instead of =
  def testNestedHtmlFile(self):
    self.assertContentsPreserved(
        """<script></script><script></script><script>
    // sometimes functions might be evil and do something like this, but we
    // should still use the original values when returning the filtered array
</script>
""",
        comment_scrubber.HtmlCommentExtractor())


class MoeDirectiveTest(basetest.TestCase):
  """Tests for Moe Directive application."""

  def testEasy(self):
    self.RunScenario('easy')

  def testIntracommentStrip(self):
    self.RunScenario('intracomment_strip')

  def testPythonEasy(self):
    self.RunScenario('easy_python', comment_scrubber.PythonCommentExtractor())

  def testInsert(self):
    self.RunScenario('insert')

  def RunScenario(self, scenario_name, extractor=None):
    if not extractor:
      extractor = comment_scrubber.CLikeCommentExtractor()
    scrubber = comment_scrubber.CommentScrubber(extractor)
    scenario_dir = os.path.join(TEST_DATA_DIR, 'directives', scenario_name)
    unstripped = os.path.join(scenario_dir, 'input.txt')
    file_obj = test_util.FakeFile(filename=unstripped)
    scrubber.ScrubFile(file_obj, None)
    expected = os.path.join(scenario_dir, 'expected.txt')
    out = os.path.join(FLAGS.test_tmpdir, scenario_name+'.out.txt')
    file_util.Write(out, file_obj.new_contents)
    basetest.DiffTestFiles(out, expected)


class CommentScrubberTest(basetest.TestCase):
  """Unittests for the comment-specific scrubbers."""

  def setUp(self):
    string_file = os.path.join(TEST_DATA_DIR, '..', 'sensitive_strings.json')
    self.sensitive_strings = config_utils.ReadConfigFile(string_file)

  def FileObj(self):
    return scrubber_module.ScannedFile('foo', 'foo', FLAGS.test_tmpdir, 'foo')

  def assertRevision(self, scrubber, expected, line):
    result = scrubber.ScrubComment(unicode(line), self.FileObj())
    self.assertTrue(isinstance(result, base.Revision),
                    'Expected revision, got %s' % result)
    self.assertEquals(expected, result.new_text)

  def assertPublish(self, scrubber, line):
    self.assertEquals(None, scrubber.ScrubComment(unicode(line),
                                                  self.FileObj()))

  def assertError(self, scrubber, line):
    self.assertTrue(isinstance(scrubber.ScrubComment(unicode(line),
                                                     self.FileObj()),
                               comment_scrubber.TodoError))

  def UserScrubber(self):
    usernames_file = os.path.join(TEST_DATA_DIR, '..', 'usernames.json')
    username_scrubber = usernames.UsernameFilter(
        usernames_file=usernames_file,
        publishable_usernames=set(['nicksantos', 'dbentley', 'user']),
        scrubbable_usernames=set(['someguy', 'otherguy']))
    return comment_scrubber.TodoScrubber(username_scrubber)

  def assertUserRevision(self, expected, line):
    self.assertRevision(self.UserScrubber(), expected, line)

  def assertUserPublish(self, line):
    self.assertPublish(self.UserScrubber(), unicode(line))

  def assertUserError(self, line):
    self.assertError(self.UserScrubber(), unicode(line))

  def testObviousCases(self):
    self.assertUserPublish('// TODO(nicksantos) ')
    self.assertUserRevision('// TODO(user) ', '// TODO(someguy) ')
    self.assertUserRevision('// NOTE(user) ', '// NOTE(someguy) ')
    self.assertUserRevision('// HACK(user) ', '// HACK(someguy) ')
    self.assertUserRevision('// XXX(user) ', '// XXX(someguy) ')
    self.assertUserRevision('/* XXX(user) */', '/* XXX(someguy) */')
    self.assertUserError('// TODO(dracula) ')

    # Usernames from config file.
    self.assertUserPublish('// TODO(joe_pub) ')
    self.assertUserRevision('// TODO(user) ', '// TODO(joe_scrub) ')
    self.assertUserError('// TODO(joe_nope) ')

  def testPipes(self):
    self.assertUserPublish('// TODO(nicksantos|dbentley)')
    self.assertUserRevision('// TODO(user|nicksantos)',
                            '// TODO(someguy|nicksantos)')
    self.assertUserRevision('// TODO(nicksantos|user)',
                            '// TODO(nicksantos|someguy)')
    self.assertUserRevision('// TODO(user|user)',
                            '// TODO(otherguy|someguy)')

  def testCommas(self):
    self.assertUserPublish('// TODO(nicksantos,dbentley)')
    self.assertUserRevision('// TODO(user,nicksantos)',
                            '// TODO(someguy,nicksantos)')
    self.assertUserRevision('// TODO(nicksantos,user)',
                            '// TODO(nicksantos,someguy)')
    self.assertUserRevision('// TODO(user,user)',
                            '// TODO(otherguy,someguy)')

  def SensitiveWordCommentScrubber(self, white_list):
    words = self.sensitive_strings[u'sensitive_words']
    return comment_scrubber.SensitiveStringCommentScrubber(
        white_list, sensitive_string_scrubber.SensitiveWordScrubber(words))

  def testCodeWords(self):
    white_list = whitelist.Whitelist([])
    scrubber = self.SensitiveWordCommentScrubber(white_list)
    self.assertRevision(scrubber, '', '// testy')
    self.assertPublish(scrubber, '// fine')

  def testWhitelist(self):
    whitelist_entry = ('SENSITIVE_WORD', 'testy', 'foo')
    scrubber = self.SensitiveWordCommentScrubber(
        whitelist.Whitelist([whitelist_entry]))
    self.assertPublish(scrubber, '// testy')

  def testWhitelistStar(self):
    whitelist_entry = ('SENSITIVE_WORD', 'testy', '*')
    scrubber = self.SensitiveWordCommentScrubber(
        whitelist.Whitelist([whitelist_entry]))
    self.assertPublish(scrubber, '// testy')

  def SensitiveReCommentScrubber(self, white_list):
    res = self.sensitive_strings[u'sensitive_res']
    return comment_scrubber.SensitiveStringCommentScrubber(
        white_list, sensitive_string_scrubber.SensitiveReScrubber(res))

  def testCodeRes(self):
    white_list = whitelist.Whitelist([])
    scrubber = self.SensitiveReCommentScrubber(white_list)
    self.assertRevision(scrubber, '', '// xxxsupersecretxxx')
    self.assertPublish(scrubber, '// fine')

  def testReWhitelist(self):
    whitelist_entry = ('SENSITIVE_RE', 'supersecret', 'foo')
    scrubber = self.SensitiveWordCommentScrubber(
        whitelist.Whitelist([whitelist_entry]))
    self.assertPublish(scrubber, '// xxxsupersecretxxx')

  def testNonDocumentationCommentScrubber(self):
    """All non-documentation comments should be removed."""

    scrubber = comment_scrubber.AllNonDocumentationCommentScrubber()
    self.assertRevision(scrubber, '',
                        '/* C comment */')
    self.assertRevision(scrubber, '',
                        '// C++ comment.')
    self.assertRevision(scrubber, '',
                        '# Python comment')
    self.assertPublish(scrubber,
                       '/** Javadoc comment */')
    self.assertPublish(scrubber,
                       '"""Python docstring"""')
    self.assertPublish(scrubber,
                       '// Copyright Google 2011. All rights reserved.')
    self.assertPublish(scrubber,
                       '/* Copyright 2011. */')
    self.assertPublish(scrubber,
                       '/*-{...}-*/')

  def testAllCommentScrubber(self):
    scrubber = comment_scrubber.AllCommentScrubber()
    self.assertRevision(scrubber, '', '/* C comment */')
    self.assertRevision(scrubber, '', '// C++ comment.')
    self.assertRevision(scrubber, '', '# Python comment')
    self.assertRevision(scrubber, '', '/** Javadoc comment */')
    self.assertRevision(scrubber, '', '"""Python docstring"""')
    self.assertPublish(scrubber,
                       '// Copyright Google 2011. All rights reserved.')
    self.assertPublish(scrubber, '/* Copyright 2011. */')
    self.assertPublish(scrubber, '// MOE:begin_strip')
    self.assertPublish(scrubber, '/* MOE:end_strip */')
    self.assertPublish(scrubber, '/* MOE:end_strip_and_replace */')
    self.assertPublish(scrubber, '/* MOE:insert */')
    self.assertPublish(scrubber, '// MOE:begin_intracomment_strip')
    self.assertPublish(scrubber, '/* MOE:end_intracomment_strip */')

  def AuthorDeclarationScrubber(self):
    return comment_scrubber.AuthorDeclarationScrubber(
        username_filter=usernames.UsernameFilter(
            publishable_usernames=set(['publishable'])))

  def testAuthorsObviousCases(self):
    scrubber = self.AuthorDeclarationScrubber()
    self.assertRevision(scrubber, '', '// Author: nicksantos')
    self.assertRevision(scrubber, '', '  Author: nicksantos')
    self.assertRevision(scrubber, '', '* @author nicksantos')
    self.assertRevision(scrubber, '', ' * @author nicksantos')
    self.assertRevision(scrubber, '', '  <!-- Author: nicksantos -->')

    self.assertPublish(scrubber, '// Author: publishable@google.com')
    self.assertPublish(scrubber, '* @author publishable@google.com')
    self.assertPublish(scrubber, '  Author: publishable@google.com')

    self.assertRevision(scrubber, '', '  Author: foo@google.com')

    self.assertPublish(scrubber, '* @author Nicholas.J.Santos@gmail.com')
    self.assertPublish(scrubber, '* @author chadkillingsorth@missouristate.edu')

  def testAuthorsLineInsideCommentBlock(self):
    """The entire author line should be removed from the comment block."""

    scrubber = self.AuthorDeclarationScrubber()
    self.assertRevision(scrubber,
                        '/* Some first comment line.\n'
                        ' */',

                        '/* Some first comment line.\n'
                        ' * @author nicksantos\n'
                        ' */')
    self.assertRevision(scrubber,
                        ' // Some first comment line.\n'
                        ' //',

                        ' // Some first comment line.\n'
                        ' // Author: nicksantos\n'
                        ' //')
    self.assertRevision(scrubber,
                        '  <!--Some first comment line.\n'
                        '-->',

                        '  <!--Some first comment line.\n'
                        ' Author: someuser@google.com (Some User)\n'
                        '-->')

  def testAuthorInString(self):
    scrubber = self.AuthorDeclarationScrubber()
    self.assertPublish(scrubber, '"// Author: nicksantos@google.com"')
    self.assertPublish(scrubber, '"* @author nicksantos@google.com"')

  def assertContents(self, scrubber, expected_lines, actual_lines):
    context = FakeContext()
    file_obj = test_util.FakeFile(contents=u'\n'.join(actual_lines))
    scrubber.ScrubFile(file_obj, context)
    self.assertMultiLineEqual(
        u'\n'.join(expected_lines), file_obj.new_contents)

  def assertContentsError(self, lines):
    context = FakeContext()
    scrubber = comment_scrubber.CommentScrubber(
        comment_scrubber.CLikeCommentExtractor())
    file_obj = test_util.FakeFile(contents=u'\n'.join(lines))
    scrubber.ScrubFile(file_obj, context)
    self.assertEqual(1, len(context.errors))
    error, = context.errors
    self.assertEqual('COMMENT_SCRUBBER_ERROR', error.filter)

  def testDirectiveErrors(self):
    self.assertContentsError(['/* MOE:begin_strip MOE:end_strip */'])
    self.assertContentsError(['/* MOE:begin_strip */',
                              '/* MOE:begin_strip */'])
    self.assertContentsError(['/* MOE:end_strip */'])
    self.assertContentsError(['/* MOE:end_strip_and_replace foo */'])
    self.assertContentsError(['/* MOE:begin_strip */',
                              '/* MOE:insert */',
                              '/* MOE:end_strip */'])
    self.assertContentsError(['/* MOE:foo */'])
    self.assertContentsError(['/* MOE:begin_intracomment_strip */'])
    self.assertContentsError(['/* MOE:end_intracomment_strip */'])
    self.assertContentsError(['/* MOE:end_intracomment_strip',
                              ' * MOE:begin_intracomment_strip */'])
    self.assertContentsError(['/* MOE:begin_strip',
                              ' * MOE:strip_line',
                              ' * MOE:end_strip */'])
    self.assertContentsError(['/* MOE:insert MOE:',
                              ' * MOE:strip_line',
                              ' * MOE:end_intracomment_strip */'])
    self.assertContentsError(['/* MOE:insert MOE:',
                              ' * MOE:strip_line',
                              ' * MOE:end_intracomment_strip */'])
    self.assertContentsError(['/* Block comment',
                              ' * MOE:strip_line',
                              ' */'])

  def CheckReplace(self, extractor, test_cases):
    for input_text, expected in test_cases:
      self.assertEqual(
          expected,
          comment_scrubber._GetReplacementText(input_text, extractor))

  def testExcludeDelimiters(self):
    self.CheckReplace(comment_scrubber.CLikeCommentExtractor(), [
        ('// MOE:end_strip_and_replace foo\n', 'foo\n'),
        ('/* MOE:end_strip_and_replace foo\nbar*/', 'foo\nbar'),
        ])

  def testExcludePythonDelimiters(self):
    self.CheckReplace(comment_scrubber.PythonCommentExtractor(), [
        ('# MOE:end_strip_and_replace foo\n', 'foo\n'),
        ('#MOE:end_strip_and_replace foo\n', 'foo\n'),
        ])

  def testExcludeHtmlDelimiters(self):
    self.CheckReplace(comment_scrubber.HtmlCommentExtractor(), [
        ('<!-- MOE:end_strip_and_replace foo -->', 'foo'),
        ('<!--MOE:end_strip_and_replace foo-->', 'foo'),
        ('<!--MOE:end_strip_and_replace foo\nbar-->', 'foo\nbar'),
        ])

  def testStartAndEndDelimitersC(self):
    scrubber = comment_scrubber.CommentScrubber(
        comment_scrubber.CLikeCommentExtractor())
    self.assertContents(
        scrubber,
        ['// x',
         '// z'],
        ['// x',
         '// MOE:begin_strip',
         '// y',
         '// MOE:end_strip',
         '// z'])

  def testStartAndEndDelimitersPython(self):
    scrubber = comment_scrubber.CommentScrubber(
        comment_scrubber.PythonCommentExtractor())
    self.assertContents(
        scrubber,
        ['# x',
         '# z'],
        ['# x',
         '# MOE:begin_strip',
         '# y',
         '# MOE:end_strip',
         '# z'])

  def testPythonCommentWithoutDelimiters(self):
    extractor = comment_scrubber.PythonCommentExtractor()
    self.assertEqual('foo', extractor.CommentWithoutDelimiters('# foo'))
    self.assertEqual('foo', extractor.CommentWithoutDelimiters('#foo'))
    self.assertEqual('', extractor.CommentWithoutDelimiters('#'))
    self.assertEqual('', extractor.CommentWithoutDelimiters('# '))
    self.assertEqual('foo', extractor.CommentWithoutDelimiters("'''foo'''"))
    self.assertEqual('foo', extractor.CommentWithoutDelimiters('"""foo"""'))
    self.assertEqual('foo', extractor.CommentWithoutDelimiters('r"""foo"""'))
    self.assertEqual('foo', extractor.CommentWithoutDelimiters('u"""foo"""'))
    self.assertEqual('foo', extractor.CommentWithoutDelimiters('ru"""foo"""'))
    self.assertRaises(base.Error, extractor.CommentWithoutDelimiters,
                      '/* whoops */')

  def testHtmlCommentWithoutDelimiters(self):
    extractor = comment_scrubber.HtmlCommentExtractor()
    self.assertEqual('foo', extractor.CommentWithoutDelimiters('<!--foo-->'))
    self.assertEqual('foo>', extractor.CommentWithoutDelimiters('<!--foo>-->'))
    self.assertEqual(' foo', extractor.CommentWithoutDelimiters('<!-- foo-->'))
    self.assertEqual('foo', extractor.CommentWithoutDelimiters('/*foo*/'))
    self.assertEqual('foo', extractor.CommentWithoutDelimiters('//foo'))
    self.assertRaises(base.Error, extractor.CommentWithoutDelimiters,
                      '<!-- whoops */')

  def testStripLineDirectiveC(self):
    scrubber = comment_scrubber.CommentScrubber(
        comment_scrubber.CLikeCommentExtractor())
    self.assertContents(
        scrubber,
        ['int a;',
         'int c;'],
        ['int a;',
         '// MOE:strip_line',
         'int c;'])
    self.assertContents(
        scrubber,
        ['int a;',
         'int c;'],
        ['int a;',
         'int b; // MOE:strip_line The preceding relies on the magic seed 42',
         'int c;'])
    self.assertContents(
        scrubber,
        ['int a;',
         'int c;'],
        ['int a;',
         'int b;  // MOE:strip_line',
         'int c;'])
    self.assertContents(
        scrubber,
        ['int a;',
         'int c;'],
        ['int a;',
         'int b1;  // MOE:strip_line',
         'int b2;  // MOE:strip_line',
         'int c;'])
    self.assertContents(
        scrubber,
        ['int a;',
         'int c;'],
        ['int a;',
         'int b;  // This line and comment are secret. MOE:strip_line',
         'int c;'])
    self.assertContents(
        scrubber,
        ['int a;',
         'int c;'],
        ['int a;',
         'int b;  /* MOE:strip_line */',
         'int c;'])

  def testStripLineDirectivePython(self):
    scrubber = comment_scrubber.CommentScrubber(
        comment_scrubber.PythonCommentExtractor())
    self.assertContents(
        scrubber,
        ['a = ""',
         'c = a'],
        ['a = ""',
         'b = a  # MOE:strip_line',
         'c = a'])

  def testStripLineDirectiveShell(self):
    scrubber = comment_scrubber.CommentScrubber(
        comment_scrubber.ShellLikeCommentExtractor())
    self.assertContents(
        scrubber,
        ['a=""',
         'c=a'],
        ['a=""',
         'b=a  # MOE:strip_line',
         'c=a'])

  def testStripLineDirectiveHtml(self):
    scrubber = comment_scrubber.CommentScrubber(
        comment_scrubber.HtmlCommentExtractor())
    self.assertContents(
        scrubber,
        ['a = ""',
         'c = a'],
        ['a = ""',
         'b = a  <!-- MOE:strip_line -->',
         'c = a'])


if __name__ == '__main__':
  basetest.main()
