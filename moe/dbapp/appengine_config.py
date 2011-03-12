#!/usr/bin/env python
import cache

def webapp_add_wsgi_middleware(app):
    from google.appengine.ext.appstats import recording
    app = recording.appstats_wsgi_middleware(app)
    app = cache.CacheResettingMiddleware(app)
    return app
