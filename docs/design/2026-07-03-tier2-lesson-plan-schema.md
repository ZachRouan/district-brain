# Tier 2 — Curriculum & Lesson-Plan Ingestion + Metadata Schema

**Status:** Living draft — Phase 1 + Phase 2 are both in build scope; Phase 2's relationship-access engine runs on a **synthetic SIS adapter**, so it needs no real student data or real SIS. What stays **provisional** (revised once school + SIS facts and a Drive sample arrive): the concrete real-district SIS adapter, the social-studies grammar, and the §9 open questions.
**Date:** 2026-07-03 (last revised 2026-07-03)
**Scope decision:** Build **both phases**. Phase 1 = the district-consensus corpus (curriculum maps, pacing guides, scope & sequence). Phase 2 = teacher-authored lesson/unit plans + relationship-based access, built as an **SIS (Student Information System)-agnostic engine behind a pluggable adapter** and developed/tested against a **synthetic adapter**. Adapting to a real district's SIS — yours or another school's — is then implementing one adapter against a fixed interface (§5).

> Ohio standard-code grammars below were extracted from the official Ohio Department of Education and Workforce (ODEW, formerly ODE) standards PDFs; the initial "uniform grade-band code" assumption was **caught and corrected** during verification — Ohio uses four distinct per-subject grammars and Ohio science is *not* NGSS (Next Generation Science Standards). Sources are listed at the end.
>
> **This is a living document.** Expect it to change as facts arrive from the schools and the SIS: the §9 open questions should shrink, the SIS/section fields (§2.1) firm up, and the social-studies grammar (§3.1) get filled in or dropped. Sections not yet grounded in the district's real artifacts are marked _(provisional)_.

---

## 1. Goal & context

District Brain's Tier 2 ingests the district's own curriculum artifacts so staff can ask *"what does our 3rd-grade math curriculum cover on fractions, and when in the year?"* — answered from the district's real documents, with chunk-level citations. The differentiating end-state (Phase 2) is **relationship-based access**: a 3rd-grade teacher retrieving what her current students' 2nd-grade teachers actually covered.

The non-negotiable from the project charter holds unchanged: **access scoping lives in retrieval, never in the prompt.** Standard codes and metadata added here are *retrieval* keys; the access boundary stays exactly where Tier 1 put it — `visible_documents(user)` in `chat/retrieval.py`.

### What's new versus Tier 1

Tier 1 documents are flat: a `Document` scoped to a set of `Role`s, chunked, embedded. Tier 2 adds a **curriculum metadata layer** on top of the same `Document`/`Chunk` models, plus a **local academic-standards table** to resolve standard references into stable identifiers.

### Why consensus-corpus-first

| | District-consensus tier | Teacher-authored tier |
|---|---|---|
| Artifacts | curriculum map, pacing guide, scope & sequence | unit plan, daily lesson plan |
| Access | broadly staff-visible (role-based, like Tier 1) | section-scoped (needs SIS org-graph) |
| Tier-3 bleed risk | low (no student names in a district pacing guide) | **high** (differentiation fields, "what I actually taught") |
| Blocked on | nothing | SIS export reality, multi-role users, per-section authoring facts |

