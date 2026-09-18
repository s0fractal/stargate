# Stargate contract

Status: **32K — DRAFT, implemented for the flows described below**.
Build 16 is a local development implementation, not an adopted or published
standard. It is not a Warrant verifier.

## One temperature

A single Kelvin integer identifies the semantic edition: canonical data bytes
and addressing, evaluation and budget rules, canonical exits, record identity,
signature inputs, verification, fingerprints and settlement.
Internal modules have no independent protocol versions.

Start at 32K. After the first contract is defined and released, a change to any
of those semantics consumes a step: 32K → 31K → … → 0K. Changes to an unreleased
draft do not consume steps. Temperature is neither progress percentage nor a
reward for tests, and there is no deadline to reach zero.

The same temperature may receive implementation corrections to an unambiguous
contract, performance improvements and CLI changes. If a correction changes
observed results, describe the defect and affected builds/results. If the
contract itself was ambiguous or changes, lower the temperature. A test suite
alone does not establish semantic equivalence.

At 0K the semantic contract is frozen. Implementations may still be repaired to
conform to it. A semantic change requires a distinct contract identity; do not
reset the temperature under the same identity or disguise it as a bug fix.

## Identity and unsupported editions

The canonical signed body identifies Stargate through the `stargate` field
whose integer value is its temperature. The signature domain also names Stargate. Hashes of predecessor records must not be silently reused for new meanings.

A current verifier supports one temperature. It must explicitly reject an
unsupported edition before interpreting or executing its contents. It must not
skip unknown reasons, reinterpret historical data, dynamically fetch old code,
or silently route to a legacy evaluator. Older releases are separate historical
verification tools, with declared environments and no promise of perpetual
platform support. New records derived from old records receive new identities;
original signed bytes are preserved.

## Build identity

The package version is an increasing build number, initially 1. Its source of
truth is `stargate.__version__`; packaging reads it directly. The CLI reports
both build and temperature. Never replace a published artifact in place.
A result's provenance must identify the implementation build as well as the
semantic edition. Author build is signed in the body; verifier build is reported separately.
A build label is provenance, not proof of which software an author actually ran.

Kelvin is not used as the Python package version, so newer packages do not sort
behind older ones. Public package-name availability has not been checked; local
installation under the working name is not a claim on an index namespace.

## Implementation boundary

Python is the only initial implementation. Filesystem layout, local operational
limits, help text and Python internals are not automatically frozen protocol
surfaces. Local resource failure must remain distinguishable from a canonical
computation result. Operational improvements must preserve signed bytes and
semantic results for successfully executed supported inputs.

The implementation scope and wire format below define the initial flow.
There is no collective settlement, historical-runtime routing, persisted resume, wave
layer or federation in this draft.

## Origin of the version approach

The policy is Stargate's adaptation, not a claim to reproduce Urbit's complete
versioning or update machinery. Urbit distinguishes Kelvin-versioned Arvo from
its separately versioned runtime:
https://github.com/urbit/docs.urbit.org/blob/master/content/user-manual/os/updates.md

## 32K computation

A node is an opcode byte, a flags byte, then the indicated 32-byte fields in
atom/left/right order. Exactly these forms are valid:

| Opcode | Flags | Payload |
|---|---|---|
| 0x00 literal | 0x01 | atom |
| 0x01 reference | 0x01 | target hash |
| 0x02 application | 0x06 | left hash, right hash |
| 0xff dissonance | 0x01 | reason hash |

Node addresses are SHA-256 of those bytes. I/K/S are intrinsic literal nodes
whose atoms are SHA-256 of ASCII `I`, `K`, `S`. Their bytes need not be stored.
Invalid node encoding materializes DISSONANCE(SHA-256(`Invalid Object`)).
Foreign bytes under an address cause a local fault, not an invalid-object term.

Evaluation takes a term hash, uint32 ATP, and a content environment. It uses
lazy left-spine resolution and leftmost-outermost reduction. A hash thunk has
size 1, a materialized reference size 2, a literal/dissonance size 1 and an
application size 1 + sizes of children. Materialization costs the resulting
size. I x → x, K x y → x, and reference dereference each cost 1. S x y z →
(x z)(y z) costs 1 + size(z). An unaffordable action is not charged or applied.
A zero-budget non-genesis thunk exhausts before fetching; missing demanded
content with an affordable fetch gives unresolved_reference. Dead branches need
not be fetched. Intrinsic genesis hashes are normal forms without work.

The receipt contains result_hash, atp_spent, exit. Exit is exactly normal_form,
atp_exhausted, or unresolved_reference. The latter two return dissonance terms
with atoms SHA-256(`ATP Exhausted`) and SHA-256(`Unresolved Reference`). The same
dissonance term can also be a normal form; result_hash never substitutes for exit.

