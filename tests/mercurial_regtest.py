#!/usr/bin/env python
#
# Copyright 2010 Google Inc. All Rights Reserved.

"""Tests for moe.mercurial."""

__author__ = 'dbentley@google.com (Daniel Bentley)'

from google.apputils import basetest

from moe import base
from moe import mercurial
from moe import moe_app
import test_util


REPO = None

def setUp():
  global REPO
  moe_app.InitForTest()
  REPO = mercurial.MercurialRepository(
      EXAMPLE_REPOSITORY_URL,
      'test')


# We use an actual repository for end-to-end testing.
EXAMPLE_REPOSITORY_URL = 'https://jgments.googlecode.com/hg/'

class MercurialTest(basetest.TestCase):

  def testHeadRevision(self):
    self.assertEqual('47b097c7d97e', REPO.GetHeadRevision('47b097c7d97e'))
    self.assertNotEqual('47b097c7d97e', REPO.GetHeadRevision())

  def testRevisionsSinceEquivalence(self):
    db = test_util.MockDbClient()
    equiv = base.Correspondence('1001', '2996fd487ac1')
    db.NoteEquivalence(equiv)
    rs, eqs = REPO.RevisionsSinceEquivalence('ceadf5c0ce18', base.PUBLIC, db)
    rev_ids = [r.rev_id for r in rs]
    self.assertListEqual(['ceadf5c0ce18', '47b097c7d97e', '2b02deffcc80'],
                         rev_ids)

  def testRevisionFromId(self):
    REPO.MakeRevisionFromId('123456789012')


if __name__ == '__main__':
  basetest.main()
