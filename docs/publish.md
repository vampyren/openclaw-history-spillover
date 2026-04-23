# Publishing notes

## Current state

The project is locally complete enough to publish, but GitHub publishing from this host is currently blocked by missing auth.

## What was checked

- `gh` CLI is not authenticated here
- no `~/.config/gh/hosts.yml`
- no `~/.git-credentials` with GitHub credentials
- browser attach to a signed-in Chrome profile failed because Chrome remote debugging was not available

## Fastest ways to unblock publishing

### Option 1: GitHub CLI login on the host

Run on the host:

```bash
gh auth login
```

Recommended choices:
- GitHub.com
- HTTPS
- Login with browser

Then verify:

```bash
gh auth status
```

### Option 2: Add a PAT for git/gh

A token with repo creation/push permissions would allow:

```bash
gh repo create ...
git push ...
```

### Option 3: Start signed-in Chrome with remote debugging

If the user browser is available with remote debugging, browser automation can create the repo in the signed-in GitHub session.

## Suggested repo name

- `openclaw-history-spillover`

## Suggested first release

- `v0.1.0`
