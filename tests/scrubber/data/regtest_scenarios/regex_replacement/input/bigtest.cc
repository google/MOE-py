#ifndef FOO_BIGTEST_H
#define FOO_BIGTEST_H

#ifdef USE_BAR
#  include "foo/bar.h"
#  include "foo/baz.h"
#endif  // USE_BAR

// This is part of GTEST.
class Bigtest {
  // ...
};

#endif  // FOO_BIGTEST_H
