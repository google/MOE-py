// Copyright (C) 2008 Google Inc.

package com.google.common.base;

import com.google.common.annotations.GwtCompatible;
import com.google.common.annotations.GwtIncompatible;
import com.google.testing.util.EqualsTester;
import com.google.testing.util.NullPointerTester;
import com.google.testing.util.SerializableTester;

import junit.framework.TestCase;

import java.util.Arrays;
import java.util.List;

/**
 * Unit test for static utility methods in {@link BinaryPredicates}.
 *
 */
@GwtCompatible(emulated = true)
public class BinaryPredicatesTest extends TestCase {

  public void testAlwaysTrue_apply() {
    BinaryPredicate<Object, Object> bp = BinaryPredicates.alwaysTrue();

    assertTrue(bp.apply("one", "two"));
    assertTrue(bp.apply("one", null));
    assertTrue(bp.apply(null, "two"));
    assertTrue(bp.apply(null, null));
  }

  public void testAlwaysTrue_equals() {
    EqualsTester tester = new EqualsTester(ALWAYS_TRUE);
    tester.addEqualObject(BinaryPredicates.alwaysTrue());
    tester.addNotEqualObject(ALWAYS_FALSE);
    tester.testEquals();
  }

  public void testAlwaysTrue_isSingleton() {
    BinaryPredicate<Object, Object> bp1 = BinaryPredicates.alwaysTrue();
    BinaryPredicate<Object, Object> bp2 = BinaryPredicates.alwaysTrue();
    assertSame(bp1, bp2);
  }

  @GwtIncompatible("SerializableTester")
  public void testAlwaysTrue_isSerializableSingleton() {
    BinaryPredicate<Object, Object> bp1 = BinaryPredicates.alwaysTrue();
    BinaryPredicate<Object, Object> bp2 = BinaryPredicates.alwaysTrue();
    assertSame(bp1, bp2);
    assertSame(bp1, SerializableTester.reserializeAndAssert(bp1));
  }

  public void testAlwaysFalse_apply() {
    BinaryPredicate<Object, Object> bp = BinaryPredicates.alwaysFalse();

    assertFalse(bp.apply("one", "two"));
    assertFalse(bp.apply("one", null));
    assertFalse(bp.apply(null, "two"));
    assertFalse(bp.apply(null, null));
  }

  public void testAlwaysFalse_equals() {
    EqualsTester tester = new EqualsTester(ALWAYS_FALSE);
    tester.addEqualObject(BinaryPredicates.alwaysFalse());
    tester.addNotEqualObject(ALWAYS_TRUE);
    tester.testEquals();
  }

  public void testAlwaysFalse_isSingleton() {
    BinaryPredicate<Object, Object> bp1 = BinaryPredicates.alwaysFalse();
    BinaryPredicate<Object, Object> bp2 = BinaryPredicates.alwaysFalse();
    assertSame(bp1, bp2);
  }

  @GwtIncompatible("SerializableTester")
  public void testAlwaysFalse_isSerializableSingleton() {
    BinaryPredicate<Object, Object> bp1 = BinaryPredicates.alwaysFalse();
    BinaryPredicate<Object, Object> bp2 = BinaryPredicates.alwaysFalse();
    assertSame(bp1, bp2);
    assertSame(bp1, SerializableTester.reserializeAndAssert(bp1));
  }

  public void testEquality_apply() {
    BinaryPredicate<Object, Object> bp = BinaryPredicates.equality();

    assertTrue(bp.apply("one", "one"));
    assertTrue(bp.apply("one", new String("one")));
    assertFalse(bp.apply("one", "two"));
    assertFalse(bp.apply("one", null));
    assertFalse(bp.apply(null, "two"));
    assertTrue(bp.apply(null, null));
  }

  public void testEquality_equals() {
    EqualsTester tester = new EqualsTester(BinaryPredicates.equality());
    tester.addEqualObject(BinaryPredicates.equality());
    tester.addNotEqualObject(
        ALWAYS_TRUE, ALWAYS_FALSE, BinaryPredicates.identity());
    tester.testEquals();
  }

  public void testEquality_isSingleton() {
    BinaryPredicate<Object, Object> bp1 = BinaryPredicates.equality();
    BinaryPredicate<Object, Object> bp2 = BinaryPredicates.equality();
    assertSame(bp1, bp2);
  }

