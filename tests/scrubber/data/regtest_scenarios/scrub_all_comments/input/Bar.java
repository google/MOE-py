// Copyright 2011 Google Inc. All Rights Reserved.

/**
 * Class javadoc here.
 */
public class Bar {

  public Bar() {
    // Regular comment.

    # Python comment should be unscrubbed.

    int publicVar;
    String x =
        "Unterminated string should prevent extraction of below comments.
    /* MOE:insert
     int secondPublicVar; */
  }
}
