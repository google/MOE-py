// Here is a java file
public class Foo {
  public Foo() {}
  int getCount() { return 0; }

  private static class IncludedInner {
    @UnrelatedAnnotation int x;
  }
}