  @GwtIncompatible("SerializableTester")
  public void testEquality_isSerializableSingleton() {
    BinaryPredicate<Object, Object> bp1 = BinaryPredicates.equality();
    BinaryPredicate<Object, Object> bp2 = BinaryPredicates.equality();
    assertSame(bp1, bp2);
    assertSame(bp1, SerializableTester.reserializeAndAssert(bp1));
  }

  public void testIdentity_apply() {
    BinaryPredicate<Object, Object> bp = BinaryPredicates.identity();

    assertTrue(bp.apply("one", "one"));
    assertFalse(bp.apply(new Long(135135135L), new Long(135135135L)));
    assertFalse(bp.apply("one", "two"));
    assertFalse(bp.apply("one", null));
    assertFalse(bp.apply(null, "two"));
    assertTrue(bp.apply(null, null));
  }

  public void testIdentity_equals() {
    EqualsTester tester = new EqualsTester(BinaryPredicates.identity());
    tester.addEqualObject(BinaryPredicates.identity());
    tester.addNotEqualObject(
        ALWAYS_TRUE, ALWAYS_FALSE, BinaryPredicates.equality());
    tester.testEquals();
  }

  public void testIdentity_isSingleton() {
    BinaryPredicate<Object, Object> bp1 = BinaryPredicates.identity();
    BinaryPredicate<Object, Object> bp2 = BinaryPredicates.identity();
    assertSame(bp1, bp2);
  }

  @GwtIncompatible("SerializableTester")
  public void testIdentity_isSerializableSingleton() {
    BinaryPredicate<Object, Object> bp1 = BinaryPredicates.identity();
    BinaryPredicate<Object, Object> bp2 = BinaryPredicates.identity();
    assertSame(bp1, bp2);
    assertSame(bp1, SerializableTester.reserializeAndAssert(bp1));
  }

  public void testFirst_apply() {
    BinaryPredicate<String, ? super Integer> bp =
        BinaryPredicates.first(Predicates.equalTo("one"));
    assertTrue(bp.apply("one", 1));
    assertFalse(bp.apply("two", 2));
    assertFalse(bp.apply(null, null));
  }

  public void testFirst_equals() {
    EqualsTester tester = new EqualsTester(
        BinaryPredicates.first(Predicates.isNull()));
    tester.addEqualObject(
        BinaryPredicates.first(Predicates.isNull()));
    tester.addNotEqualObject(
        ALWAYS_TRUE, ALWAYS_FALSE,
        BinaryPredicates.first(Predicates.alwaysFalse()),
        BinaryPredicates.first(Predicates.alwaysTrue()),
        BinaryPredicates.second(Predicates.isNull()));
    tester.testEquals();
  }

  public void testSecond_apply() {
    BinaryPredicate<? super String, Integer> bp =
        BinaryPredicates.second(Predicates.equalTo(2));
    assertFalse(bp.apply("one", 1));
    assertTrue(bp.apply("two", 2));
    assertFalse(bp.apply(null, null));
  }

  public void testSecond_equals() {
    EqualsTester tester = new EqualsTester(
        BinaryPredicates.second(Predicates.isNull()));
    tester.addEqualObject(
        BinaryPredicates.second(Predicates.isNull()));
    tester.addNotEqualObject(
        ALWAYS_TRUE, ALWAYS_FALSE,
        BinaryPredicates.second(Predicates.alwaysFalse()),
        BinaryPredicates.second(Predicates.alwaysTrue()),
        BinaryPredicates.first(Predicates.isNull()));
    tester.testEquals();
  }

  private static <X, Y> BinaryPredicate<X, Y> throwsBinaryPredicate(
      final RuntimeException e) {
    return new BinaryPredicate<X, Y>() {
      @Override public boolean apply(X x, Y y) {
        throw e;
      }
    };
  }

  private static final BinaryPredicate<Object, Object>
      ALWAYS_TRUE = BinaryPredicates.alwaysTrue();
  private static final BinaryPredicate<Object, Object>
      ALWAYS_FALSE = BinaryPredicates.alwaysFalse();

