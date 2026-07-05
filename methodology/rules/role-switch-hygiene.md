<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Rule: role-switch hygiene

The shared rule set must be re-read **unconditionally at the start of every
task**, including when a session switches roles within a single session.

## Why

The shared rules are the load-bearing substrate under every role's configuration.
A session that skips re-reading them on a role-switch carries forward stale
context from its previous role: rule amendments since the last read are invisible,
and role-specific overrides that applied under the previous role — and should not
apply under the new one — can bleed through without notice.

The failure mode is silent. A rule that applies non-obviously to the new role can
be missed, producing a correctness bug downstream. Re-reading is the cheap,
mechanical guard against it.

## The rule

Before performing any action under a role:

1. Re-read the full shared rule set, regardless of whether the current session has
   read it earlier under a different role.
2. Re-read the configuration and skills of the new role.
3. Then, and only then, proceed with the task's intent (step 1 of
   [`verification-discipline.md`](verification-discipline.md)).

The re-read is the action. "I read them a few minutes ago" is not the re-read;
"I remember what they say" is not the re-read. The rule is strict because the
failure mode it prevents is silent.

## When this applies

- The start of every task, every time.
- Every role-switch within a single session — for example, a session that
  co-pilots planning in one role and then hands off to an implementation role: the
  implementation role re-reads before acting, even though the session read the
  shared rules minutes earlier.
- Every resumption of a previously-paused session where more than one role runs.

A fresh-session start is already covered by the "read before acting" directive in
each role's configuration; this rule is the additional commitment that the
directive is not weakened by a prior in-session read under a different role.

## Scope and exceptions

This rule is shared because every role is subject to it symmetrically. It lives in
the shared set, rather than duplicated into each role's own rules, precisely to
prevent per-role drift of the re-read discipline.

There are no exceptions. A future revision may narrow the scope (e.g., skip the
re-read if the session has not advanced past a role's own substrate), but any such
narrowing must come with the justification and evidence the amendment protocol
requires for shared-rule changes.
