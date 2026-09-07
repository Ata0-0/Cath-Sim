# Regulatory boundary

**Research prototype - Not for clinical use.**

## What this software is

A research prototype for studying the mechanics of catheter motion inside a
left-atrium-shaped geometry. Its purpose is to help investigate modelling
approaches, not to inform care.

## What this software is not

* It is **not** a medical device, and no regulatory clearance has been sought
  for it under any framework.
* It **must not** be used for diagnosis, treatment planning, procedure
  rehearsal for a specific patient, device selection, or any other clinical
  decision.
* It produces **no** lesion prediction, electric-field solution, PFA threshold
  or thermal damage estimate. Those belong to a separate future module and
  nothing here approximates them.
* It does not model any specific commercial device. The catheter models are
  named `GenericSteerableRF`, `GenericBalloon`, `GenericLoop`,
  `GenericLatticeSphere` and `GenericPentasplinePFA` precisely so that they are
  not read as a validated stand-in for a named product.

## Geometric similarity is not mechanical accuracy

A simulated catheter can look exactly like a photograph of a real one and still
be mechanically wrong in every number that matters. Shape resemblance says
nothing about bending stiffness, torsional response, contact force or tissue
apposition. This distinction is stated in the UI, in the exported files and in
`docs/assumptions.md`, and it is the reason uncalibrated parameters block
simulation instead of quietly defaulting.

## Validation status

| Claim | Status |
| --- | --- |
| The solver solves the equations it claims to solve | **Verified** by the automated suite in `docs/validation-plan.md` |
| Those equations describe a real catheter | **Not established.** No bench measurement has been made. |
| Contact forces are physically meaningful | **Not applicable.** Contact is not implemented (Milestone 2). When it is, the output is a numerical estimate from an uncalibrated model, and it must not be called a clinical contact-force reading. |

## Required labelling

The string

> Research prototype - Not for clinical use.

must appear:

* on every screen of the viewer (enforced by a test);
* in every exported JSON and CSV file (enforced by a test);
* at the top of every document in `docs/`;
* in the licence file.

## Data handling

* The default anatomy is procedurally generated. No patient data ships with
  this repository.
* DICOM is out of scope for this milestone. No patient name, identifier, study
  date or DICOM tag is read, displayed or stored.
* Uploaded meshes are processed locally in the browser by default.
* Logs never contain file contents or any identifier.
* Input size, triangle count and parse time are bounded, and malformed or
  decompression-bomb-style inputs are rejected rather than partially parsed
  (Milestone 2).

## If this ever moves toward clinical use

It would need, at minimum: a documented intended use and risk analysis; a
quality system; verification and validation against physical measurement
(section 3 of `docs/validation-plan.md`); clinical evaluation; and the relevant
regulatory submission. None of that has been started, and nothing in this
repository should be presented as a step toward it.
