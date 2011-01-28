// Here is a java file

public class Foo {
  public Foo() {}
  @GwtIncompatible("Does't work in GWT") int getCount() { return 0; }
}