  public void testAnd_ofTwoBinaryPredicates_apply() {
    String x = "these arguments don't matter";
    Integer y = 2;
    assertTrue(BinaryPredicates.and(ALWAYS_TRUE, ALWAYS_TRUE).apply(x, y));
    assertFalse(BinaryPredicates.and(ALWAYS_TRUE, ALWAYS_FALSE).apply(x, y));
    assertFalse(BinaryPredicates.and(ALWAYS_FALSE, ALWAYS_TRUE).apply(x, y));
    assertFalse(BinaryPredicates.and(ALWAYS_FALSE, ALWAYS_FALSE).apply(x, y));

    ArithmeticException expected = new ArithmeticException();

    BinaryPredicate<String, Integer> trueAndThrow =
        BinaryPredicates.and(ALWAYS_TRUE, throwsBinaryPredicate(expected));
    try {
      trueAndThrow.apply(x, y);
      fail("Should throw exception from second Relation");
    } catch (ArithmeticException actual) {
      assertSame(expected, actual);
    }

    BinaryPredicate<String, Integer> falseAndThrow =
        BinaryPredicates.and(ALWAYS_FALSE, throwsBinaryPredicate(expected));

    assertFalse("Should short-circuit when first part of 'and' is false",
        falseAndThrow.apply(x, y));
  }

  @SuppressWarnings("unchecked")
  public void testAnd_ofVarArgs_apply() {
    String x = "these arguments don't matter";
    Integer y = 2;
    assertTrue(BinaryPredicates.and().apply(x, y));
    assertTrue(BinaryPredicates.and(ALWAYS_TRUE).apply(x, y));
    assertFalse(BinaryPredicates.and(ALWAYS_FALSE).apply(x, y));
    assertTrue(BinaryPredicates.and(
        ALWAYS_TRUE, ALWAYS_TRUE, ALWAYS_TRUE, ALWAYS_TRUE).apply(x, y));
    assertFalse(BinaryPredicates.and(
        ALWAYS_TRUE, ALWAYS_TRUE, ALWAYS_FALSE, ALWAYS_TRUE).apply(x, y));
  }

  @SuppressWarnings("unchecked")
  public void testAnd_ofVarArgs_isView() {
    BinaryPredicate[] bps = { ALWAYS_TRUE, ALWAYS_TRUE, ALWAYS_TRUE };
    BinaryPredicate<Object, Object> and = BinaryPredicates.and(bps);
    assertTrue(and.apply("these", "arguments"));
    bps[1] = ALWAYS_FALSE;
    assertFalse(and.apply("don't", "matter"));
  }

  @SuppressWarnings("unchecked")
  public void testAnd_ofIterable_isView() {
    List<BinaryPredicate<Object, Object>> bps =
        Arrays.asList(ALWAYS_TRUE, ALWAYS_TRUE, ALWAYS_TRUE);
    BinaryPredicate<Object, Object> and = BinaryPredicates.and(bps);
    assertTrue(and.apply("these", "arguments"));
    bps.set(1, ALWAYS_FALSE);
    assertFalse(and.apply("don't", "matter"));
  }

  public void testAnd_equals() {
    BinaryPredicate<Object, Object> and =
        BinaryPredicates.and(ALWAYS_TRUE, ALWAYS_TRUE);
    BinaryPredicate<Object, Object> same =
        BinaryPredicates.and(ALWAYS_TRUE, ALWAYS_TRUE);
    BinaryPredicate<Object, Object> different =
        BinaryPredicates.and(ALWAYS_TRUE, ALWAYS_FALSE);
    BinaryPredicate<Object, Object> or =
        BinaryPredicates.or(ALWAYS_TRUE, ALWAYS_FALSE);
    @SuppressWarnings("unchecked")
    BinaryPredicate<Object, Object> more =
        BinaryPredicates.and(ALWAYS_TRUE, ALWAYS_TRUE, ALWAYS_TRUE);
    @SuppressWarnings("unchecked")
    BinaryPredicate<Object, Object> less =
        BinaryPredicates.and(ALWAYS_TRUE);
    BinaryPredicate<Object, Object> not = BinaryPredicates.not(ALWAYS_TRUE);

    EqualsTester tester = new EqualsTester(and);
    tester.addEqualObject(same);
    tester.addNotEqualObject(different, not, more, or, less);
    tester.testEquals();
  }

  public void testOr_ofTwoBinaryPredicates_apply() {
    String x = "these arguments don't matter";
    Integer y = 2;
    assertTrue(BinaryPredicates.or(ALWAYS_TRUE, ALWAYS_TRUE).apply(x, y));
    assertTrue(BinaryPredicates.or(ALWAYS_TRUE, ALWAYS_FALSE).apply(x, y));
    assertTrue(BinaryPredicates.or(ALWAYS_FALSE, ALWAYS_TRUE).apply(x, y));
    assertFalse(BinaryPredicates.or(ALWAYS_FALSE, ALWAYS_FALSE).apply(x, y));

    ArithmeticException expected = new ArithmeticException();

    BinaryPredicate<String, Integer> shouldThrow =
        BinaryPredicates.or(ALWAYS_FALSE, throwsBinaryPredicate(expected));
    try {
      shouldThrow.apply(x, y);
      fail("Should throw exception from second Relation");
    } catch (ArithmeticException actual) {
      assertSame(expected, actual);
    }

    BinaryPredicate<String, Integer> shouldBeTrue =
        BinaryPredicates.or(ALWAYS_TRUE, throwsBinaryPredicate(expected));
    assertTrue("Should short-circuit when first part of 'or' is true",
        shouldBeTrue.apply(x, y));
  }

