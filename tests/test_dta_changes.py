import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dta_changes


class DtaChangeTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.source=self.root/'datasets'/'raw'/'one.dta';self.source.parent.mkdir(parents=True)
        self.source.write_bytes(b'original file')
    def tearDown(self): self.tmp.cleanup()
    def apply_change(self,data,columns):
        candidate=self.source.parent/'candidate.dta';candidate.write_bytes(data)
        record,directory=dta_changes.create_backup(self.root,self.source,columns)
        return dta_changes.commit_drop(self.root,self.source,candidate,record,directory)
    def test_delete_and_multiple_undo_restore_exact_bytes(self):
        self.apply_change(b'after first',['a']);self.apply_change(b'after second',['b'])
        self.assertEqual(dta_changes.undo(self.root,self.source)['columns'],['b'])
        self.assertEqual(self.source.read_bytes(),b'after first')
        self.assertEqual(dta_changes.undo(self.root,self.source)['columns'],['a'])
        self.assertEqual(self.source.read_bytes(),b'original file')
        with self.assertRaisesRegex(ValueError,'没有可回滚'):dta_changes.undo(self.root,self.source)
    def test_external_changes_are_not_overwritten(self):
        self.apply_change(b'after first',['a']);self.source.write_bytes(b'external edit')
        with self.assertRaisesRegex(ValueError,'其他修改'):dta_changes.undo(self.root,self.source)
        self.assertEqual(self.source.read_bytes(),b'external edit')
    def test_invalid_fields_and_files_are_rejected(self):
        for fields in ([],['a','a'],['missing'],['a','b'],['a;drop']):
            with self.subTest(fields=fields),self.assertRaises(ValueError):dta_changes.validate_columns(['a','b'],fields)
        outside=self.root/'outside.dta';outside.write_bytes(b'data')
        with self.assertRaises(ValueError):dta_changes.checked_target(self.root,outside)
    def test_changed_source_after_backup_is_not_replaced(self):
        record,directory=dta_changes.create_backup(self.root,self.source,['a'])
        candidate=self.source.parent/'candidate.dta';candidate.write_bytes(b'new')
        self.source.write_bytes(b'changed externally')
        with self.assertRaisesRegex(ValueError,'其他操作修改'):
            dta_changes.commit_drop(self.root,self.source,candidate,record,directory)
        self.assertEqual(self.source.read_bytes(),b'changed externally')


if __name__=='__main__':unittest.main()
