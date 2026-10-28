# Security and data handling

Plain-language version for anyone who asks "is this safe to run on our data?"
Short answer: yes, because it never leaves your computer. Here's the longer one.

## How it runs
It's an offline desktop tool. It opens PDFs and writes files in a folder you
pick. That's it. No internet connection, no open ports, no accounts to log into,
nothing uploaded anywhere, no usage tracking. If you unplugged the network cable
it would work exactly the same.

## Working with confidential data
Because everything happens on the machine itself, sensitive data never
gets sent anywhere, so there's nothing in transit for anyone to intercept. That
makes "keep it local" the easiest security model there is.

A few common-sense habits:
- run it on a trusted/managed computer
- write the outputs to a folder only the right people can open
- don't hand someone an `.exe` that you've parked sensitive data next to

The tool keeps no history and stores nothing of its own. The only files it makes
are the ones you asked for, in the folder you chose, plus a local `run.log` of
what it processed.

## "Is the code itself risky?"
Fair question, so here's the straight version for this app.

Most of the scary breach stuff (hacking, stolen logins, injection, data leaks)
needs a website, a server, user accounts, or an internet connection. This thing
has none of those. It's an offline file converter. That whole category of risk
just doesn't have a door to come through here.

What's actually left is small and ordinary: the open-source libraries it bundles,
and the theoretical case of opening a deliberately booby-trapped PDF. Both are
handled the boring way: stick to well-known library versions from the standard
Python package index, and only run PDFs you trust (your own sheets).

And the code is readable. It's small, plain Python you or anyone else can sit
down and go through. It comes with automated tests and an accuracy check, and it
touches no passwords and no network.

## If you need extra peace of mind (high-stakes or external use)
- get a person to skim the code (it's short)
- rebuild now and then so the libraries stay patched
- code-sign the `.exe` so Windows stops warning and people can see who published it
  (needs a paid certificate, only worth it if you're sharing widely)
- only feed it PDFs from sources you trust

## The one-liner for a meeting
"It's an offline desktop tool. The data stays on this computer, nothing gets
uploaded, and the code is open for anyone to read."
