# Reaching the files LibreOffice MCP produces

Documents produced by the MCP tools (and by `scripts/make-report.sh`) are
written under `/srv/docs/outbox/` on the Hermes host (LXC 104). There are
three practical ways for a human to get to them.

## 1. The dufs web share (easiest, LAN-only)

A `dufs` static file server is already running as the systemd unit
`hermes-docs.service`, serving `/srv/docs` on `http://192.168.1.104:8087`.

- Browse: `http://192.168.1.104:8087/outbox/`
- It supports plain HTTP GET/PUT/DELETE and directory listing, and requires
  HTTP Basic Auth.
- Credentials live in `/etc/hermes-office/dufs.env` (mode 600, root-only).
  **Do not print or copy the values out of that file into chat, logs, or
  scripts that echo them** — read the file directly on the host if you need
  to type the password into a browser prompt or a `curl -u` invocation.
- Example (fill in the real user/pass yourself, never paste them into a
  shared terminal history):
  ```
  curl -u "$DUFS_USER:$DUFS_PASS" http://192.168.1.104:8087/outbox/
  ```

## 2. scp / sftp directly to the LXC host

Since this is a normal SSH-accessible Linux host, any file under `/srv/docs`
can be pulled with standard OpenSSH tooling from your workstation:

```
scp root@192.168.1.104:/srv/docs/outbox/q3-production-report.pdf ./
sftp root@192.168.1.104
sftp> cd /srv/docs/outbox
sftp> get q3-production-report.pdf
```

This works even if `hermes-docs.service` is ever stopped, and it needs no
extra auth beyond whatever SSH credentials/keys you already use to reach the
LXC.

## 3. sshfs mount (browse it like a local folder)

For repeated access without re-running `scp` each time, mount the share
over SSH with `sshfs` on your workstation:

```
mkdir -p ~/mnt/hermes-docs
sshfs root@192.168.1.104:/srv/docs ~/mnt/hermes-docs
# ... browse ~/mnt/hermes-docs/outbox in your normal file manager/editor ...
umount ~/mnt/hermes-docs   # when done
```

This is the most convenient option if you're regularly opening the generated
`.docx`/`.pdf` files in a desktop editor, since it behaves like a local
directory rather than a one-off download.

(The LXC does not share a bind-mounted host path with the Proxmox host in
this setup, so a `file://` path on the hypervisor itself is not available —
sshfs is the practical stand-in for that.)

## 4. Send it to yourself on WhatsApp (works off-LAN)

This host runs the Hermes gateway (`hermes-gateway.service`) with WhatsApp
configured, and a gateway reply can carry a file by absolute path:

```
MEDIA:/srv/docs/outbox/q3-production-report.pdf
```

A reply containing that line is delivered as a real WhatsApp document
attachment, so it reaches you when you are not on the home network. The
`MEDIA:` tag is only intercepted on messaging platforms — in a terminal
session it prints as literal text.

## 5. What does *not* work: the WebObsidian vault, for binaries

The vault at `http://192.168.1.107:8787` is a note store, and its agent API
(`/api/v1/notes/{path}`) accepts **text** payloads only — the agent cannot
POST a PDF or DOCX. Binaries would have to be copied into the vault
directory on the vault host, and WebObsidian has no PDF viewer (a PDF lands
in an empty editor tab). So: markdown reports can go into the vault as
notes, but for `.pdf`/`.docx` outputs use options 1–4 above.
