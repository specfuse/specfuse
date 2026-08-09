<!--
Copyright 2026 Specfuse Contributors
Licensed under the Apache License, Version 2.0. See LICENSE.
-->

# Rule: a validator that closes over a borrowed vocabulary must verify against its owner

Some validators enumerate what is allowed: a JSON Schema with
`additionalProperties: false`, a closed enum, an allow-list of flags, a switch
whose `default` branch raises. Enumeration is usually right — it is what turns a
typo into an error instead of a silent no-op.

The rule is about the case where **the enumerated set is defined somewhere
else.** A linter that closes over a vendor-extension vocabulary owned by a code
generator, a config validator that closes over the flags a service accepts, a
router that closes over another team's event types: in each, one repo decides
what is legal and a different repo decides what is accepted. Those two sets are
kept in agreement by nothing at all unless something checks.

**When you close over a vocabulary you do not own, you owe an automated check
that your copy still agrees with the owner's.**

## Why memory is not enough

The obvious mitigation — "we update the allow-list when the owning repo adds
something" — is what fails, and it fails quietly for three compounding reasons.

**The owner has no reason to tell you.** Their feature is done when their tests
pass. Your allow-list is not in their repo, their plan, or their review.

**A closed schema converts a stale copy into a hard block, not a soft one.** An
open validator that lags behind merely misses a warning. A closed one *rejects
the new thing*: the first consumer to use the owner's new capability fails
validation, so the capability cannot be adopted at all until someone edits the
validator.

**The error names the wrong artifact.** The message points at the consumer's
input — the spec, the config, the payload — because that is what was being
validated. Nothing points at the allow-list. So the first move is usually to
delete the offending value, which abandons the feature being adopted and leaves
the drift in place for the next person.

The result is a failure that is invisible until someone tries, then reads as
their mistake. In the incident that produced this rule, one vocabulary drifted
three times: a key shipped across 78 consumer definitions and sat broken for
months before anyone noticed, a second blocked a rollout until the validator was
patched by hand, and a third was on the same path. Every instance was caught by
a human happening to notice, and the standing practice — "patch the validator
alongside the feature" — is what had already failed twice by then.

## What the check must do

1. **Read the owner's artifact, not a description of it.** Extract the
   vocabulary from the thing that defines behaviour — the compiled binary, the
   published schema, the source of record. A document describing the vocabulary
   is one more copy that can drift.
2. **Fail in the blocking direction.** Owner-has / validator-rejects must fail
   the build. The reverse — the validator accepts something the owner never
   mentions — is usually noise (values reached indirectly leave no trace to
   extract) and should be reported, not enforced.
3. **Run where the drift is born.** The moment the owner's artifact is upgraded
   — a version pin, a dependency bump, a vendored copy refresh — is when the
   vocabulary changes and the fix is cheapest. Checking only at consumer-build
   time means every consumer discovers it separately.
4. **Discover the closed sets structurally.** Enumerate what is closed by shape,
   not by a hand-written list of the ones you remember. A list of guards is
   itself a closed vocabulary that drifts, and the guard added next month is the
   one nobody will think to add to it.
5. **Never skip silently.** If the owner's artifact is unavailable, say what was
   *not* verified. A check that quietly passes when it could not run is worse
   than no check: it converts an unknown into a green.
6. **Account for every value, including the exceptions.** A value that
   legitimately belongs elsewhere goes in an explicit exceptions file with a
   reason. "Known and explained" and "unnoticed" must not look the same.

## One copy, one runner

A second copy of a hand-maintained validator is the same problem wearing a
different hat, and the copy nothing executes is the one that rots. In the same
incident, a duplicate ruleset had drifted so far that the platform running it
rejected every definition in the tree, while CI ran the other copy and stayed
green for months. Keep one copy and one runner; if a second must exist, it is
generated from the first, not maintained beside it.

## Applying it

The obligation lands on whoever closes the set — the consumer, not the owner.
Asking the owner to announce vocabulary changes is worth doing and does not
discharge it: an announcement you must remember to act on is memory again, and
the check is what makes adoption verifiable rather than remembered.
