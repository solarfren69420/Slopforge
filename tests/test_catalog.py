import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build import validate, markdown
from art import make_art


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.catalog=json.loads((ROOT/'data/projects.json').read_text())

    def test_actual_catalog_is_valid(self):
        self.assertEqual(len(validate(self.catalog)),len(self.catalog['projects']))
        self.assertEqual({p['kind'] for p in self.catalog['projects']},{'games','tools'})

    def test_unsafe_repository_url_is_rejected(self):
        self.catalog['projects'][0]['repo']='https://github.com.evil.example/project'
        with self.assertRaises(AssertionError):validate(self.catalog)

    def test_duplicate_repositories_are_rejected_case_insensitively(self):
        duplicate=copy.deepcopy(self.catalog['projects'][0])
        duplicate['id']='duplicate'
        duplicate['repo']=duplicate['repo'].upper().replace('HTTPS://GITHUB.COM','https://github.com')
        self.catalog['projects'].append(duplicate)
        with self.assertRaises(AssertionError):validate(self.catalog)

    def test_missing_data_requirements_are_rejected(self):
        self.catalog['projects'][0]['data_note']=''
        with self.assertRaises(AssertionError):validate(self.catalog)

    def test_unsubstantiated_progress_field_is_rejected(self):
        self.catalog['projects'][0]['completion']=100
        with self.assertRaises(AssertionError):validate(self.catalog)

    def test_generated_catalog_preserves_every_source(self):
        text=markdown(self.catalog['projects'])
        for p in self.catalog['projects']:self.assertIn(']('+p['repo']+')',text)

    def test_generated_art_is_deterministic_and_self_contained(self):
        for p in self.catalog['projects']:
            svg=make_art(p)
            self.assertEqual(svg,make_art(p))
            self.assertNotIn('href=',svg)
            self.assertNotIn('<script',svg)


if __name__=='__main__':unittest.main()
