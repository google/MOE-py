#!/usr/bin/env python
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template

import base


class FormsPage(webapp.RequestHandler):
  def get(self):
    self.response.out.write(
        base.RenderTemplate('forms.html', {}))
