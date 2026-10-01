# Expected Packet Outcomes

This file records the expected outcomes for the exposure packets.
It is used as ground truth for deterministic rule tests, worker tests,
reviewer tests, and later evaluation.

The expected outcomes in this file are test expectations. They are not
regulatory determinations for real exposure events.

---

## P1 — exp-0411

### Packet Facts

- Worker ID: WKR-1047
- TEDE: 6.2 rem
- Lens Dose Equivalent: 3.0 rem
- Shallow-Dose Equivalent: 11 rem
- Intake: none
- Loss of control: No
- Planned Special Exposure: No
- Equipment failure: No
- Lost/stolen/missing material: No
- Source never left the device.

### Expected Rule Outcomes

#### R1 — Immediate Notification

Expected outcome: `not_required`

P1 does not meet the immediate-notification dose thresholds.

#### R2 — 24-Hour Notification

Expected outcome: `not_required`

Although the TEDE value is above the applicable dose threshold for this
rule, the packet establishes that there was no loss of control.

#### R3 — Written Report

Expected outcome: `required`

Expected reporting timeframe: `30 days`

#### Equipment Worker

Expected dispatch: `No`

No equipment failure is reported.

---

## P2 — exp-0412

### Packet Facts

- Worker ID: WKR-1047
- TEDE: 4.1 rem
- Lens Dose Equivalent: 9.0 rem
- Shallow-Dose Equivalent: 310 rad
- Shallow-dose site: Extremity
- Intake: none
- Loss of control: Yes
- Planned Special Exposure: No
- Equipment failure: Yes
- Source assembly failed to return to its fully shielded position.
- Lost/stolen/missing material: No

### Expected Rule Outcomes

#### R1 — Immediate Notification

Expected outcome: `required`

The TEDE and lens measurements are below the immediate-notification
thresholds, but the shallow extremity dose of 310 rad meets/exceeds the
250 rad shallow-dose threshold used by R1.

#### R2 — 24-Hour Notification

Expected outcome: `not_required`

The immediate-notification path is the expected notification behavior for
this packet based on the shallow-dose result.

#### R3 — Written Report

Expected outcome: `required`

#### Equipment Worker

Expected dispatch: `Yes`

The packet describes a source assembly that could not be returned to its
fully shielded position. Equipment-failure analysis is therefore required.

---

## P3 — exp-0413

Pending teammate packet and expected-outcome verification.

---

## P4 — exp-0414

Pending teammate packet and expected-outcome verification.
