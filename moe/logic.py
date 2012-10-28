#!/usr/bin/env python
#
# Copyright 2011 Google Inc. All Rights Reserved.

"""MOE logic functions.

This is a module for functions that operate on MOE data structures to answer
questions related to MOE operations. E.g., DetermineCorresondingInternalRevision
belongs here. Factorial doesn't. These functions should be useful in more than
one MOE app, and so deserve a common home to prevent app-on-app dependencies.
"""

__author__ = 'dbentley@google.com (Daniel Bentley)'


from moe import base
from moe import moe_app

def VerifyEquivalences(db, internal_repository, public_repository):
  """Verify equivalences, for each marking it verified or invalid.

  Args:
    db: MoeDbClient
    internal_repository: SourceControlRepository
    public_repository: SourceControlRepository
  """
  equivalences = db.FindUnverifiedEquivalences()
  for e in equivalences:
    verified_internal_revision = internal_repository.GetHeadRevision(
        e.internal_revision)
    verified_public_revision = public_repository.GetHeadRevision(
        e.public_revision)
    if verified_internal_revision and verified_public_revision:
      new_equivalence = base.Correspondence(verified_internal_revision,
                                            verified_public_revision)
      db.NoteEquivalence(new_equivalence)

    if (verified_internal_revision != e.internal_revision or
        verified_public_revision != e.public_revision):

      if verified_internal_revision and verified_public_revision:
        moe_app.RUN.ui.Info(
            ('Found invalid Equivalence. (Replaced with:)\n'
             'Internal Revision: %s (%s)\n'
             'Public Revision: %s (%s)') %
            (e.internal_revision, verified_internal_revision,
             e.public_revision, verified_public_revision))
      else:
        moe_app.RUN.ui.Info(
            ('Found invalid Equivalence.\n'
             'Internal Revision: %s\n'
             'Public Revision: %s') %
            (e.internal_revision, e.public_revision))


      db.NoteEquivalence(e, verification_status=base.VERIFICATION_INVALID)