Local admission/resource failures produce no canonical receipt or decision.
CLI and record verification limit ATP to 10,000,000; kernel Python callers may
supply local limits. These limits are operational, not another semantic edition.
The implementation is synchronous; concurrent in-process evaluator use is not
promised (the inherited evaluator adjusts Python's recursion limit).

## 32K signed check

An envelope has exactly `body` and `signature`. Its body has exactly:

```json
{"stargate":32,"build":"11","key":"<public key hex>","check":{"term":"<hash>","atp":4,"expect":"<hash>","exit":"normal_form","environment":["<term hash>"]},"decision":"accept","policy":null,"subject":null}
```

This example is explanatory, not canonical field ordering. The encoding is
UTF-8 integer-domain JCS: UTF-16 code-unit object-key ordering, no whitespace,
no float/NaN/Infinity, no lone surrogates, no duplicate keys; integers are within
±(2^53−1). Hashes and keys are 64 lowercase hexadecimal characters, signatures
128. ATP must be an integer uint32 (booleans are rejected). Build is a nonempty
ASCII decimal string. Unknown fields, legacy shapes and other temperatures are
invalid; no older implementation is selected automatically.

RecordID = SHA-256(canonical body). Ed25519 signs the bytes
`b"stargate-record:" + bytes.fromhex(RecordID)`. The key is inside the signed
body. The envelope is canonical too. Its storage object hash differs from the
RecordID because the envelope additionally contains the signature.

Creation re-executes the check. Verdict pass requires BOTH expected result_hash
and expected exit to match. It signs decision accept for pass and reject for
fail. Verification requires an explicitly supplied trusted public key, a valid
signature and re-execution agreeing with the signed decision. Small-order and
noncanonical public keys are rejected. A self-supplied key in the record grants
no trust. Neither an expected exhaustion nor an accepted claim proves a normal
form, a real-world assertion or an external policy: it proves this stated
computation claim in the verifier's available content environment.

The outcome fingerprint is exactly:

```
("stargate", 32, tuple(environment), term, expect, expected_exit, verdict, result_hash, actual_exit)
```

ATP budget and atp_spent do not affect this identity. Each record still signs its
own budget. A fingerprint is not an admission vote or settlement. Stargate does
not yet implement Warrant's disagreement graph, thresholds or re-litigation.

The check has exactly term, atp, expect, exit and environment. Environment is a
sorted, duplicate-free list of lowercase SHA-256 addresses. It is signed as
part of the body and included in the outcome fingerprint. It defines the entire
non-intrinsic domain visible to evaluation; objects outside it are absent EVEN
IF the local store holds them. Genesis I/K/S remain intrinsic regardless of this
list. A demanded listed object unavailable locally is a StoreError naming its
hash: UNVERIFIED, with no verdict or decision. Corrupt bytes are likewise local
faults. Unused listed objects need not be fetched or locally present.

Thus an explicit absence (outside the signed domain) can canonically produce
unresolved_reference; a local missing copy (inside the domain) cannot. Two
verifiers able to supply the demanded listed bytes evaluate the same domain,
regardless of extra local objects. This does not assert availability elsewhere
or prove that the author chose a domain appropriate to an external question.
An explicit empty domain is legal, but is not a claim that a term is globally
unresolvable. Different domains may have the same outcome; this fingerprint is
not a settlement novelty/admissibility rule.

API callers must supply the domain explicitly. CLI `record` by default first
captures addresses actually demanded by this evaluation; any missing fetch
aborts before signing. Then it re-executes against that bound domain and signs.
This performs two evaluations; it is not an optimization. To intentionally
claim absence, use `--environment FILE` with a JSON address list (possibly []).
Each execution caches fetched bytes, checking their addresses. No signed
local rejection is manufactured from an unobserved missing object.

Raw CLI `eval` remains a diagnostic over the supplied local store, with no
signature or decision; its unresolved_reference is not a verified record.
Corrupt addressed bytes, I/O and resource failures during verification
are local unverified outcomes, never fail/reject. Input decoding and reading
object files are not charged ATP; this CLI is not a hostile-input network service.

## CLI results

`init`, `keygen`, `put`, `genesis`, `apply`, `eval`, `record`, `verify` output JSON.
`record` returns both RecordID and envelope object hash; `verify` takes the latter
and an explicit `--trust` key. Key generation creates a new mode-0600 seed file
and refuses to overwrite any existing path. Exit 0 means the operation completed
(including a successfully verified reject); inspect decision/verdict. Exit 1 / operation_error is an operational command failure, such as refusing
to overwrite a key or being unable to read a key/input file during authoring.
Exit 2 / invalid is malformed input/signature/unsupported edition. Exit 3 /
unverified is inability to evaluate/verify the declared computation locally,
including missing demanded domain members; no decision is returned. `eval` and
`verify` I/O failures also use 3. Argparse syntax errors use exit 2 with its
standard text diagnostic; JSON statuses apply after argument parsing.

The record API raises InvalidRecord for malformed record fields, including
term, expect, environment addresses and signer keys. StoreError,
AdmissionRefused and ResourceFault remain separate local-failure exceptions.

## In-process continuation

`start(term_hash, atp, env, limits=None)` returns an Evaluation.
`resume(state, additional_atp)` advances that same object. The state is internal
Python memory, not a wire format, record or new canonical exit. Default local
limits are VERIFIER_LIMITS. Environment must be a mapping of 32-byte keys to
immutable bytes, copied at start; resume accepts no replacement environment or
limits. Content/address mismatch remains checked when a node is demanded.

Grant is cumulative uint32 credit. Both each increment and the cumulative grant
must satisfy admission limits, before advancing state. Unspent credit carries
over so several small increments can fund one expensive action. Spent counts
only committed priced actions and never resets. Fetch counters and resource
limits likewise do not reset. An invalid/refused increment leaves state alone;
a resource fault while running marks the state faulted and it cannot resume.

Status suspended carries receipt=None. Normal completion or canonical unresolved
reference carries the corresponding Receipt with cumulative spent. Completed
or faulted objects cannot be resumed. A zero increment on an already suspended
object is a no-op. Initial genesis at zero credit can finish immediately.

With positive credit the machine may prepare one next action before knowing
its full cost, like the original materialization path. If unaffordable, it
retains the pending action without committing or charging it; live and pending
terms are guarded by local resource limits. Resuming does not repeat its fetch
or contraction preparation. At zero credit it performs no new demanded fetch,
but probing for an already-normal term re-traverses the search spine at each
zero-credit boundary reached during execution. This traversal can repeat and
cost CPU without spending ATP. Explicit resume(state, 0) remains a no-op;
these probes occur within start or a positive-credit resume. No-repeat claims
cover fetch and prepared contraction work, not all step5 calls or elapsed time.
Snapshot copying, Python traversal overhead and transient pending work are
not an exact CPU/memory accounting model for ATP. Snapshot allocation is outside
ATP; the interface is not a hostile-input service.

For a fixed snapshot and unchanged limits, split and one-shot executions that
finish without local faults agree on exit, result hash and cumulative spent
when total grant is equal. At insufficient total grant the resumable API is
suspended, while fixed-budget eval_receipt returns canonical atp_exhausted.
Suspension must not be coerced into that receipt or a pass/fail verdict.
Suspension is an additional resource-sampling point: small credit increments
can cause ResourceFault where the SAME term, environment, total grant and
limits complete in one shot. Such a state is terminal (status=faulted,
receipt=None); resume refuses it, and its accumulated work cannot be recovered
through this API. Splitting is therefore NOT a refinement of one-shot local
failure behavior. A caller requiring grant-schedule-independent local outcomes
must not assume this interface provides them. No changes to the signed check format follow from this
process-local API.

## Policy provenance and authoring (build 7 candidate)

Every body has the REQUIRED field policy: either null for a raw computation
claim or exactly {rule: hash, facts: hash}. Both references are lowercase SHA-256
and covered by RecordID/signature. Rule is exact UTF-8 source bytes (including
whitespace/comments); facts is canonical integer-domain JSON containing only
named boolean values. All declared names must occur exactly once, with no extra,
unknown or unused facts. Reordering/spacing a facts input file does not change
its canonical hash; changing raw rule text does change its hash.

Rule grammar: zero or more `fact NAME: bool` declarations followed by one
`check EXPR`. Names are ASCII identifier components optionally separated by dots.
Keywords cannot name facts. Expressions support true, false, declared names,
!, &&, || and parentheses, in that precedence order; binary operators associate
left. # starts a line comment. No inline values are allowed with external facts.
The low-level compile_source API also accepts closed inline-fact source when no
facts parameter is supplied; provenance records always use the external-facts
path. This is not a separate executable runtime or signed format.

Compilation lowers Church boolean operations to the kernel; the direct boolean
interpreter checks the closed result. Compiler output ALWAYS expects K and
normal_form, budgets measured spend, and declares the sorted generated object
set. Exact serialized checks are replayed before emission. A false predicate
therefore produces reject, not accept of a FALSE expectation.

Creation authenticates source/facts against their addresses and checks their
compilation before signing. Verification first validates envelope shape,
signature and caller-supplied trust, then fetches source/facts, checks their
hashes and encoding, recompiles, and requires equality of ALL check fields.
Comparison includes term, ATP, expect, exit and environment. It then executes
the signed check against the supplied addressed objects and compares decision.
Generated compiler objects must NOT silently fill absent bundle/store objects.

The signed check ATP is the compilation measurement ceiling during verification,
also subject to verifier admission/resource limits. A malformed rule/facts or
compiled-check mismatch is invalid. Missing material is StoreError/unverified,
naming the hash; resource inability or detected internal compiler disagreement
is noncanonical/unverified. Failure does not yield a decision.

Report policy is null for raw claims, otherwise {rule, facts, source, inputs}
with authenticated decoded content. Bundle verification follows exactly the same
path and needs no local store. Source/facts are separate from the computational
environment: they are mandatory provenance dependencies even when no term fetch
occurs. The computational fingerprint stays unchanged and does not identify the
rule text; RecordID does. No settlement consumption of fingerprints is added.

The author and recipient share a compiler implementation, so reproducibility is
not a formal compiler-correctness proof. It neither verifies the external truth
of facts nor establishes a policy's legitimacy. Current 32K remains unreleased;
old bodies without policy are rejected, not migrated or silently interpreted.

## Portable check container

A bundle is canonical JSON with exactly stargate_bundle (integer 32), envelope
(the existing signed record envelope), and objects (hash → lowercase hex bytes).
It adds no new record identity or signature domain. Other temperatures, unknown
fields, noncanonical JSON, malformed object keys/hex and object/hash mismatches
are invalid. Every included object must belong to the signed computational environment or
be named by a signed policy.rule/policy.facts reference.

Export verifies the record with caller-supplied trust and captures the ordered
execution's fetched objects into a hash map. Rule/facts bytes and demanded computational bytes are included;
the signed environment itself is not shortened. Unused environment members may
be omitted, including ones absent on the exporter. Canonical JSON makes this
export deterministic for a fixed envelope and successful execution.

Verification uses exclusively the included objects, with the existing signed
BoundEnvironment semantics: omitted demanded members mean unverified, outside-
domain members are invisible, and intrinsic genesis nodes need no object. It
checks signature/trust and re-executes through the existing verify_record path.
No local-store/network fallback, extraction or persisted import is performed.
A bundle cannot grant trust in its author. Signature/hash malformation is
invalid; missing demanded bytes or local resource inability is unverified.

The CLI reader reads at most 16 MiB + 1 byte and refuses larger files as a local
StoreError. The API applies the same cap to supplied bytes before parsing.
This is an operational limit, not the contract's data-domain limit or an exact
RSS bound. Export's cap is checked during capture and on final encoding; reading
objects from the exporter's local store retains that store's existing allocation
behavior. Export publishes through an exclusive hard link to a completed temp
file and never overwrites; unsupported filesystem operations are operation_error.
The container transports authenticated policy material where referenced; it
does not introduce application truth, quorum or global availability claims.


## Recipient requirement

`require_bundle(raw, trusted_keys, *, rule, facts, subject=None)` accepts an independently
provided UTF-8 rule string and exact-domain boolean fact dictionary. It validates
the request with the current rule grammar and hashes exact rule bytes and
canonical facts. It then performs full bundle verification. Verification errors
retain their original classes; no requirement verdict is produced on failure.

For a verified record, evaluate these predicates in order: policy is non-null,
policy.rule equals expected rule hash, policy.facts equals expected facts hash,
report.subject equals expected subject (including null), and decision is accept. The first failed predicate gives, respectively,
policy_missing, rule_mismatch, facts_mismatch, subject_mismatch or decision_reject. All predicates
must hold for status satisfied with reason null; otherwise status is unsatisfied.
The report includes expected {rule, facts, subject} hashes/null and the original verification
report under verification. It is local output, not a signed record.

`sg require BUNDLE --trust KEY --rule FILE --facts FILE` exposes this operation.
It returns 0 for satisfied, 4 for unsatisfied, 2 for malformed inputs or invalid
proofs, and 3 for missing material, I/O or local admission/resource inability.
Duplicate fact keys are rejected before canonicalization. Request validation
precedes proof verification. Raw policy:null records cannot satisfy a request.
The command has no store fallback and executes no subsequent external action.
This imposes no freshness or anti-replay property and makes no claim about
real-world truth of the expected inputs. The bundle container is unchanged; the current body includes the subject field.


## Artifact subject

Every signed body MUST contain subject, exactly null or a lowercase 64-hex SHA-256
digest. Bodies without this field are invalid. create_record and author_policy
accept subject=None or a validated digest. The field is signed and contributes
to Record ID, but not the computational fingerprint, term or reduction budget.
verify_record reports the signed subject without resolving its bytes.

The subject is not a computational environment member or a policy source
reference. Naming it does not admit its bytes into a bundle's object domain;
only an independent computational/source reference can do so. Export does not
fetch an artifact solely because it is named as subject.

require_bundle compares the signed subject to the recipient's subject by exact
equality after policy/fact identity and before decision. Null is an explicit
unbound requirement, never a wildcard. The API consumes a digest selected by
the caller; CLI --subject hashes the file's binary bytes. Both policy and record
CLI commands can bind a subject. Only regular files are hashed; chunked reading
avoids loading the artifact into memory. Detected size/mtime/ctime change during
reading is an I/O refusal (require: unverified/3, authoring: operation_error/1).
Invalid subject shape or a nonregular file is invalid/2. Missing or unreadable
recipient artifact is unverified/3; a complete verified proof with a different
subject is unsatisfied/4. Existing verification failures retain their classes.

The binding authenticates that the signer associated this decision with that
digest. The binding alone does not derive boolean facts from the artifact, prove availability,
or establish content safety. Hashing is not an atomic snapshot or a lock against
later mutation. Consumers acting on a file must preserve the checked bytes.
No artifact execution, publication, freshness or replay prevention is provided.
This is one revised 32K draft body, without a legacy acceptance path.


## Artifact admission

admit_bundle(raw, trusted_keys, *, rule, facts, subject, output) accepts local
source and destination paths. It stages the source in a mode-0600 temporary file
in the output directory and hashes exactly the chunks written, using the same
regular-file and detected-change rules as subject hashing. It closes the staged
writer before invoking require_bundle with that hash as the required subject.

On unsatisfied it returns the requirement report plus artifact:null and MUST NOT
publish the output. On satisfied it exclusively hard-links the staged file to
the output path. It MUST NOT copy or link the original source for publication,
and MUST NOT overwrite an existing destination, including a symlink. Thus source
replacement after staging cannot change the admitted bytes. Atomic destination
creation, rather than a prior existence check, handles a competing creator.

Success returns {status:admitted, artifact:{path,sha256}, requirement:REPORT}.
The report is unsigned local output. CLI admit has required --subject and --output
in addition to --trust, --rule, --facts and bundle path. It uses exit 0 for admitted,
4 for unsatisfied, 2 for invalid input/proof, 3 for unavailable input or verifier
inability, and 1/operation_error for destination I/O failure. API input read I/O
becomes StoreError; output I/O remains OSError. Verification exceptions propagate.
The temporary path is removed in a finally block on ordinary control flow.

The caller controls the destination directory. Other writers with access to the
staged or final file are outside this guarantee. Staging is not an atomic source
snapshot; the signed digest binds the bytes actually read. There is no crash
recovery, fsync/durability, artifact execution, upload, replay prevention or
permanent immutability. A crash can leave staging files; failure after link (for
example cleanup failure) can leave a published output despite an error result.
Source file size and disk consumption are not capped. No signed format, evaluator
semantics or temperature change is introduced.


## Locally derived artifact facts

policy, require and admit accept exactly one of --facts FILE or --derive FILE.
Derive requires a subject file. The profile is a JSON object of 1–32 WPL fact
names, each mapping to exactly one predicate. The complete computed fact domain
must match the rule's declared and used facts; no mixing with manual inputs.
Duplicate keys are invalid. Profiles are snapshotted before measurement.

Predicates: {size_at_least:N} means total byte count >= N; {size_at_most:N} means
byte count <= N; N is an integer in [0, 2^53), excluding booleans.
{utf8:true} means the full byte sequence decodes with strict UTF-8, including EOF.
No other parameters or predicates are accepted. Empty bytes, NUL and BOM are
valid UTF-8. Overlong, surrogate, out-of-range and incomplete encodings are not.
Results must be independent of chunk boundaries. Memory use for content is
bounded by streaming chunks and decoder state; file size/time remains uncapped.

measure_subject(path, profile) returns {profile,facts,subject}; digest and facts
must be computed from the same byte stream. Authoring passes these facts and
subject to the unchanged signed policy flow. In derived admission, both hash and
fact measurements MUST consume the chunks written to staging, without a second
source read. Derived facts become the exact recipient inputs to require_bundle.
Subject comparison, rule comparison, decision and publication rules remain in
force. API admit_bundle accepts exactly one of facts or derive. CLI input/profile
read errors keep the existing authoring/verification classifications.

A verified signed accept whose facts disagree with measurement is unsatisfied
with facts_mismatch; an honest false fact set that makes the rule reject is
unsatisfied with decision_reject. Profile/domain errors are invalid, never a
boolean false fact. Failed UTF-8 decoding is a false predicate, not a tool error.

The local requirement report includes derivation:{profile,facts,subject}; the
admitted report nests it under requirement. This is unsigned local measurement.
The recipient MUST select the profile independently; no bundle-supplied profile
is used as authority. Profiles are not signed, stored as provenance dependencies,
or needed for verify-bundle. The signature continues to bind actual boolean
facts and subject, not the method by which a signer obtained them. Thus a bundle
alone is not evidence that any derivation was performed. Only these byte
properties are measured; no broader content safety or real-world fact truth is
established. Signed body/bundle formats and 32K remain unchanged.


## Joint admission (local recipient operation)

admit_all(requirements, *, subject, output) requires 1–32 named requests before
publishing one artifact. Each request is an object with exactly name, bundle
(bytes), trust (nonempty public-key collection), rule (text), and one of facts
(boolean map) or derive (profile). Names are unique nonempty strings of at most
64 characters. All configuration is snapshotted and its shape/rule input domain
validated before reading the subject. Trust is checked separately for each
request; it is never pooled across requests.

The subject is read once into a private stage. That stream feeds one SHA-256 and
every requested derivation. In plan order, require_bundle receives that SAME
digest, the request's own trust/rule/facts and bundle. Only when ALL reports are
satisfied is the stage exclusively linked to output (0600, no replacement).
Source changes after staging cannot change either request's subject or the
published bytes. A source change detected while reading is instead an unverified
refusal, as with single admission; no snapshot of a concurrently changing source
is promised. The caller must control the output directory, as for admit.

Success is {status:admitted, artifact:{path,sha256}, requirements:[{name,report}]}.
First unsatisfied stops the run and returns {status:unsatisfied, failed:NAME,
artifact:null, requirements:[{name,report}, ...]}; this list contains only the
visited prefix, including the refusal. It does NOT claim anything about later
proofs. Invalid/unverified/local-operation exceptions retain their classifications
and abort without publication; no aggregate verdict is fabricated. The temporary
stage is removed on every path. Reports and plans are unsigned local objects,
not transferable proofs, quorum rules, or assertions of independent signers.
Multiple requests may deliberately trust the same signer.

CLI: sg admit-all PLAN --subject FILE --output FILE. PLAN is a JSON list with the
same per-request keys; bundle, rule and facts/derive values are local file paths,
resolved relative to the plan's directory (absolute paths allowed). Duplicate
JSON keys and unknown request fields are invalid. All referenced inputs are read
before staging. Missing/unreadable plan inputs are unverified/3, malformed inputs
invalid/2, verified refusal unsatisfied/4, destination errors operation_error/1,
and completed publication admitted/0. There is no global trust flag, implicit
sender-selected requirement, or network fetch. The operator selects this plan;
accepting an untrusted sender's plan would let that sender choose the policy.

admit_bundle uses the same staging/checking implementation for its single request
and retains its existing report shape. Signed records, bundles and the 32K draft
contract temperature are unchanged.

## Counterexample packets (inert evidence)

A case is canonical JSON with exactly stargate_case (integer 32), manifest and
files. Manifest has exactly title, claim, scope, limits, source, entrypoint and
expected. The first three and expected are nonempty text, limits a nonempty list
of nonempty text; source has repository (nonempty text) and commit (40 lowercase
hex Git SHA-1). These are attributed claims supplied by the packer, NOT verified
repository history or authenticated provenance. Entrypoint names an included file.

Files maps 1–64 logical relative paths to {sha256,hex}. Hex is lowercase, even
length; digest must equal SHA-256 of decoded bytes. Paths are at most 240 ASCII
characters, with slash-separated [A-Za-z0-9_.-]+ components, excluding . and .. .
Absolute paths, backslashes, case-fold duplicate names and file/directory prefix
collisions are rejected. The local packet limit is 16 MiB. case_id is SHA-256 of
the entire canonical packet, including narrative metadata and payloads.

inspect_case returns status:intact plus metadata/file hashes and decoded payloads.
Intact means structure and bytes agree, NOT that the claim is true, the author
is authentic, the code is safe, or reproduction has run. An attacker who rewrites
payload and digest can create a different intact packet. Pin the whole case_id
out of band or use existing signed subject mechanisms if authentication is needed.
Neither provenance text nor the expected outcome is accepted as a replay result.

pack_case(manifest, files) takes a logical-name-to-bytes map. CLI case-pack takes
an ordinary JSON {manifest,files:[names]} document, --root and --output; duplicate
JSON keys refuse. It reads bounded regular files under the resolved root, then
publishes exclusively. Source paths resolve symlinks inside that root; outside
root resolution refuses. Caller controls the source/output directories during use;
this is not a filesystem sandbox against a concurrent directory mutator.

case-inspect FILE reads only packet data. case-unpack FILE --output DIR validates
all contents before exclusively creating a new 0700 directory; files are 0600.
No file is imported or executed, no network lookup occurs, no permissions are made
executable, and existing destinations (including symlinks) refuse unchanged.
Success is status:materialized, executed:false. On write exceptions it attempts to
remove the newly owned directory. Directory publication is not atomic: process
death or cleanup failure may leave partial files; their presence is not completion.
The caller must control the destination parent while unpacking.

CLI codes: intact/materialized 0, output operation errors 1, malformed packet 2,
missing/unreadable inputs or local size refusal 3. There is no automatic replay
command and no transfer from expected text into a verified/satisfied decision.
Executing an extracted reproducer is a separate operator action with the operator's
permissions. Python -I is import isolation, not a sandbox.

## Finite boolean laboratory (build 15, draft)

This unsigned mode is separate from signed judgments and artifact admission.
No trust set, key or founder service participates in `lab-check`. It establishes
only a finite computation claim, not author identity or facts about external
artifacts. Existing signed-record trust requirements are unchanged.

A canonical JSON packet has exactly: `stargate_world:32`,
`contract:"boolean-exhaustive-1"`, `rule`, `inputs`, `max_atp`, `objective`,
`predecessor`, `guide`, `sources`, `license`. Its ID is SHA-256 of those bytes.
`inputs` is a sorted list of zero to eight unique non-reserved WPL names;
all must be declared and used by both programs. Rules use unassigned
`fact name: bool` declarations. The existing compiler's syntax/size/depth
admission limits apply. `max_atp` is an integer in 0..10000, per program per
row; it does not bound wall time. `objective` is `equivalence` or
`lower_max_atp`. `predecessor` is null for a created root or the parent ID
for a computed successor. A predecessor field alone is not proof of a transition.

The packet carries exact UTF-8 source bytes for the installed checker closure,
the MIT license and a fixed guide. This implementation requires equality with
its own source files before checking; different bytes give `runtime_unavailable`,
not a counterexample. Files in `sources` are never automatically loaded or
executed. The installed runtime and its source files must remain consistent
and under the operator's control. Matching source bytes are not a proof that
an interpreter, host or manually modified checker behaves correctly.

A proposal has exactly `parent` (copied packet ID) and `candidate` (WPL text).
There are no caller-supplied computed claims or trust fields. Human JSON spacing
is allowed; duplicate keys and extra fields refuse. Both programs are parsed
before enumeration; malformed source is invalid. Compiler budget failure has a
distinct `CompileIncomplete` subclass of `PolicyError`, retaining compatibility
with existing callers while allowing this mode to classify exhaustion separately.

In sorted input order, enumerate tuples from all-false to all-true. Each program
is compiled into a separate closed SKI term for each row. The existing compiler
cross-checks the kernel result against its source interpreter. A second checker
uses a separate character lexer and shunting-yard parser, without importing that
parser, AST, interpreter or lowering. Both programs' results must agree with
this oracle before any row becomes evidence of equivalence or difference.

Semantic results are:

- `equivalent`: all 2^N rows completed and matched. Maxima are computed over the
  full domain. Before declaring equivalence, the checker requires exactly 2^N
  rows and checks each row's input against the bit pattern of its index, computed
  without the enumeration iterator. Missing, repeated or out-of-order inputs are
  checker_error, never equivalence. Admission additionally requires strictly smaller candidate maximum
  ATP if the objective is `lower_max_atp`; equality is not improvement.
- `counterexample`: the first completed, oracle-checked row with different
  parent/candidate boolean results. No successor is emitted.
- `incomplete`: no counterexample was established before budget/resource refusal.
  Completed rows are retained, but no successor is emitted.

`checker_error` is a separate operational failure for internal compiler or
cross-checker disagreement, never an accusation against the candidate. A run
stops at the first counterexample, incomplete row or checker error. It need not
search later rows after a refusal. Reports are recomputed, unsigned observations;
there is no API that admits a saved report as evidence without re-execution.

On admission, the successor retains the parent's contract, source closure,
inputs, budget and objective, replaces `rule` with candidate text, and sets
`predecessor` to the exact parent ID. Parent bytes remain unchanged. The result
is deterministic for a fixed runtime/packet/proposal; multiple valid successors
are allowed. No repository merge or external deployment occurs.

CLI: `lab-check` exits 0 for admitted, 4 for a counterexample or equivalent but
not improved, 3 for incomplete/runtime unavailable, 2 for malformed inputs, and
1 for checker/operation errors. `--output` writes only admitted successor bytes,
refusing an occupied destination through the existing bundle writer. Reports
include row inputs, boolean results, term hashes and ATP, plus the successor ID
when admitted. Missing experiment/proposal files give `unverified` / 3; failure to write an
output remains an operation error / 1.

`lab-unpack` checks structure and local runtime correspondence, then writes fixed
paths in a fresh directory (0700, files 0600). Existing files, directories and
symlinks refuse. Its parent directory must be controlled by the caller; extraction
is not an atomic multi-file transaction, and failures attempt cleanup. It never
runs packet code. The included `replay.py` requires an explicit invocation and
Python >=3.11 with its standard library; neither a Stargate installation nor
cryptography/network access is required. `-I -S` avoids site startup and installed
packages, but is not a sandbox. `lab-inspect` emits `runtime_digest = SHA256(canon(sources))` and
`replay_digest = SHA256(replay.py bytes)`. Semantic reports carry runtime_digest.
Replay takes a proposal path, optionally a new successor path, and requires
`--expect-runtime` with a separately obtained digest. Before importing packet
modules, the launcher hashes the fixed source map with standard-library JSON
(the filenames are ASCII, so its key ordering matches canonical UTF-16 ordering).
A mismatch gives runtime_unavailable / 3 and publishes nothing. Replay requires
-I -S, checked using builtin sys before importing other modules. After preflight,
a private loader compiles exactly the verified source snapshot in dependency
order, with an empty package search path. No packet directory is added to sys.path
and no pyc is loaded. The runtime_sources accessor uses loader.get_data: in replay
this returns snapshot bytes, while the normal installed loader reads its source
files. No packet source is reread after its digest check. Missing or
malformed expected digests refuse with exit 2.

The expected runtime digest AND the launcher bytes must be authenticated through
an independent trusted installation or reviewed revision. A packet or report
cannot authenticate its own checker. The preflight is not protection against
replacement of the independently checked launcher itself or dishonest hosts.
The snapshot loader excludes adjacent modules and stale/adversarial packet
bytecode caches, and source-file changes after hashing do not change execution.
Ordinary installed sg still assumes a consistent trusted installation. Both paths
trust the interpreter and its standard library.

Invalid input or local I/O errors in this minimal replay
script may print a Python traceback; it never claims admission on those errors.


## Counterexample-guided neighborhood search (build 16, draft)

`lab-search` is an untrusted proposal strategy above the finite lab; it does not
change world/proposal/admission formats. It considers preorder one-node negation,
binary operator flip, operand swap, idempotence for structurally equal operands,
and double-negation elimination, then traverses children left-to-right. Mutated
ASTs are printed as fully parenthesized WPL with sorted declarations. Up to
max_candidates (integer 1..256, default 32) generated strings are considered.
Exact repeated strings and invalid generated rules still consume attempts.
A generator's exhaustion is local to this neighborhood, not a no-solution proof.

Experience is a data object with exactly parent, runtime_digest, counterexamples.
Each of at most 256 entries has candidate text and input (the exact boolean
assignment for all named inputs). Both identities must match the supplied world.
Every entry is recomputed using compiler/kernel and the independent oracle;
non-reproducing claims refuse as invalid. Resource refusal returns incomplete,
checker disagreement checker_error. Only the first witness per input is retained.
Caller-owned experience is snapshotted, never edited or executed.

For each new candidate, replay remembered inputs first. A completed disagreement
produces a screened attempt with its row witness; no full check is needed to
reject that candidate. Matching this sample grants nothing. All survivors go to
lab.verify_transition, including its independent oracle, coverage checks and
cost objective. Full counterexamples extend experience. A candidate that is incomplete in
screening or the full gate is marked incomplete, increments incomplete_candidates,
and contributes no negative example; search continues with the next candidate.
A checker_error stops search. If the iterator is exhausted after any incomplete
candidate, status is search_incomplete with reason incomplete_candidates (CLI 3),
not neighborhood_exhausted. Incoming experience replay still refuses the search
on incomplete/error before any candidates run: it has not established its hints.

Reports contain parent, runtime_digest, attempted, full_checks, screened,
incomplete_candidates, attempts
and experience. Per-attempt status is duplicate, invalid, screened, or the full
lab result. found includes the exact two-field proposal and successor ID, with
successor bytes returned separately. Search returns only a successor supplied
by the full gate; a saved report has no admission authority. Experience can be
reused as data, but neither search reports nor heuristics authenticate themselves.

Statuses: found (CLI 0), neighborhood_exhausted (4), search_incomplete with
candidate_limit (3), incomplete (3), checker_error (1). Malformed input is 2.
Reaching the candidate limit remains incomplete even if the iterator would be
exhausted on its next call; the search does not look ahead beyond the limit.
The search budget excludes incoming experience replay (separately capped at 256
witnesses) and is not an ATP/CPU aggregate budget. Output uses the existing
exclusive bundle writer only after found. No other files are written by search.
