# Warrant table maintenance comparison

Scope recorded before execution, 2026-10-01. This is a retrospective simplification
check, outside the three-item utility screening and its denominator. It is not a new
bug discovery, a blind comparison, or a productivity experiment.

Compare the existing pinned Warrant table with a handwritten Python transition
function on every Boolean input (16 states × 4 events) and the existing six adapter
scenarios. The author has read the model, table and adapter. Use the unchanged adapter
and effect spy; signing, arbitrary schedules and malformed inputs are outside scope.
Require two deliberately wrong replacements to fail, including one that the six
adapter scenarios miss. No production consumer or checker changes are permitted.

Decision rule: equal transitions plus equal observed effects establish a candidate
simplification for this fixed transition policy only. Count source bytes and physical
lines separately from generated table bytes. These counts are not maintenance effort.
Do not claim a replacement preserves digest refusal, projection parsing, or independently
checked model-to-table provenance. Record those lost properties before recommending
adoption. A mismatch blocks the simplification claim; neither outcome justifies a new
framework. Active labour, token cost and future maintenance cost are not measured.

Source: Warrant master `e4591b2338fc41a398ae9ec6a6d4e4c403df161b`, read from GitHub on
2026-10-01. Its two relevant source files are byte-identical to the existing adapter
pin `ac80aee`. The current source already has no installed Stargate dependency; it
vendors a fixed runtime and embeds a projection.
