// Copyright 2005 Google Inc. All Rights Reserved.

package com.google.common.base;

import com.google.common.annotations.GwtCompatible;
import com.google.common.annotations.GwtIncompatible;
import com.google.common.base.Join.JoinException;
import com.google.common.collect.ImmutableMap;
import com.google.common.collect.Iterators;
import com.google.common.collect.Maps;
import com.google.testing.util.NullPointerTester;

import junit.framework.TestCase;

import java.io.IOException;
import java.util.Arrays;
import java.util.Iterator;
import java.util.Map;

/**
 * Unit test for {@link Join}.
 *
 */
@GwtCompatible(emulated = true)
public class JoinTest extends TestCase {

  public void testBasic() throws Exception {
    assertEquals("", Join.join(",", new Object[0])); // no varargs form for this
    assertEquals("a", Join.join(",", "a"));
    assertEquals("a,b,c", Join.join(",", "a", "b", "c"));
    assertEquals("a,null,,b", Join.join(",", "a", null, "", "b"));
  }

  public void testArray() throws Exception {
    String[] array = { "a", "b", "c" };
    assertEquals("a,b,c", Join.join(",", array));
  }

  public void testAppendableIterator() throws Exception {
    Appendable sb = new StringBuilder();
    Iterator<String> iterator = Arrays.asList("a", "b").iterator();
    Join.join(sb, ",", iterator);
    assertEquals("a,b", sb.toString());
  }

  public void testAppendableIterable() throws Exception {
    Appendable sb = new StringBuilder();
    Iterable<String> iterator = Arrays.asList("a", "b");
    Join.join(sb, ",", iterator);
    assertEquals("a,b", sb.toString());
  }

  public void testAppendableVarargs() throws Exception {
    Appendable sb = new StringBuilder();
    Join.join(sb, ",", "a", "b");
    assertEquals("a,b", sb.toString());
  }

  public void testAppendableArray() throws Exception {
    String[] array = { "a", "b", "c" };
    Appendable sb = new StringBuilder();
    Join.join(sb, ",", array);
    assertEquals("a,b,c", sb.toString());
  }

  public void testExceptionGetsChained() throws Exception {
    final IOException ex = new IOException();
    Appendable badAppendable = new Appendable() {
      public Appendable append(CharSequence csq) throws IOException {
        throw ex;
      }
      public Appendable append(CharSequence csq, int start, int end)
          throws IOException {
        throw ex;
      }
      public Appendable append(char c) throws IOException {
        throw ex;
      }
    };

    // This should work
    Join.join(badAppendable, "x", Iterators.emptyIterator());

    try {
      Join.join(badAppendable, "x", "foo");
      fail();
    } catch (JoinException e) {
      assertSame(ex, e.getCause());
    }
  }

  public void testMap() {
    assertEquals("", Join.join("=", ",", ImmutableMap.of()));
    assertEquals("", Join.join("", ",", ImmutableMap.of("", "")));
    assertEquals("=", Join.join("=", ",", ImmutableMap.of("", "")));

    Map<String, String> mapWithNulls = Maps.newLinkedHashMap();
    mapWithNulls.put("a", null);
    mapWithNulls.put(null, "b");
    assertEquals("a=null,null=b", Join.join("=", ",", mapWithNulls));

    StringBuilder sb = new StringBuilder();
    Join.join(sb, ":", " ", ImmutableMap.of(1, 2, 3, 4, 5, 6));
    assertEquals("1:2 3:4 5:6", sb.toString());
  }

  public void testArgumentReturned() {
    StringBuilder sb = new StringBuilder();

    // varargs
    StringBuilder returned = Join.join(sb, "a", "b");
    assertSame(sb, returned);

    // array
    returned = Join.join(sb, ",", new String[] { "a", "b", "c" });
    assertSame(sb, returned);

    // iterable
    returned = Join.join(sb, ",", Arrays.asList("a", "b"));
    assertSame(sb, returned);

    // iterator
    returned = Join.join(sb, ",", Arrays.asList("a", "b").iterator());
    assertSame(sb, returned);

    // map
    returned = Join.join(sb, "=", ",", ImmutableMap.of("a", "b"));
    assertSame(sb, returned);
  }

  @GwtIncompatible("NullPointerTester")
  public void testNullPointerExceptions() throws Exception {
    NullPointerTester tester = new NullPointerTester();
    tester.testAllPublicStaticMethods(Join.class);
  }
}
