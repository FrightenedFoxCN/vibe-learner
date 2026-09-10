# Diagnostic document fixture

`diagnostic-document.pdf` is a synthetic one-page text PDF generated with
PyMuPDF for the real upload/parse/plan browser test. It contains a short chapter
about observation and evidence repeated six times, using built-in Helvetica.
There is no user data, image/OCR dependency, embedded attachment or external link.
The browser test checks that neither its filename nor text reaches diagnostics.
This fixture exercises text parsing, not OCR accuracy or representative textbooks.
