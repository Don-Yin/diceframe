# Released runtime-1 compatibility fixture

These two stdlib files are the unchanged DiceFrame main launcher contract at
`d2246e0d0d32867e8e090c238b588441bad96a28` (application 2.6.1).
They intentionally remain frozen. Process tests use this old launcher to install,
start, commit and roll back a new version/data pair; they must not substitute the
new implementation for the already-deployed user launcher.

No runtime data or credentials are included. Application payloads and databases
are synthetic and created only in pytest temporary directories.
