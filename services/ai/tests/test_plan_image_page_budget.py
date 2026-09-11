"""Page-image ceiling must also bound page-range preparation."""
import tempfile
import unittest
from pathlib import Path
import fitz
from app.models.planning import ReadPageRangeImagesArgumentsV1
from app.services.plan_prompt import read_page_range_images


class PlanImagePageBudgetTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / 'six-pages.pdf'
        with fitz.open() as document:
            for index in range(6):
                page = document.new_page(width=72, height=72)
                page.insert_text((8, 20), str(index + 1))
            document.save(self.path)

    def test_huge_model_page_end_still_renders_only_four_pages(self):
        arguments = ReadPageRangeImagesArgumentsV1(page_start=1, page_end=10**30, max_images=4)
        result = read_page_range_images(document_path=str(self.path), **arguments.model_dump())
        self.assertEqual(result['image_count'], 4)
        self.assertEqual([image['page_number'] for image in result['images']], [1, 2, 3, 4])

    def test_requested_count_and_finite_page_end_both_limit_rendering(self):
        result = read_page_range_images(document_path=str(self.path), page_start=3,
                                        page_end=10**30, max_images=2)
        self.assertEqual([image['page_number'] for image in result['images']], [3, 4])
        result = read_page_range_images(document_path=str(self.path), page_start=3,
                                        page_end=3, max_images=4)
        self.assertEqual([image['page_number'] for image in result['images']], [3])

    def test_start_beyond_document_does_not_wrap_or_render(self):
        result = read_page_range_images(document_path=str(self.path), page_start=10**30,
                                        page_end=10**30 + 8, max_images=4)
        self.assertEqual(result['images'], [])