Phase 1 ships real teacher value (search the district's curriculum history) **and** exercises every genuinely-new mechanism — four-grammar code extraction, local standards resolution, table-structure chunking — without waiting on SIS archaeology or risking a FERPA (Family Educational Rights and Privacy Act) one-way door. This directly serves the PROJECT.md pre-mortem: smallest-shippable over grander-unshipped (pre-mortem #6, builder abandonment), and it keeps the highest privacy exposure (pre-mortem #2, one privacy incident) out of the first build.

---

## 2. Data model

Three additions, all in `corpus/`. `Document` and `Chunk` are unchanged in shape; `Document` gains an optional one-to-one metadata companion.

### 2.1 `CurriculumMetadata` (one-to-one with `Document`)

Present only for Tier 2 documents. Keeps `Document` tier-agnostic.

| Field | Type | Source | Access-scoping (Phase 2)? |
|---|---|---|---|
| `document` | OneToOne(Document) | — | — |
| `artifact_types` | ArrayField(choice) | extracted | no |
| `merged_artifact` | bool | inferred | no |
| `authorship_level` | choice {district_consensus, school, individual_teacher} | inferred (+ override) | **yes** |
| `grades` | ArrayField(str) | extracted (+ override) | no (retrieval filter) |
| `subject` | choice {ela, math, science, social_studies} | extracted | no (retrieval filter) |
| `school_year` | CharField `"2025-26"` | **SIS / coordinator** | **yes** |
| `sis_teacher_id` | CharField, null | SIS | **yes** |
| `sis_section_id` | CharField, null | SIS | **yes** |
| `document_mode` | choice {prescribed_planned, enacted_actual} | inferred | no |
| `lifecycle_status` | choice {living, point_in_time} + `revision_date` | inferred | no |
| `parent_document` | FK(Document, self, null) | inferred | no |
| `field_provenance` | JSONField `{field: {source, confidence}}` | — | no |

Notes:
- **Access-scoping vs. retrieval filtering.** The access-scoping fields (`authorship_level`, `school_year`, `sis_teacher_id`, `sis_section_id`) parameterize the Phase 2 retrieval *filter* (`visible_documents()`) — they never enter the prompt and never grant entitlement on their own; entitlement is the org-graph relationship, which these fields key into. Every other field (`grades`, `subject`, `standard_codes`, …) only narrows *relevance* within what a user is already entitled to see. This keeps the §5 invariant intact: metadata and codes are retrieval keys, never access keys.
- **`artifact_types` is an array + `merged_artifact` flag** because districts routinely collapse map + pacing + scope-and-sequence into one spreadsheet. A single-label assumption mislabels and misroutes retrieval.
- **`authorship_level` is the access-decision key, not `artifact_types`.** A district-*provided* unit plan is broadly visible; a teacher-*adapted* copy is section-sensitive. Because it's inferred and genuinely ambiguous for unit plans, it carries a confidence in `field_provenance` and is **coordinator-overridable**. Phase 1 only ingests `district_consensus` docs, so this field is uniform in Phase 1 but the schema and override path exist from day one.
- **`school_year` MUST NOT be derived from file timestamps.** Plans are copied/reused year to year; `modifiedTime` lies. It is a separately-sourced field (SIS section-to-course-year link, or a coordinator tagging step). Getting it wrong scopes the flagship feeder query to the wrong year — a correctness failure, not a cosmetic one. Kept **separate** from `last_updated`.
- `sis_teacher_id` / `sis_section_id` are opaque SIS keys now (nullable CharFields); they become FKs to org-graph models in Phase 2. Null for all Phase 1 consensus docs. _(Provisional until the district's SIS export reality is confirmed — see §9.)_
- `field_provenance` records where each inferred/extracted field came from (`folder_path`, `filename`, `doc_header`, `doc_body_regex`, `classroom_topic`, `onenote_section`, `planbook_csv`, `sis`, `coordinator_override`) with a confidence tag. Grade/subject especially must be storable as "inferred, low-confidence" and overridable.

### 2.2 `AcademicStandard` (canonical standards table, imported locally)

A local mirror of the standards catalog, so a free-text code resolves to a stable identifier **offline** (no per-ingest API call — fits the closet box).

| Field | Notes |
|---|---|
| `canonical_id` | Common Standards Project GUID (primary resolved key) |
| `asn_identifier` | Achievement Standards Network id (crosswalk) |
| `statement_notation` | the human code, e.g. `3.NF.1` — **NOT globally unique** |
| `jurisdiction` | e.g. Ohio (`F4CB2B5DF6904071BBCC671A3AB783B8`) |
| `subject`, `grade_or_band` | composite scope key with jurisdiction |
| `code_system` | which grammar: `math_k8`, `math_hs`, `math_practice`, `ela`, `science_k8`, `science_hs`, `band_coded`, `social_studies` (unverified) |
| `description` | standard text (for semantic Stage-2 matching + display) |
| `set_version`, `superseded` | track current vs. retired standard sets |
| `parent_id`, `ancestor_ids` | hierarchy (domain → cluster → standard) |

Populated by a management command `import_standards` from a local CSP export (JSON/CSV). CC-licensed (Creative Commons) ASN data; no runtime dependency on any external host.

### 2.3 `StandardReference` (through model: Document/Chunk ↔ AcademicStandard)

Every standard *mention* found in a document, resolved or not.

| Field | Notes |
|---|---|
| `document` | FK (required) |
| `chunk` | FK (nullable) — set when the code was found in a specific table cell/row, so week/unit→standard survives |
| `standard` | FK(AcademicStandard, **nullable**) — null = unresolved, kept first-class |
| `raw_token` | exact string as written, preserved for citation |
| `match_method` | {exact_regex, normalized_regex, semantic_suggested, coordinator_confirmed, unresolved, district_local} |
| `match_confidence` | float |

**A wrong resolved code silently poisons the shared retrieval key.** So: never guess. Below-threshold matches stay `unresolved` (raw token retained, surfaced for human confirmation), and legitimately local/non-standard objectives go in a `district_local` bucket so they aren't perpetually re-flagged.

### 2.4 Enabling Tier 2 in the tier guard

`Document.ENABLED_TIERS` becomes `(Tier.TIER_1, Tier.TIER_2)` and the `document_tier_1_only` CheckConstraint widens to `tier__in=[1, 2]` (kept as a physical guard so **Tier 3 still cannot be stored**, by any code path). This is the deliberate, migrated widening the Tier-1 constraint comment anticipated. Per the project charter non-negotiable #3, activating Tier 2 is also a *process* gate (Tier 1 running cleanly + board awareness) — the migration is the technical half of a decision made outside the code. The existing tier-guard tests in `tests/test_models.py` must be updated in lockstep (see §8).

### 2.5 Multi-role users (`accounts` change)

Phase 2 relationships assume a person can hold several roles at once (teacher **and** coach; a principal who also teaches a section). Today `User` holds exactly one `Role` (`accounts/models.py`); PROJECT.md's design notes flag multi-role as the required step toward relationship-based access. The change: `User.role` (single FK) → a many-to-many (or a `UserRole` through model), and every `visible_documents()` caller unions the user's role scopes. This touches the `accounts` model and the retrieval boundary, so it lands with Phase 2, behind the same scoping tests.

---

## 3. Standard-code extraction & resolution

### 3.1 The four Ohio grammars (verified)

A single regex will **not** cover these. Extraction dispatches on `subject`.

| Subject | Format | Examples |
|---|---|---|
| Math K-8 | `grade.DOMAIN.number[.sub]`, no cluster letter | `3.OA.7`, `3.NF.3.d`, `1.NBT.4` |
| Math HS | `CATEGORY.DOMAIN.number`, **dots not hyphens**; `(+)`/★ sit outside the token | `A.APR.1`, `F.IF.4`, `G.CO.1` |
| Math practices | `MP.number` (non-unique across grades/states) | `MP.1` |
| ELA | `STRAND.grade.number[sub]`, grade in the **middle** | `RL.3.1`, `RI.4.3`, `W.5.1a` (strands RL/RI/RF/W/SL/L) |
| Science K-8 | `grade.STRAND.number` (Ohio-authored, **not NGSS**) | `1.PS.1`, `3.LS.2`, `6.ESS.1` |
| Science HS | `COURSE.TOPIC.number`, no grade digit (Ohio-authored) | `PS.M.1`, `B.H.1`, `C.PM.1` |
| Band-coded (Technology, Fine Arts, some Sci/SS materials) | `gradeBAND.STRAND.statement.indicator` | `6-8.KC.1.a` |
| Social Studies | **UNVERIFIED** _(provisional)_ | no parser ships until the format is confirmed against the official Ohio SS standards PDF |
| Extended (special-ed) | append `a/b/c` complexity suffix (a = highest) | preserve, do not strip |

> **Sub-indicator vs. extended-standard suffix.** A trailing lowercase letter is overloaded: in `W.5.1a` / `3.NF.3.d` it is a normal sub-part of a *regular* standard, but Ohio's **Extended** Standards (a separate published set for students with significant cognitive disabilities) append an `a/b/c` *complexity* suffix. The two are told apart by **which standard set the document aligns to** — extended standards occupy a distinct set/namespace in the catalog — not by the token shape. The reliable signal is the source's alignment, never a regex on the suffix. _(Provisional — confirm against real extended-standard samples before building.)_

### 3.2 Two-stage resolution

**Stage 1 — coded mentions (high feasibility for math/ELA):**
1. Scan **the whole document body**, not just a labeled "Standards" field — codes appear inline in objectives too.
2. Dispatch the regex on `subject`.
3. **Normalize before matching:** strip `CCSS.MATH.CONTENT.`/`CCSS.ELA-LITERACY.` prefixes; treat Ohio dotted HS-math (`A.APR.1`) == national hyphen (`A-APR.1`); accept Ohio short (`3.MD.7`) == cluster-lettered (`3.MD.C.7`); strip leading/trailing `(+)` and modeling-star adornments; preserve extended `a/b/c` suffixes; apply fuzzy OCR tolerance (`l`/`1`, `O`/`0`, case).
4. Exact-match the normalized token against the local `AcademicStandard` table using a **composite scope key** `(jurisdiction=Ohio, subject, grade)` — because `statement_notation` is not unique (`3.G.2`, `MP.1` recur). A missing/wrong subject or grade causes cross-subject/cross-state collisions.
5. Store `canonical_id` + `asn_identifier` as the resolved key; keep `raw_token` for citation.

**Stage 2 — free-text/prose (medium; science & social studies especially):** semantic nearest-neighbor *suggestion* against `AcademicStandard.description`, with **human confirmation**. Never auto-assign below a threshold set from a small labeled eval on real district phrasing (accuracy is currently unmeasured — the eval is a build task, mirroring the Tier-1 practice of calibrating retrieval against measured data, not anecdotes).

**Fallback:** no confident match → keep the raw mention as a first-class `unresolved` reference. Never drop it, never guess. Expect **low code yield for science/social studies** and rely on `grade + subject + school_year + section` metadata plus embedding retrieval there.

### 3.3 Dataset & caveats

- **Common Standards Project** (`api.commonstandardsproject.com`): free, keyless, carries Ohio's jurisdiction with current *and* superseded sets. Import to a local RDBMS via the CC-licensed bulk data.
- **CSP currency vs. latest ODEW wording is unconfirmed** → ingest-QA spot-checks sampled CSP descriptions against the official ODEW PDFs.
- CASE / Satchel Rosetta Exchange is a secondary path with **different field names** (`humanCodingScheme`, UUID `identifier`) — keep a crosswalk, don't collide namespaces.
- ASN's own host has degraded TLS — **never a runtime dependency** (import-time only).
- EdGate/EdGraph are paid and not needed.

---

## 4. Ingestion & chunking

Extends the existing pipeline (`corpus/extractors.py`, `corpus/chunking.py`, `corpus/ingest.py`) — it is not replaced.

- **Header recognition, not enforcement.** Segment on recognized section headers but chunk the prose beneath them as free text. Anchor on the near-universal field set (Objective, Standards, Materials, Procedure, Assessment, Differentiation) with an **alias table** for framework labels — UbD (Enduring Understanding / Essential Question / Transfer / Performance Task; "Determine Acceptable Evidence" == "Assessment Evidence"), Hunter (Anticipatory Set / Guided Practice / Closure), 5E (Engage/Explore/Explain/Elaborate/Evaluate), GRR (Gradual Release of Responsibility — I Do / We Do / You Do), and the Danielson framework as used in OTES 2.0 (Ohio Teacher Evaluation System) components 1c–1f. **All headers optional and unordered** — never hard-code counts or sequence.
- **Table-structure recovery for pacing guides & maps.** These are grids (week × standard). Extend the existing enriched-table path (`_render_table` in `corpus/extractors.py`, commit `fb2a541`) so a week/unit → standard-code association is preserved in the chunk *text*. A code stripped of its row/column context loses the very metadata (which week/unit) that makes it filterable. `_render_table` is pure text rendering — no `Chunk` rows exist at that point — so the `StandardReference.chunk` FK is populated in a **post-chunking step in `ingest_document`** (`corpus/ingest.py`), correlating each resolved raw token back to the `Chunk` it landed in; the existing `FORM_FEED`-per-row isolation makes that near-1:1 row→chunk mapping reliable.
- **Whole-document code regex** (§3.2 step 1), in addition to any dedicated alignment section.
- **Graceful degradation.** No headers / single paragraph → whole-document chunking + whole-document code regex, not a dropped plan. Do **not** normalize every plan to one template.
- **OCR** born-from-paper/scanned PDFs before the code regex; use the fuzzy normalization above. *Prevalence of scanned vs. born-digital in this district is unverified* — sample the corpus to decide whether OCR is a core dependency or an edge case (Phase 1 consensus docs are likelier born-digital).
- **`field_provenance` on every metadata write**; exploit richer structure only when a source provides it (Google Classroom topic = unit boundary, course = section; OneNote notebook tree; Planbook CSV), but design around the least-structured source (prose/scanned PDF).

---

## 5. Access model

### Phase 1 — consensus corpus (role-based, unchanged mechanism)

Consensus documents scope by `Role` exactly as Tier 1 does — `visible_documents(user)` is unchanged in mechanism. `authorship_level=district_consensus` documents are attached to the staff role(s); retrieval filters by role membership as today. **No relationship logic, no prompt-level filtering.** The security boundary — `visible_documents()` and its scoping tests (`tests/test_retrieval_scoping.py`) — is extended, never loosened. (Enabling Tier 2 also requires updating the separate tier-**guard** tests in `tests/test_models.py`; see §8.)

### Phase 2 — relationship-based access, SIS-agnostic

Built now, against a **synthetic SIS adapter** — no real student data, no real SIS required (tier discipline). Adapting to a real district is implementing one adapter against the interface below.

**The org-graph, abstracted.** The access engine consumes an `SISAdapter` interface, never a specific vendor. Entities it exposes:

- `Student(id)`
- `Staff(id)` → maps to a District Brain `User`
- `Section(id, subject, grade, school_year, teacher_id)` — a class in a given year
- `Enrollment(student_id, section_id, school_year)` — who was in what class, when
- **Feeder edges** — derived from enrollment history: a current section's students trace back to their prior-year sections (the "feeder homerooms").

**Adapter interface (roughly):**
- `sections_for_teacher(teacher_id, school_year) -> [Section]`
- `students_in_section(section_id) -> [student_id]`
- `feeder_sections(teacher_id, current_year) -> [Section]` — current students → their prior-year sections

**Resolving the canonical rule.** *"A 3rd-grade teacher may see last year's 2nd-grade plans for the feeder homerooms of her current students"* becomes: `feeder_sections(teacher, current_year)` → a set of `(section_id, school_year)` pairs the teacher is entitled to. `visible_documents(user)` then returns:

> consensus docs (role-based, Phase 1) **∪** teacher plans where `authorship_level=individual_teacher AND (sis_section_id, school_year) ∈ entitled feeder set` **∪** the user's own authored plans.

Scoping stays a database filter, computed before similarity — never a prompt instruction.

**Synthetic adapter.** A generated K-5 building (rosters, sections, multi-year enrollment, feeder patterns) implements `SISAdapter` for dev and test. The full engine — and the "motivated 14-year-old" red-team (a student probing for another's records, a teacher reaching for a non-feeder section's plans, year-boundary edges) — runs on it with zero real data.

**Per-district adapters (the "different schools" path).** PowerSchool, Infinite Campus, ProgressBook, Skyward, Aeries each implement the same interface; the engine is unchanged. This is both the maintenance story and the go-to-market wedge (non-PowerSchool districts have no vendor path today).

Phase 1's schema already carries every field Phase 2 keys off (`authorship_level`, `sis_teacher_id`, `sis_section_id`, `school_year`), so no Tier 2 re-ingest is needed as adapters arrive.

**Invariant:** standard codes are shared retrieval keys and must **never** grant access. Any design where a resolved code widens entitlement is rejected.

---

## 6. Tier-3 bleed controls

Phase 1 largely sidesteps this (consensus docs carry no student data), but the ingest pipeline gets the screening hook now so Phase 2 can't forget it.

- **Enacted/diary lesson records** (`document_mode=enacted_actual`) routinely embed student names, behavior notes, worked examples → they cross into Tier 3. Scrub-at-ingest or exclude; **when in doubt, exclude** (FERPA is a one-way door). Decide deliberately whether to ingest them at all.
- **Differentiation / accommodation blocks** frequently name individual students and reference IEP/504 accommodations → screen and scrub before ingesting the plan.
- **Per-student sources are not Tier 2 curriculum:** ingest only teacher-canonical material (Google Classroom `courseWorkMaterials`, OneNote Content Library), never per-student OneNote section groups or Classroom submissions.
- **Assessment-evidence sections** may cite specific student results → screen before promoting to filterable metadata or citable chunks.
- **Synthetic student data only in all development** — the tier-discipline non-negotiable. Never pull real teacher plans that embed student data into a Tier 1/2 prototype, even as test data.
- Control point is the **document content scrub at ingest**, not the metadata layer.

---

## 7. Staleness

- `last_updated` (an existing `Document` `DateField`, sourced from the file's `modifiedTime`) is the staleness signal the UI already surfaces per source. Kept **separate** from `school_year` (which it cannot stand in for).
- `lifecycle_status`: maps / scope-and-sequence / pacing guides are **living** (continuously revised) — a stale pacing-guide citation is a real failure mode; lesson plans are **point-in-time**. Drives "cite the current version" and staleness surfacing. Prefer "I don't have that" over stale synthesis.

---

## 8. Scope boundary (what's in / out)

Both phases are in build scope. Phase 2's relationship engine is built and tested on the synthetic SIS adapter.

**In — Phase 1 (corpus + standards foundation):** `CurriculumMetadata`, `AcademicStandard`, `StandardReference` models + migrations; widen `ENABLED_TIERS`/CheckConstraint to Tier 2; **update the tier-guard tests in `tests/test_models.py` (`test_document_rejects_tiers_above_one`, `test_database_refuses_a_direct_tier_two_save`) to reject only Tier 3, matching the widened guard**; `import_standards` command (Ohio CSP data); four-grammar extractor + normalization + Stage-1 resolution + unresolved bucket; header alias table + pacing-guide table-association chunking; ingest of `district_consensus` artifacts scoped by role; tier-3 content-scrub hook; labeled eval harness for Stage-2.

**In — Phase 2 (relationship engine, on synthetic SIS):** multi-role users (`accounts` change + retrieval union); the `SISAdapter` interface + a **synthetic adapter** (generated rosters/sections/enrollments/feeder patterns); the relationship-scoped `visible_documents()` branch; ingest of teacher-authored unit/lesson plans with the tier-3 scrub enforced; the "motivated 14-year-old" red-team test suite against the synthetic building.

**Out (deferred — needs real facts):** the concrete **real-district SIS adapter** (yours or another school's — waits on §9 answers about what your SIS exposes); anything gated on the **per-section-vs-grade-team authoring** fact (§9 Q1) — the engine is built and correct, but real `sis_section_id` population in *your* building waits on that answer; the **social-studies parser** (grammar unverified); Stage-2 semantic auto-suggestion in production (built as a harness, off by default until the eval passes); Drive `appProperties` write-back.

---

## 9. Open questions — deferred to colleagues / a Drive sample  _(provisional — this list shrinks as answers arrive)_

These no longer block *building* Phase 2 (the engine runs on the synthetic adapter) — they gate its **real-data payoff in your building** and the shape of your real SIS adapter. Nothing web research can answer; only colleagues + your SIS + a Drive sample. Phrased as precise asks so the conversation is short:

1. Are lesson plans authored **per-section**, or **shared across a grade-level team**? (Decides whether `sis_section_id` is fillable — and whether the flagship feeder feature is realizable from existing artifacts at all.)
2. Does the **SIS expose** section→file / teacher→course-**year** links, and the **feeder-pattern graph**? (Without these org-graph keys, relationship access can't resolve at retrieval time.)
3. **Platform mix** — Google (Docs/Sheets/Classroom), OneNote Class Notebooks, Planbook, or a mix? (Picks the primary ingestion adapter; "Google is dominant" is an unverified prior.)
4. In what **exact printed form** do teachers write standard codes, per subject — bare `3.NF.1`, cluster-lettered `3.NF.A.1`, full CCSS-prefixed, or prose with none? (Sets regex priorities. Share ~20–30 real or synthetic-mirrored plans.)
5. Do we ingest **social studies**? (Its Ohio grammar is unverified — a parser is built only if it's in scope and only after confirming the format.)
6. Does the district run **OTES 2.0 / Danielson** planning templates with 1c–1f as verbatim fields? (Confirms whether the Danielson aliases earn their place in the header recognizer.)
7. District **calendar structure** (quarters/trimesters/semesters), and is the calendar itself ingestable so pacing-guide "week of X" resolves to concrete dates?
8. Existing **Shared Drive layout / filename convention** to lean on as a structured prior, or fully ad-hoc?

---

## 10. Key risks

1. **`school_year` provenance** — file timestamps are confirmed unreliable; source from SIS/coordinator or the flagship feeder query scopes to the wrong year.
2. **`section` may not exist** — if plans are grade-team-shared, `sis_section_id` is unfillable and the lesson-plan access use case needs new authoring discipline. Open until confirmed.
3. **Subject coverage asymmetry** — math/ELA codes are reliable; science/social studies are prose-based, low-yield. Don't over-promise standard-level retrieval across all subjects; it degrades to grade+subject+year retrieval for science/SS.
4. **Standard-resolution corruption** — a wrong canonical code poisons the shared retrieval key. Never-guess + unresolved bucket + human-confirm is a hard requirement; Stage-2 accuracy is unmeasured until the eval exists.
5. **Machine-readable data currency** — CSP may lag latest ODEW wording; social-studies grammar unverified. Ingest-QA spot-checks against official PDFs; no SS parser ships on assumption.
6. **`statement_notation` non-uniqueness** — always match with the `(jurisdiction, subject, grade)` scope key.
7. **Tier-3 bleed** — lesson plans embed student data; scrub-at-ingest is load-bearing; a miss is a FERPA one-way door.
8. **Merged artifacts** — districts collapse map+pacing+S&S into one sheet; the schema must allow multi-label or ingest mislabels/misroutes.
9. **Authorship ambiguity** — unit plans vary district-provided vs teacher-adapted; misclassification over-shares or over-restricts. Needs confidence + coordinator override.
10. **Access-scoping discipline** — codes are retrieval keys, never access keys; all scoping stays in the retrieval filter, never the prompt.

---

## Sources (verified)

- Ohio Math standards (grade 3), ODEW PDF — `education.ohio.gov/.../MATH-Standards-Grade-3.pdf`
- Ohio ELA standards (grade 1), ODEW PDF — `education.ohio.gov/.../1st_Grade_ELA_Standards.pdf`
- Ohio Learning Standards for Technology (2025), ODEW PDF — `education.ohio.gov/.../Ohio-s-Learning-Standards-for-Technology-2025-Final.pdf`
- Common Standards Project API — `api.commonstandardsproject.com` (Ohio jurisdiction `F4CB2B5DF6904071BBCC671A3AB783B8`)
- Understanding by Design white paper (ASCD) — `files.ascd.org/.../UbD_WhitePaper0312.pdf`
- Curriculum mapping (Jacobs consensus vs. diary maps) — `en.wikipedia.org/wiki/Curriculum_mapping`, `cpet.tc.columbia.edu/news-press/demystifying-curriculum-maps`
- Ohio ASPIRE lesson-plan templates — `ohioaspire.org/LessonPlanTemplates.html`
