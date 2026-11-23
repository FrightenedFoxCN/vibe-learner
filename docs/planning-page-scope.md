# Planning physical PDF pages

Document Setup accepts an optional physical PDF page range such as `100–103, 110`.
The numbers are the reader's one-based PDF page positions. Empty input leaves the
constraint unknown. Zero, reversed/overlapping ranges, printed Roman labels and
non-integer text are rejected. Up to 64 intervals are accepted. The text survives
Plan/Settings navigation and page reload in the existing draft cache; file bytes
are not serialized. Goal-only generation omits the page constraint.

After parsing, the generation Hook checks the ranges against the actual page
count before starting Planning. The server independently checks its authoritative
Document row during operation admission. The range is saved in `PlanningIntentV1`,
the operation fingerprint and protected generation input. Reusing a request key
with another range conflicts rather than silently admitting another operation.

Existing Planning tools reject text/image requests outside explicit physical
ranges. Proposal validation requires every schedule anchor and content slice to
stay inside the requested intervals and cover all requested pages. Commit checks
these bounds again against the admitted intent before writing any Plan/Document
projection; the v2 committed-projection and operation read-back checks retain that
binding. The browser decoder also rejects an out-of-scope or incomplete persisted
schedule.

## Printed labels are separate

`DocumentPageCoordinateV1` / `DocumentPageNumbering` pair a physical page with an
optional `PrintedPageLabelV1` / `PrintedPageLabel`. Labels come only from the
uploaded PDF's explicit page-label metadata. A PDF can therefore map physical
100 to printed label `70`, or supply no printed label at all. Neither case changes
which page is read, rendered, scheduled or committed. The API never infers labels
from OCR or assumes a constant offset. Metadata is a reader aid and may differ
from the visible ink on a page.

Plan Workspace shows the saved physical range and independently queries up to
64 range endpoints for label comparison. It identifies the current Document
revision used for that comparison; the original Plan's physical constraint stays
historical and immutable. Missing/unavailable labels leave the scope usable and
are displayed as unknown/unavailable. The read-only label DTO does not mutate
Document/Debug or rewrite historical creation digests.
