# M3 Full-call Blind Results — 2026-09-13

## Evaluation interpretation

Persona and Scene generation are creative transformation steps. The submitted
reviews are interpreted without penalizing useful, non-conflicting expansion
such as roles, personality, teaching style, localized names, atmosphere, or
interaction detail. A defect requires lost constraints, a contradiction, false
certainty, or added information that would materially mislead downstream
generation. The frozen blind packet did not itself define minor/major severity
with this downstream-information-utility threshold, so severity conclusions
remain rubric-limited rather than an independently frozen semantic standard.

## Persona and Scene

- Frozen execution commit: `c1c40b7793c1aaf1c3723b3b4d8ad5a65d5d4b5d`.
- Final exporter commit: `f230e1a19d859da6826d5ec5df821a364fd0005b`.
- Eight of eight Persona lifecycles, eight of eight Scene lifecycles, and eight
  of eight joint lifecycles completed strict proposal validation, save,
  immediate read-back, and restart read-back.
- Eighteen provider wires were issued: all returned HTTP 200 with
  `finish_reason=stop`. Two Scene samples used the production bounded repair;
  no Persona sample required repair.
- Application generation HTTP was 200 for all sixteen domain operations. No
  application or upstream 502 occurred.
- Blind reviewer A recorded 87 pass, one minor, and no major grades. Blind
  reviewer B recorded 84 pass, four minor, and no major grades.
- Both reviewers treated the `ice_core_courier` Persona's change from physical
  ice-core delivery to a core data package as minor. It can mislead later
  generation about the delivered object and recipient, but it preserves Ren's
  core courier profession, transactional relationship, and explicit non-teacher
  and non-friend boundaries. The reviewers therefore retained a real defect but
  did not grade it major. The preregistered gate mechanically passed under the
  two submitted reviews; because the frozen packet omitted the severity
  threshold described above, this is not a stronger independent certification
  of semantic severity.

The first zero-wire preflight exposed an invalid transport call-kind label. A
later 16-wire run was incorrectly reported as candidate failure because the
research adapter applied strict Python datetime validation to ISO timestamps in
the application DTO; production v3 traces had passed. Both runs remain on disk
under explicit `preflight-zero-wire` and `live-harness-invalid` names and were
not substituted into the final denominator.

## Tavern

- Corrected adapter commit: `31a36787b4ee9f4799b6d8b77f7014d794798ce4`.
- The corrected campaign retained all 20 arms and ten families. Fifteen arms
  completed Room creation, committed opening and user messages, one direct
  persona turn, strict Tavern v3 validation, Message primary-output commit,
  idempotent replay, and restart Room/Run read-back.
- Fifteen provider wires were issued; every wire returned HTTP 200 with
  `finish_reason=stop`. The other five arms failed before issuing a wire.
- The five failures were zero-wire `SyntaxError` spawn/import failures. They
  occurred in a campaign executed from the shared main checkout and are
  consistent with checkout/import drift, but the bounded artifacts do not
  contain traceback, per-worker source digests, or a transition timeline that
  proves a specific Git merge caused them. They remain infrastructure failures
  in the original denominator and were not retried.
- The anonymous packet consequently contains five strict pairs and five
  symmetric unavailable pairs. Both reviewers found counterfactual sensitivity
  in all five evaluable pairs and no major content defect. The fixed 9/10
  operational promotion gate did not pass because only five pairs were
  evaluable.

An earlier 20-wire Tavern run completed and committed every domain operation,
but its generic AdapterResult was rejected after the fact because the adapter
used a custom scope string and a fixture-only canonicalizer that forbids finite
application floats. That run is retained as `live-harness-invalid` and is not
used to replace the corrected campaign's failed arms.

## 502 attribution

The historical Scene application 502s and these campaigns show the same needed
layering: an application 502 does not imply an upstream 502. In the historical
sample, upstream requests were HTTP 200 and failures came from length-truncated
or schema-invalid model output. In the full-call campaigns reported here, all
69 issued wires were upstream HTTP 200: 33 in the two corrected campaigns and
36 in the two retained harness-invalid diagnostic campaigns. The observed
failures were local Harness failures or zero-wire `SyntaxError` spawn/import
failures. No upstream 502 was observed.

## Execution isolation correction

Binding a preregistration to a Git commit is not sufficient if spawned workers
import from a shared checkout. A locked branch and separate worktree now exist:

- branch: `codex/m3-full-call-locked`
- worktree: `/private/tmp/vibe-learner-m3-full-call-locked`

Future live campaigns must execute entirely from that worktree without branch
switches, merges, or source edits during the run. Sandbox approval is relevant
only to `.git` writes and outbound execution permissions; it is not an
experimental reliability strategy.
