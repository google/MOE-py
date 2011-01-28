#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.


from google.appengine.api import users
from google.appengine.ext import webapp
from google.appengine.ext.webapp.util import run_wsgi_app

import base
import forms
import models
import project

class MainPage(webapp.RequestHandler):
  def get(self):
    self.response.out.write(
        base.RenderTemplate('main.html',
                            {'names': project.GetProjectNames(),
                             'infos': project.GetProjectInfos()
                             }))


application = webapp.WSGIApplication([
    ('/', MainPage),
    ('/api/cancel_migration', project.CancelMigration),
    ('/api/find_equivalences', project.FindEquivalencesPage),
    ('/api/migration_for_revision', project.MigrationForRevision),
    ('/api/approve_migration', project.ApproveMigration),
    ('/api/unapprove_migration', project.UnapproveMigration),
    ('/api/finish_migration', project.FinishMigration),
    ('/api/migration_info', project.MigrationInfo),
    ('/api/note_equivalence', project.NoteEquivalence),
    ('/api/note_migration', project.NoteMigration),
    ('/api/project/(.*)', project.ProjectApi),
    ('/api/start_migration', project.StartMigration),
    ('/api/update_project', project.UpdateProject),
    ('/api/find_migration', project.FindMigration),
    ('/api/edit_changelog', project.EditChangelog),
    ('/api/update_migration_diff', project.UpdateMigrationDiff),
    ('/api/start_process', project.StartProcess),
    ('/api/update_process', project.UpdateProcess),
    ('/api/end_process', project.EndProcess),
    ('/api/get_last_process', project.GetLastProcess),
    ('/api/note_revisions', project.NoteRevisionsPage),
    ('/api/revisions', project.GetRevisions),
    ('/api/recent_history', project.RecentHistoryPage),
    ('/api/add_comment', project.AddComment),
    ('/api/edit_comment', project.EditComment),
    ('/api/comments', project.GetComments),
    ('/forms', forms.FormsPage),
    ('/project/(.*)/pending', project.PendingMigrationsPage),
    ('/project/(.*)', project.ProjectPage),
    ('/migration/(\d*)', project.MigrationPage),
    ], debug=True)


def profiled_main():
  run_wsgi_app(application)


def main():
  if base.PROFILING_ENABLED:
    base.GetProfiler().runctx("profiled_main()", globals(), locals())
  else:
    profiled_main()


if __name__ == '__main__':
  main()
