// Copyright 2005 Google Inc. All Rights Reserved.

package com.google.common.base;

import com.google.common.annotations.GwtCompatible;
import com.google.common.annotations.GwtIncompatible;
import com.google.testing.util.NullPointerTester;

import junit.framework.TestCase;

import java.util.Comparator;

/**
 * Unit test for {@link Pair}.
 *
 */
@GwtCompatible(emulated = true)
public class PairTest extends TestCase {

  private static final String FIRST_THING = "first thing";
  private static final Integer SECOND_THING = 12;

  private static final Pair<String,Integer> SIMPLE_PAIR
      = Pair.of(FIRST_THING, SECOND_THING);

  public void testFields() {
    assertEquals(FIRST_THING, SIMPLE_PAIR.first);
    assertEquals(SECOND_THING, SIMPLE_PAIR.second);
    assertEquals(FIRST_THING, SIMPLE_PAIR.getFirst());
    assertEquals(SECOND_THING, SIMPLE_PAIR.getSecond());
  }

  public void testEquals() {
    assertEquals(SIMPLE_PAIR, SIMPLE_PAIR);
    assertEquals(SIMPLE_PAIR, Pair.of(FIRST_THING, SECOND_THING));
    assertEquals(Pair.of(null, null), Pair.of(null, null));
    assertFalse(Pair.of(SECOND_THING, FIRST_THING).equals(SIMPLE_PAIR));
    assertFalse(SIMPLE_PAIR.equals("foo"));
    assertFalse(SIMPLE_PAIR.equals(null));
  }

  public void testHashCode() {
    Pair<String, String> p1 = Pair.of("a", "b");
    Pair<String, String> p2 = Pair.of("a", "b");
    Pair<String, String> p3 = Pair.of("b", "a");
    assertEquals(p1.hashCode(), p2.hashCode());
    assertFalse(p1.hashCode() == p3.hashCode());
  }

  public void testToString() throws Exception {
    assertEquals("(first thing, 12)", SIMPLE_PAIR.toString());
    assertEquals("(null, null)", Pair.of(null, null).toString());
  }

  public void testComparators_reflexive() {
    assertEquals(0, Pair.<String, Integer>compareByFirst()
        .compare(SIMPLE_PAIR, SIMPLE_PAIR));
    assertEquals(0, Pair.<String, Integer>compareBySecond()
        .compare(SIMPLE_PAIR, SIMPLE_PAIR));
  }

  public void testComparators_equal() {
    Pair<Integer, String> pair1 = Pair.of(10, "Aaron");
    Pair<Integer, String> pair2 = Pair.of(10, "Zack");
    Pair<Integer, String> pair3 = Pair.of(15, "Zack");

    Comparator<Pair<Integer, String>> first = Pair.compareByFirst();
    Comparator<Pair<Integer, String>> second = Pair.compareBySecond();

    assertEquals(0, first.compare(pair1, pair2));
    assertEquals(0, first.compare(pair2, pair1));
    assertEquals(0, second.compare(pair2, pair3));
    assertEquals(0, second.compare(pair3, pair2));
  }

  public void testComparators_unequal() {
    Pair<Integer, String> pair1 = Pair.of(10, "Aaron");
    Pair<Integer, String> pair2 = Pair.of(10, "Zack");
    Pair<Integer, String> pair3 = Pair.of(15, "Zack");

    Comparator<Pair<Integer, String>> first = Pair.compareByFirst();
    Comparator<Pair<Integer, String>> second = Pair.compareBySecond();

    assertTrue(0 < first.compare(pair3, pair1));
    assertTrue(first.compare(pair1, pair3) < 0);
    assertTrue(0 < second.compare(pair2, pair1));
    assertTrue(second.compare(pair1, pair2) < 0);
  }

  public void testFirstFunction() {
    Function<Pair<String, Integer>, String> function = Pair.firstFunction();
    assertEquals(FIRST_THING, function.apply(SIMPLE_PAIR));
  }

  public void testSecondFunction() {
    Function<Pair<String, Integer>, Integer> function = Pair.secondFunction();
    assertEquals(SECOND_THING, function.apply(SIMPLE_PAIR));
  }

  @GwtIncompatible("NullPointerTester")
  public void testNullPointers() throws Exception {
    NullPointerTester tester = new NullPointerTester();
    tester.testAllPublicStaticMethods(Pair.class);
    tester.testAllPublicInstanceMethods(Pair.of(1, 2));
    tester.testAllPublicInstanceMethods(Pair.of(null, null));
  }
}
