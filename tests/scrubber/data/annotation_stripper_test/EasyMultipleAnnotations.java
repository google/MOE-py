// Here is a java file

@Include
public class Foo {
  public Foo() {}
  int getCount() { return 0; }
  @Exclude int getCount2() { return 1; }

  private static class IncludedInner {
    @UnrelatedAnnotation int x;
    @Exclude int y;
  }

  @StaticAnnotations.Exclude(parametrized = "true")
  private static class ExcludedInner {
    int w;
    @Include int shouldntBeIncluded;
  }
}

class Confidential {
  @Include int shouldntBeIncluded;
}
