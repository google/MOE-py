package com.google.example;

import com.google.example.subpackage.OtherClass;
import static com.google.example.subpackage.OtherClass.baz;

/**
 * Uses various classes, such as {@link
 * com.google.example.subpackage.AClass} and {@link OtherClass} to do
 * nothing in particular.
 */
public class Example {
    private static final String CLASS_NAME = "com.google.example.subpackage.AClassFactory";

    private static com.google.example.subpackage.YetAnotherClass staticField;
    private com.google.example.subpackage.AClass field1;
    private OtherClass field2;

    public static void main (String[] args) {
	staticField = new com.google.example.subpackage.YetAnotherClass();
	new Example().go(staticField);
    }

    /**
     * @see com.google.example.subpackage.OtherClass#baz(com.google.example.subpackage.InitClass)
     * @see #bar(OtherClass)
     */
    public void go(com.google.example.subpackage.YetAnotherClass foo) {
	field2 = baz(com.google.example.subpackage.InitClass.init());
	field1 = bar(field2);
	Example.class.getResource("/com/google/example/subpackage/resource-file.txt");
    }

    /**
     * Instantiates a {@link com.google.example.subpackage.AClass},
     * using either a class constant, reflection with a constant
     * field, or reflection with an embedded constant value.
     *
     * @throws com.google.example.subpackage.OurException If there is a problem.
     */
    public com.google.example.subpackage.AClass bar(OtherClass other)
	throws com.google.example.subpackage.OurException
    {
	try {
	    if (other.check1()) {
		return com.google.example.subpackage.AClass.class.newInstance();
	    } else if (other.check2()) {
		return Class.forName(CLASS_NAME).newInstance();
	    } else {
		return Class.forName("com.google.example.subpackage.AClass").newInstance();
	    }
	} catch (Exception ex) {
	    throw new com.google.example.subpackage.OurException(ex);
	} catch (com.google.example.subpackage.OurRuntimeException ex) {
	    throw new com.google.example.subpackage.OurException(ex);
	}
    }
}
