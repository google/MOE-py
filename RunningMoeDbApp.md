# Running a Local copy of the Moe Appengine DBApp #

Download a 1.4.**version of the Appengine SDK**

Mac OS X: http://googleappengine.googlecode.com/files/GoogleAppEngineLauncher-1.4.0.dmg

Windows: http://googleappengine.googlecode.com/files/GoogleAppEngine-1.4.0.msi

Linux: http://googleappengine.googlecode.com/files/google_appengine_1.4.0.zip

After downloading Appengine add the existing make-open-easy/moe/dbapp directory to the apps list and
run the application.

Note: Appengine's 1.4 SDK looks for a Version file in the first place it can import google from. Because of how google's apputils-python installs, you may need to cp the Version file to there.