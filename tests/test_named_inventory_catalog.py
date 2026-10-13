"""Anonymous temporary ItemV2 assets; no real runtime, inventory or model inference."""
import base64
from copy import deepcopy
import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from scripts.named_inventory_catalog import load_runtime_catalog,resolve_material,CSV_PATH,MODEL_PATH

HEADERS=['variant_id','item_class_id','item_name','material_type','quality_level','embedding']
EMBEDDING=base64.b64encode(b'\0'*16).decode()


class NamedInventoryCatalogTests(unittest.TestCase):
    def setUp(self):
        directory=tempfile.TemporaryDirectory(prefix='synthetic-named-inventory-');self.addCleanup(directory.cleanup);self.root=Path(directory.name)
        self.rows=[['1','material:104301','合成教导','角色天赋素材','2',EMBEDDING],
            ['2','material:112001','合成徽记','角色与武器培养素材','2',EMBEDDING],
            ['3','material:113021','合成溶媒','','4',EMBEDDING]]
        path=self.root/MODEL_PATH;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'synthetic-onnx-fingerprint-only')
        self.write()
    def write(self,headers=None,rows=None):
        stream=io.StringIO(newline='');writer=csv.writer(stream);writer.writerow(headers or HEADERS);writer.writerows(self.rows if rows is None else rows)
        (self.root/CSV_PATH).write_text(stream.getvalue(),encoding='utf-8',newline='')
    def test_exact_pairs_row_fingerprint_and_fixed_assets_resolve_without_exporting_embedding(self):
        catalog=load_runtime_catalog(self.root);item=resolve_material(catalog,{'materialId':'104301','materialName':'合成教导'})
        expected=hashlib.sha256(json.dumps(self.rows[0],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
        self.assertEqual(item['csvRow']['rowSha256'],expected);self.assertEqual(item['csvRow']['embeddingByteLength'],16)
        self.assertEqual(item['category'],'characterDevelopmentItems');self.assertNotIn('embedding',item['csvRow'])
        self.assertEqual(catalog['version']['csv']['relativePath'],CSV_PATH)
        self.assertEqual(catalog['version']['model']['sha256'],hashlib.sha256(b'synthetic-onnx-fingerprint-only').hexdigest())
        self.assertEqual(resolve_material(catalog,{'materialId':'113021','materialName':'合成溶媒'})['category'],'preciousItems')
    def test_global_cross_class_or_cross_id_names_reject_even_when_requested_row_matches(self):
        for item_class in ('weapon:90001','relic:123_4','material:112003'):
            extra=list(self.rows[0]);extra[0]='4';extra[1]=item_class;self.write(rows=self.rows+[extra])
            with self.assertRaisesRegex(ValueError,'ambiguous globally'):resolve_material(load_runtime_catalog(self.root),{'materialId':'104301','materialName':'合成教导'})
    def test_missing_pair_conflicting_tier_or_fake_quantity_and_category_cannot_admit_request(self):
        catalog=load_runtime_catalog(self.root)
        for pair in ({'materialId':'104302','materialName':'合成教导'},{'materialId':'104301','materialName':'错误教导'},
            {'materialId':'104301','materialName':'合成教导','owned':7},{'materialId':'104301','materialName':'合成教导','category':'preciousItems'},
            {'materialId':'202','materialName':'合成摩拉'},{'materialId':'101016','materialName':'合成溶媒'}):
            with self.assertRaises(ValueError):resolve_material(catalog,pair)
        extra=list(self.rows[0]);extra[0]='4';extra[4]='5';self.write(rows=self.rows+[extra])
        with self.assertRaises(ValueError):resolve_material(load_runtime_catalog(self.root),{'materialId':'104301','materialName':'合成教导'})
    def test_identical_class_metadata_variants_use_first_exact_row_but_empty_113_kind_is_not_weekly_classification(self):
        extra=list(self.rows[0]);extra[0]='4';self.write(rows=self.rows+[extra])
        self.assertEqual(resolve_material(load_runtime_catalog(self.root),{'materialId':'104301','materialName':'合成教导'})['csvRow']['variantId'],'1')
        row=['4','material:113060','合成材料','','5',EMBEDDING];self.write(rows=self.rows+[row])
        item=resolve_material(load_runtime_catalog(self.root),{'materialId':'113060','materialName':'合成材料'})
        self.assertEqual(item['purpose'],'developmentMaterialNamespace');self.assertNotIn('weekly',item['purpose'])
    def test_duplicate_columns_invalid_embedding_unsupported_kind_or_missing_assets_fail_closed(self):
        self.write(headers=HEADERS+['item_name'],rows=[self.rows[0]+['合成教导']])
        with self.assertRaises(ValueError):load_runtime_catalog(self.root)
        for value in ('bad base64!',base64.b64encode(b'123').decode(),''):
            rows=deepcopy(self.rows);rows[0][-1]=value;self.write(rows=rows)
            with self.assertRaises(ValueError):load_runtime_catalog(self.root)
        rows=deepcopy(self.rows);rows[0][3]='角色经验素材';self.write(rows=rows)
        with self.assertRaises(ValueError):resolve_material(load_runtime_catalog(self.root),{'materialId':'104301','materialName':'合成教导'})
        (self.root/MODEL_PATH).unlink()
        with self.assertRaises(OSError):load_runtime_catalog(self.root)


if __name__=='__main__':unittest.main()
