package com.othercompany.example;

import com.othercompany.example.subpackage.OtherClass;
import static com.othercompany.example.subpackage.OtherClass.baz;

/**
 * Uses various classes, such as {@link
 * com.othercompany.example.subpackage.AClass} and {@link OtherClass} to do
 * nothing in particular.
 */
public class Example {
    private static final String CLASS_NAME = "com.othercompany.example.subpackage.AClassFactory";

    private static com.othercompany.example.subpackage.YetAnotherClass staticField;
    private com.othercompany.example.subpackage.AClass field1;
    private OtherClass field2;

    public static void main (String[] args) {
	staticField = new com.othercompany.example.subpackage.YetAnotherClass();
	new Example().go(staticField);
    }

    /**
     * @see com.othercompany.example.subpackage.OtherClass#baz(com.othercompany.example.subpackage.InitClass)
     * @see #bar(OtherClass)
     */
    public void go(com.othercompany.example.subpackage.YetAnotherClass foo) {
	field2 = baz(com.othercompany.example.subpackage.InitClass.init());
	field1 = bar(field2);
	Example.class.getResource("/com/othercompany/example/subpackage/resource-file.txt");
    }

    /**
     * Instantiates a {@link com.othercompany.example.subpackage.AClass},
     * using either a class constant, reflection with a constant
     * field, or reflection with an embedded constant value.
     *
     * @throws com.othercompany.example.subpackage.OurException If there is a problem.
     */
    public com.othercompany.example.subpackage.AClass bar(OtherClass other)
	throws com.othercompany.example.subpackage.OurException
    {
	try {
	    if (other.check1()) {
		return com.othercompany.example.subpackage.AClass.class.newInstance();
	    } else if (other.check2()) {
		return Class.forName(CLASS_NAME).newInstance();
	    } else {
		return Class.forName("com.othercompany.example.subpackage.AClass").newInstance();
	    }
	} catch (Exception ex) {
	    throw new com.othercompany.example.subpackage.OurException(ex);
	} catch (com.othercompany.example.subpackage.OurRuntimeException ex) {
	    throw new com.othercompany.example.subpackage.OurException(ex);
	}
    }
}
