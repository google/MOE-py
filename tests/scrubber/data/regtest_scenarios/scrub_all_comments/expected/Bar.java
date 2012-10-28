// Copyright 2011 Google Inc. All Rights Reserved.

public class Bar {

  public Bar() {

    # Python comment should be unscrubbed.

    int publicVar;
    String x =
        "Unterminated string should prevent extraction of below comments.
    /* MOE:insert
     int secondPublicVar; */
  }
}
