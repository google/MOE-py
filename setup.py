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

import sys
from setuptools import setup, find_packages

REQUIRE = [
    'google_apputils>=0.2',
    ]

if sys.version_info < (2, 5):
    REQUIRE += [
        'cElementTree>=1.0',
        ]

if sys.version_info < (2, 6):
    REQUIRE += [
        'simplejson>=2.0',
        ]


MOE_STUBS = [
    ('moe_push_codebase', 'RunPushCodebase'),
    ('moe_manage_codebases', 'RunManageCodebases'),
    ('moe_init_codebases', 'RunInitCodebases'),
    ('moe_scrubber', 'RunScrubber'),
    ]
MOE_ENTRY_POINTS = ['%s = moe.stubs:%s' % s for s in MOE_STUBS]


setup(
    name = 'moe',
    version = '0.1',
    packages = find_packages(exclude=['tests']),
    package_data = {'': ['moe/scrubber/data', 'moe/dbapp']},

    entry_points = {
        'console_scripts': MOE_ENTRY_POINTS,
        },

    setup_requires = REQUIRE,
    install_requires = REQUIRE,

    google_test_dir = 'tests',
    tests_require = REQUIRE + ['mox>=0.5'],

    author = 'Google Inc.',
    author_email='opensource@google.com',
    url='http://code.google.com/p/google-moe',
    )
