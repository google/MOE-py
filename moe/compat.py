#!/usr/bin/env python
# Copyright 2010 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Compatibility module for third-party modules with multiple names.

This module defines some aliases for modules that were third-party in older
versions of Python, but have since been incorporated into the standard library
under different names.
"""

__author__ = 'dborowitz@google.com (Dave Borowitz)'


try:
  import json
except ImportError:
  import json


try:
  from xml.etree import cElementTree
except ImportError:
  from compat import cElementTree
