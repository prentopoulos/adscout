# Before a repository goes public

Making a repository public is the owner's gate. Do these checks before it, or straight after if
the owner has already made it public. Record each one in the phase's review record. The method
was used on Compute Cost & Risk Monitor (October 2026).

## 1. Secret scan of the whole history

- **Export every blob.** `git rev-list --objects --all` lists every object. Keep the blobs
  (`git cat-file -t`) and write each one (`git cat-file blob <sha>`) to a scratch folder, one
  file per blob. Keep a map from blob to the first path it appears under.
- **Scan from inside that folder:** `detect-secrets scan --all-files .`. Given the folder's
  absolute path on Windows, it silently found nothing.
- **Prove the scanner works.** Plant a fake key file (for example `password = "..."` and a
  `-----BEGIN RSA PRIVATE KEY-----` line) and a file of known hashes. Both must be reported;
  remove them afterwards. A scan that finds nothing proves nothing until the planted key is
  found.
- **Search for key shapes:** `sk-ant-`, `ANTHROPIC_API_KEY=`, `ghp_`, `github_pat_`,
  `BEGIN .* PRIVATE KEY`, `AKIA[0-9A-Z]{16}`, `x-api-key`.
- **Confirm local secret files were never committed:**
  `git log --all --oneline -- .env .codex/config.toml` prints nothing.

## 2. Survey for data that must not be published

Use this for licensed, collected or personal data that stays local.
- **Load the private values read-only.** Format each one the way the project prints numbers:
  as stored, at fixed decimals, and with thousands separators. Add the figures the project
  derives from them.
- **Search every blob and every tracked file** for exact whole-number matches. Print counts,
  paths and context with the number masked, never the values themselves.
- **Explain every match.** Typical coincidences are demo figures, hash fragments, lockfile
  timestamps and sizes, SVG coordinates and contrast ratios.
- **Record the method's limit:** another format, or a round number that is also a demo
  figure, is not told apart.

## 3. Personal details

- **Search** the tracked files and the history for the home path (`C:\Users\<name>`,
  `/c/Users/<name>`), the email address and machine names.
- **Neutralise** them in the current files.
- **History keeps them** unless the owner decides to rewrite it. Rewriting is a one-way door,
  so it is the owner's call.

## 4. Publishing list

Write exactly:
- what becomes public: every tracked file and the full Git history;
- the data statement, saying what never appears;
- what stays private: data folders, `.env`, hosted services.

The owner approves the list, and PROJECT.md §6 records the decision with its date and scope.

## 5. Check from outside

- Clone the public branch into a short path, and run the README's quick start exactly as
  written.
- Confirm that any local server listens on 127.0.0.1 only (`netstat -ano | grep LISTENING`).
- Look at the screens at 1920 × 1080 for the required labels.
