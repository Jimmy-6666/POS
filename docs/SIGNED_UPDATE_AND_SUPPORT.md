# Signed updates and support bundles

## Update trust

Only an administrator can open **ดูแลระบบ**. An update is never uploaded
through the POS web server: copy its `*.update.json` manifest and the referenced
`*.ps1` script into `runtime\staging`. The manifest format is:

```json
{
  "format_version": 1,
  "release_id": "saengngam-pos-3.0.0",
  "version": "3.0.0",
  "script": "saengngam-pos-3.0.0.ps1",
  "script_sha256": "<SHA-256 of the script>"
}
```

The script must be Authenticode-signed by the approved publisher. Configure
the publisher certificate thumbprint in `runtime\config\production.json`:

```json
{"update_signer_thumbprint":"AA11BB22CC33..."}
```

`POS_UPDATE_SIGNER_THUMBPRINT` is an allowed environment override. No private
signing key belongs on the shop machine. The page checks the manifest, script
hash, signature status, and exact thumbprint. Applying needs the current admin
PIN read from the current active staff record, starts a detached Windows
runner, re-checks the same signature/thumbprint,
and records the request in the audit log. The signed script receives only
`-InstallRoot`, `-RuntimeRoot`, and `-Port`; it is responsible for its own
backup, atomic replacement, and restart. Check `runtime\logs\signed-update-*.log`
afterward.

## Support workflow

Choose **สร้างชุดข้อมูลช่วยเหลือ**, download the generated ZIP, and send it
only through the agreed support channel. It includes runtime validation, the
latest redacted application logs, and backup status. It excludes the database,
uploads, production configuration, secret key, and browser profiles. The POS
does not open a remote-control connection or transmit a bundle automatically.
Redaction covers plain and quoted/JSON credential, authorization, cookie,
session, token, LINE identity, phone, PIN, and password fields.