  @SuppressWarnings("unchecked")
  public void testOr_ofVarArgs_apply() {
    String x = "these arguments don't matter";
    Integer y = 2;
    assertFalse(BinaryPredicates.or().apply(x, y));
    assertTrue(BinaryPredicates.or(ALWAYS_TRUE).apply(x, y));
    assertFalse(BinaryPredicates.or(ALWAYS_FALSE).apply(x, y));
    assertFalse(BinaryPredicates.or(
        ALWAYS_FALSE, ALWAYS_FALSE, ALWAYS_FALSE, ALWAYS_FALSE).apply(x, y));
    assertTrue(BinaryPredicates.or(
        ALWAYS_FALSE, ALWAYS_FALSE, ALWAYS_TRUE, ALWAYS_FALSE).apply(x, y));
  }

  @SuppressWarnings("unchecked")
  public void testOr_ofVarArgs_isView() {
    BinaryPredicate[] bps = { ALWAYS_FALSE, ALWAYS_FALSE, ALWAYS_FALSE };
    BinaryPredicate<Object, Object> or = BinaryPredicates.or(bps);
    assertFalse(or.apply("these", "arguments"));
    bps[1] = ALWAYS_TRUE;
    assertTrue(or.apply("don't", "matter"));
  }

  @SuppressWarnings("unchecked")
  public void testOr_ofIterable_isView() {
    String x = "these arguments don't matter";
    Integer y = 2;
    List<BinaryPredicate<Object, Object>> bps =
        Arrays.asList(ALWAYS_FALSE, ALWAYS_FALSE, ALWAYS_FALSE);
    BinaryPredicate<Object, Object> or = BinaryPredicates.or(bps);
    assertFalse(or.apply("these", "arguments"));
    bps.set(1, ALWAYS_TRUE);
    assertTrue(or.apply("don't", "matter"));
  }

  public void testOr_equals() {
    BinaryPredicate<Object, Object> or =
        BinaryPredicates.or(ALWAYS_TRUE, ALWAYS_TRUE);
    BinaryPredicate<Object, Object> same =
        BinaryPredicates.or(ALWAYS_TRUE, ALWAYS_TRUE);
    BinaryPredicate<Object, Object> different =
        BinaryPredicates.or(ALWAYS_TRUE, ALWAYS_FALSE);
    BinaryPredicate<Object, Object> and =
        BinaryPredicates.and(ALWAYS_TRUE, ALWAYS_TRUE);
    @SuppressWarnings("unchecked")
    BinaryPredicate<Object, Object> more =
        BinaryPredicates.or(ALWAYS_TRUE, ALWAYS_TRUE, ALWAYS_TRUE);
    @SuppressWarnings("unchecked")
    BinaryPredicate<Object, Object> less =
        BinaryPredicates.or(ALWAYS_TRUE);
    BinaryPredicate<Object, Object> not = BinaryPredicates.not(ALWAYS_TRUE);

    EqualsTester tester = new EqualsTester(or);
    tester.addEqualObject(same);
    tester.addNotEqualObject(different, not, more, and, less);
    tester.testEquals();
  }

  public void testNot_apply() {
    assertFalse(BinaryPredicates.not(ALWAYS_TRUE).apply("these", "arguments"));
    assertTrue(BinaryPredicates.not(ALWAYS_FALSE).apply("are", "ignored"));
  }

  public void testNot_equals() {
    EqualsTester tester = new EqualsTester(BinaryPredicates.not(ALWAYS_TRUE));
    tester.addEqualObject(BinaryPredicates.not(ALWAYS_TRUE));
    tester.addNotEqualObject(ALWAYS_TRUE);
    tester.testEquals();
  }

  @GwtIncompatible("NullPointerTester")
  public void testUsingNullPointerTester() throws Exception {
    NullPointerTester tester = new NullPointerTester();
    tester.testAllPublicStaticMethods(BinaryPredicates.class);
    tester.testAllPublicInstanceMethods(BinaryPredicates.alwaysTrue());
  }
}
