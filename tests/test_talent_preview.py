from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from PIL import Image
from scripts.talent_preview import verify_talent_preview,quantity
from scripts.named_count_model_assets import COUNT_MODEL_ASSETS,read_named_count_model_assets
from scripts.named_inventory import RAW_DETECTOR
from tests.talent_preview_fixture import packet,START,FINISH,BASE,rect,row

class TalentPreviewTests(unittest.TestCase):
    def verify(self,p):return verify_talent_preview(p,'芭芭拉','元素战技',START,FINISH)
    def split_runtime(self):
        temporary=tempfile.TemporaryDirectory(prefix='synthetic-talent-split-models-')
        self.addCleanup(temporary.cleanup);root=Path(temporary.name)
        config=root/'User/Config.json';config.parent.mkdir(parents=True)
        config.write_text(json.dumps({'otherConfig':{'ocrConfig':{'paddleOcrModelConfig':8}}}),encoding='utf-8')
        for name,path in [*COUNT_MODEL_ASSETS,('PpOcrDetV6',RAW_DETECTOR)]:
            asset=root/path;asset.parent.mkdir(parents=True,exist_ok=True);asset.write_bytes(('SYNTHETIC-MODEL-'+name).encode())
        models=read_named_count_model_assets(root);models['pinMethod']='actual_bundled_open_read_sha256_hold_session'
        data=(root/RAW_DETECTOR).read_bytes()
        proof={'loadMethod':'new_cpu_uncached_original_onnx_and_labels_under_read_pins','provider':'Cpu','rawModel':'V6','detectorModel':'V4',
            'countModels':models,'rawDetectorAsset':{'modelName':'PpOcrDetV6','relativePath':RAW_DETECTOR,'sha256':hashlib.sha256(data).hexdigest(),'length':len(data)}}
        return root,proof
    def modern_packet(self):
        root,proof=self.split_runtime();p=packet('芭芭拉');raw=p['nativeObservation']
        raw['costQuantityMethod']='pinned_v6_v4_slash_integer_split'
        for f in (f for f in raw['evidence']['rawFrames'] if 'materials' in f):
            f['costQuantityMethod']=raw['costQuantityMethod'];q=f['materials'][0]['quantity']
            q.update(slashPixelVerified=True,raw='3213',detectorRaw='3213',ocrRows=[],splitOcrScale=4,
                splitRegionMethod='slash_vertical_band',splitVerticalPaddingReference=6,slashBounds=rect(794,720,4,10),
                slashCorrelation=-.9,slashInkPixels=12,numeratorRegion=rect(754,714,39,22),denominatorRegion=rect(799,714,45,22),
                numeratorRaw='32',denominatorRaw='3',numeratorRows=[row('32',760,717,26,16)],denominatorRows=[row('3',810,717,18,16)],
                splitRawModel='V6',splitDetectorModel='V4',splitRawPaddleReadback=8,splitModelEvidence=deepcopy(proof))
        return p,root
    def verify_modern(self,p,root):
        return verify_talent_preview(p,'芭芭拉','元素战技',START,FINISH,trusted_runtime_root=root)
    def timed_packet(self):
        p,root=self.modern_packet();raw=p['nativeObservation'];raw['previewTimingMethod']='capture_read_evaluate_then_private_png_v1'
        previews=[f for f in raw['evidence']['rawFrames'] if 'materials' in f]
        for i,f in enumerate(previews):
            path=root/'log/synthetic-talent-preview-originals'/f'original-{i}.png';path.parent.mkdir(parents=True,exist_ok=True)
            with Image.new('RGB',(1920,1080),(20+i,30+i,40+i)) as image:
                image.save(path,format='PNG');pixels_hash=hashlib.sha256(image.tobytes('raw','BGR')).hexdigest()
            f['privateCapture']={'observedAt':f['observedAt'],'width':1920,'height':1080,'pixelType':'CV_8UC3',
                'path':str(path),'pngSha256':hashlib.sha256(path.read_bytes()).hexdigest(),'nativePixelsSha256':pixels_hash,
                'source':'diagnostic_only_lossless_native_srcmat_no_resize'}
            evaluated=previews[(i//2)*2+1]['observedAt']+100
            f['readTiming']={'captureCallStartedAt':f['observedAt']-5,'captureReturnedAt':f['observedAt'],
                'readerStartedAt':f['observedAt']+1,'readerCompletedAt':f['observedAt']+70,
                'pairEvaluatedAt':None if i%2==0 else evaluated,'pairAccepted':None if i%2==0 else True,
                'diagnosticPngCompletedAt':evaluated+200+(50 if i%2 else 0)}
        return p,root
    def timed_previews(self,p):return [f for f in p['nativeObservation']['evidence']['rawFrames'] if 'materials' in f]

    def source31_packet(self):
        p,root=self.timed_packet();raw=p['nativeObservation'];previews=self.timed_previews(p)
        proof=deepcopy(previews[0]['materials'][0]['quantity']['splitModelEvidence'])
        raw.update(previewMarkerMethod='whole_marker_required_roles_v1',tooltipQuantityMethod='existing_full_footer_v1',
            tooltipTimingMethod='capture_read_evaluate_then_private_png_v1')
        roles=(('attribute_heading','属性变更',(870,295,180,70)),('material_heading','所需材料',(870,575,180,60)),
            ('cancel_label','取消',(620,875,170,70)),('confirm_label','确认',(1170,875,180,70)))
        for f in previews:
            f.update(previewMarkerMethod=raw['previewMarkerMethod'],sourceRegionModelEvidence=deepcopy(proof))
            f['rows']=[row(text,x+10,y+10,100,30) for kind,text,(x,y,w,h) in roles]
            f['rows'] += [row('匿名完整背景',600,400,100,25),row('匿名截断背景',419,470,100,25)]
            background=[]
            for i in (4,5):
                b=f['rows'][i]['bounds'];m=(b['x']-420,1520-b['x']-b['width'],b['y']-235,985-b['y']-b['height'])
                background.append(dict(wholeRowIndex=i,insideWholeSource=min(m)>=0,leftMargin=m[0],rightMargin=m[1],topMargin=m[2],bottomMargin=m[3],claimsTitleOrInputEvidence=False))
            f['markerRoleEvidence']={'method':raw['previewMarkerMethod'],'wholeRegion':deepcopy(f['markerRegion']),
                'roles':[dict(role=kind,region=rect(x,y,w,h),wholeRowIndex=i,observedAt=f['observedAt'],rawText=text,
                    detectorRows=[row(text,x+12,y+12,90,28)]) for i,(kind,text,(x,y,w,h)) in enumerate(roles)],'backgroundRows':background}
        tips=[f for f in raw['evidence']['rawFrames'] if 'footerLabelRows' in f]
        for i,f in enumerate(tips):
            # Two explicit independent synthetic name readings for the stronger protocol.
            f.update(alternateNameRows=deepcopy(f['nameRows']),alternateRawName=f['rawName'],
                alternateNameScale=4,alternateNamePreprocessing='gray_threshold_210_inverse_cubic_4x')
            initial=deepcopy(f['quantity']);initial.update(complete=False,owned=None,required=None)
            initial['ocrRows']=[row('培养需求32/99',884,897,182,40)]
            f['quantity']['bounds']=rect(725,890,470,65);f['quantity']['ocrRows']=deepcopy(f['footerLabelRows'])
            f.update(tooltipQuantityMethod=raw['tooltipQuantityMethod'],sourceRegionModelEvidence=deepcopy(proof),
                footerQuantityEvidence=dict(method=raw['tooltipQuantityMethod'],oldRegion=rect(885,890,295,65),sourceRegion=rect(725,890,470,65),
                    initialReading=initial,initialWholeRawText='培养需求32/99',initialWholeDetectorText='培养需求32/99',
                    wholeRawText='培养需求32/99',wholeDetectorText='培养需求32/99'))
            path=root/'log/synthetic-talent-preview-originals'/f'tooltip-{i}.png'
            with Image.new('RGB',(1920,1080),(70+i,80+i,90+i)) as image:
                image.save(path,format='PNG');pixels_hash=hashlib.sha256(image.tobytes('raw','BGR')).hexdigest()
            f['privateCapture']=dict(observedAt=f['observedAt'],width=1920,height=1080,pixelType='CV_8UC3',path=str(path),
                pngSha256=hashlib.sha256(path.read_bytes()).hexdigest(),nativePixelsSha256=pixels_hash,source='diagnostic_only_lossless_native_srcmat_no_resize')
            f['readTiming']=dict(captureCallStartedAt=f['observedAt']-5,captureReturnedAt=f['observedAt'],readerStartedAt=f['observedAt'],
                readerCompletedAt=f['observedAt']+30,pairEvaluatedAt=None if i==0 else BASE+2450,
                diagnosticPngCompletedAt=BASE+2490+i*20,pairAccepted=None if i==0 else True)
        return p,root

    def source31_tips(self,p):return [f for f in p['nativeObservation']['evidence']['rawFrames'] if 'footerLabelRows' in f]

    def marker36_packet(self):
        p,root=self.source31_packet();raw=p['nativeObservation'];raw['previewMarkerMethod']='whole_marker_required_roles_v2'
        for f in self.timed_previews(p):
            f['previewMarkerMethod']=raw['previewMarkerMethod'];proof=f['markerRoleEvidence'];proof['method']=raw['previewMarkerMethod']
            material=proof['roles'][1];proof['legacyMaterialHeading']=deepcopy(material)
            proof['legacyMaterialHeading']['rawText']='所需材料C'
            proof['legacyMaterialHeading']['detectorRows'].append(row('C',1030,592,10,20))
            material['region']=rect(885,575,135,60)
            material['detectorRows']=[row('所需材料',906,589,100,28)]
            f['rows'][1]['bounds']=rect(900,585,100,30)
        return p,root

    def footer37_packet(self,complete_original=False):
        p,root=self.marker36_packet();raw=p['nativeObservation'];raw['tooltipQuantityMethod']='existing_full_footer_v2'
        for tip in self.source31_tips(p):
            proof=tip['footerQuantityEvidence'];original=deepcopy(tip['quantity'])
            original.update(complete=complete_original,owned=32 if complete_original else None,required=99 if complete_original else None,
                raw='32/99' if complete_original else '32/9?',detectorRaw='32/99' if complete_original else '32/99C')
            original['ocrRows']=[row('培养需求32/99' if complete_original else '培养需求32/99C',884,917,182,28)]
            proof.update(method=raw['tooltipQuantityMethod'],sourceRegion=rect(882,875,223,80),originalWholeReading=original,
                originalWholeRawText='培养需求32/99' if complete_original else '培养需求32/9?',
                originalWholeDetectorText='培养需求32/99' if complete_original else '培养需求32/99C')
            tip.update(tooltipQuantityMethod=raw['tooltipQuantityMethod'],footerLabelRegion=deepcopy(proof['sourceRegion']))
            tip['quantity'].update(bounds=deepcopy(proof['sourceRegion']),ocrRows=[row('培养需求32/99',884,917,182,28)])
            tip['footerLabelRows']=deepcopy(tip['quantity']['ocrRows'])
            tip['originalIdentityReading']=dict(observedAt=tip['observedAt'],nameRegion=deepcopy(tip['nameRegion']),alternateRawName='破旧的刀谭',
                alternateNameRows=[row('破旧的刀谭',740,180,160,30)],alternateNameScale=4,
                alternateNamePreprocessing='gray_threshold_210_inverse_cubic_4x',sourceRegion=rect(730,690,460,65),sourceRows=[row('来源',740,690,70,25)])
            tip.update(alternateNamePreprocessing='bgr_cubic_4x',sourceRegion=rect(730,675,460,80),sourceRows=[row('来源',740,690,70,25)])
        return p,root

    def test_identity37_accepts_new_bgr_name_source_and_preserves_failed_bounded_originals(self):
        p,root=self.footer37_packet();before=deepcopy(p)
        self.assertTrue(self.verify_modern(p,root));self.assertEqual(p,before)
        self.source31_tips(p)[0]['originalIdentityReading'].update(alternateNameRows=[],sourceRows=[])
        self.assertTrue(self.verify_modern(p,root))

    def test_identity37_exact_diagnostic_fields_clock_method_rois_and_bounded_image_rows(self):
        p,root=self.footer37_packet()
        fields=('observedAt','nameRegion','alternateRawName','alternateNameRows','alternateNameScale','alternateNamePreprocessing','sourceRegion','sourceRows')
        changes=[lambda t:t.pop('originalIdentityReading'),lambda t:t.update(originalIdentityReading=None)]
        changes += [lambda t,key=key:t['originalIdentityReading'].pop(key) for key in fields]
        changes += [lambda t:t['originalIdentityReading'].update(observedAt=t['observedAt']+1),lambda t:t['originalIdentityReading'].update(observedAt=True),
            lambda t:t['originalIdentityReading'].update(extra='forged'),lambda t:t['originalIdentityReading']['nameRegion'].update(x=731),
            lambda t:t['originalIdentityReading']['sourceRegion'].update(y=675),lambda t:t['originalIdentityReading'].update(alternateNamePreprocessing='bgr_cubic_4x'),
            lambda t:t['originalIdentityReading'].update(alternateNameScale=1),lambda t:t['originalIdentityReading'].update(alternateRawName='a'*257),
            lambda t:t['originalIdentityReading']['alternateNameRows'][0].update(text='a'*257),
            lambda t:t['originalIdentityReading'].update(sourceRows=[deepcopy(t['originalIdentityReading']['sourceRows'][0]) for i in range(17)]),
            lambda t:t['originalIdentityReading']['alternateNameRows'][0]['bounds'].update(x=-1),lambda t:t['originalIdentityReading']['sourceRows'][0]['bounds'].update(x=1900)]
        for index,change in enumerate(changes):
            with self.subTest(change=index):
                q=deepcopy(p);change(self.source31_tips(q)[0])
                with self.assertRaises(ValueError):self.verify_modern(q,root)
        v1,v1root=self.source31_packet()
        for value in (None,self.source31_tips(p)[0]['originalIdentityReading']):
            q=deepcopy(v1);self.source31_tips(q)[0]['originalIdentityReading']=value
            with self.assertRaises(ValueError):self.verify_modern(q,v1root)

    def test_identity37_new_name_source_wrong_text_method_roi_and_four_edge_margins(self):
        p,root=self.footer37_packet()
        def wrong_both(t):t['alternateRawName']='破旧的刀谭';t['alternateNameRows'][0]['text']='破旧的刀谭'
        changes=(lambda t:t.update(alternateNamePreprocessing='gray_threshold_210_inverse_cubic_4x'),lambda t:t['sourceRegion'].update(y=690),
            lambda t:t.update(alternateRawName='破旧的刀谭'),wrong_both,lambda t:t['nameRows'][0].update(text='破旧的刀谭'),
            lambda t:t['sourceRows'][0].update(text='来原'),lambda t:t['sourceRows'].append(deepcopy(t['sourceRows'][0])))
        for index,change in enumerate(changes):
            with self.subTest(change=index):
                q=deepcopy(p);change(self.source31_tips(q)[0])
                with self.assertRaises(ValueError):self.verify_modern(q,root)
        for member in ('alternateNameRows','sourceRows'):
            for axis in ('left','right','top','bottom'):
                for edge in (2,1):
                    with self.subTest(member=member,axis=axis,edge=edge):
                        q=deepcopy(p);tip=self.source31_tips(q)[0];box=tip['sourceRegion'] if member=='sourceRows' else tip['nameRegion'];r=tip[member][0]['bounds']
                        if axis=='left':r['x']=box['x']+edge
                        if axis=='right':r['x']=box['x']+box['width']-r['width']-edge
                        if axis=='top':r['y']=box['y']+edge
                        if axis=='bottom':r['y']=box['y']+box['height']-r['height']-edge
                        if edge==2:self.assertTrue(self.verify_modern(q,root))
                        else:
                            with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_footer37_preserves_failed_and_complete_original_diagnostics_and_aggregate(self):
        for complete in (False,True):
            with self.subTest(complete=complete):
                p,root=self.footer37_packet(complete);before=deepcopy(p)
                self.assertTrue(self.verify_modern(p,root));self.assertEqual(p,before)
                self.assertEqual(p['costs']['materials'][0]['required'],3)
                self.assertEqual(self.source31_tips(p)[0]['quantity']['required'],99)

    def test_footer37_three_diagnostics_mandatory_for_v2_and_forbidden_for_v1(self):
        p,root=self.footer37_packet();v1,v1root=self.source31_packet()
        for field in ('originalWholeReading','originalWholeRawText','originalWholeDetectorText'):
            with self.subTest(field=field):
                q=deepcopy(p);self.source31_tips(q)[0]['footerQuantityEvidence'].pop(field)
                with self.assertRaises(ValueError):self.verify_modern(q,root)
                q=deepcopy(v1);self.source31_tips(q)[0]['footerQuantityEvidence'][field]=None
                with self.assertRaises(ValueError):self.verify_modern(q,v1root)

    def test_footer37_original_scope_raw_rows_and_failed_values_cannot_be_changed(self):
        p,root=self.footer37_packet()
        changes=(lambda d:d.update(originalWholeReading=None),lambda d:d['originalWholeReading'].update(observedAt=d['originalWholeReading']['observedAt']+1),
            lambda d:d['originalWholeReading'].update(width=1919),lambda d:d['originalWholeReading']['bounds'].update(x=726),
            lambda d:d['originalWholeReading']['bounds'].update(height=80),lambda d:d['originalWholeReading'].update(cropMethod='detector_full_count_row'),
            lambda d:d['originalWholeReading'].update(initialReading={}),lambda d:d['originalWholeReading'].update(sourceCountRow={}),
            lambda d:d['originalWholeReading'].update(slashPixelVerified=True),lambda d:d['originalWholeReading'].update(slashBounds=rect(900,917,2,20)),
            lambda d:d['originalWholeReading'].update(splitRawModel='V6'),lambda d:d['originalWholeReading'].update(raw='32/99'),
            lambda d:d['originalWholeReading'].update(detectorRaw='32/9?'),lambda d:d.update(originalWholeDetectorText='培养需求32/99'),
            lambda d:d['originalWholeReading'].update(owned=32),lambda d:d['originalWholeReading'].update(required=99),
            lambda d:d['originalWholeReading']['ocrRows'][0]['bounds'].update(width=0))
        for index,change in enumerate(changes):
            with self.subTest(change=index):
                q=deepcopy(p);change(self.source31_tips(q)[0]['footerQuantityEvidence'])
                with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_footer37_fixed_new_roi_complete_original_prefix_and_ratio_conflicts_reject(self):
        p,root=self.footer37_packet(True)
        def change_prefix(t):
            d=t['footerQuantityEvidence'];d.update(originalWholeRawText='培养需32/99',originalWholeDetectorText='培养需32/99')
            d['originalWholeReading'].update(raw='',detectorRaw='');d['originalWholeReading']['ocrRows'][0]['text']='培养需32/99'
        def change_owned(t):
            d=t['footerQuantityEvidence'];d.update(originalWholeRawText='培养需求33/99',originalWholeDetectorText='培养需求33/99')
            d['originalWholeReading'].update(raw='33/99',detectorRaw='33/99',owned=33);d['originalWholeReading']['ocrRows'][0]['text']='培养需求33/99'
        def change_required(t):
            d=t['footerQuantityEvidence'];d.update(originalWholeRawText='培养需求32/98',originalWholeDetectorText='培养需求32/98')
            d['originalWholeReading'].update(raw='32/98',detectorRaw='32/98',required=98);d['originalWholeReading']['ocrRows'][0]['text']='培养需求32/98'
        changes=(lambda t:t['footerQuantityEvidence']['sourceRegion'].update(x=885),lambda t:t['quantity']['bounds'].update(width=220),
            lambda t:t['footerLabelRegion'].update(y=890),change_prefix,change_owned,
            lambda t:t['footerQuantityEvidence']['originalWholeReading']['ocrRows'].append(deepcopy(t['footerQuantityEvidence']['originalWholeReading']['ocrRows'][0])),
            change_required)
        for index,change in enumerate(changes):
            with self.subTest(change=index):
                q=deepcopy(p);change(self.source31_tips(q)[0])
                with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_footer37_two_pixel_edges_pass_one_pixel_fails_for_final_and_complete_diagnostics(self):
        p,root=self.footer37_packet(True)
        for member in ('quantity','originalWholeReading','initialReading'):
            for axis in ('left','right','top','bottom'):
                for edge in (2,1):
                    with self.subTest(member=member,axis=axis,edge=edge):
                        q=deepcopy(p);tip=self.source31_tips(q)[0];proof=tip['footerQuantityEvidence']
                        if member=='initialReading':
                            proof['initialReading'].update(complete=True,owned=32,required=99,ocrRows=[row('培养需求32/99',900,900,182,28)])
                        reading=tip['quantity'] if member=='quantity' else proof[member];box=reading['bounds'];r=reading['ocrRows'][0]['bounds']
                        if axis=='left':r['x']=box['x']+edge
                        if axis=='right':r['x']=box['x']+box['width']-r['width']-edge
                        if axis=='top':r['y']=box['y']+edge
                        if axis=='bottom':r['y']=box['y']+box['height']-r['height']-edge
                        if member=='quantity':tip['footerLabelRows']=deepcopy(reading['ocrRows'])
                        if edge==2:self.assertTrue(self.verify_modern(q,root))
                        else:
                            with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_footer37_envelope_frame_pair_and_proof_versions_cannot_mix(self):
        p,root=self.footer37_packet();old,_=self.source31_packet()
        def replace_first(raw):
            target=self.source31_tips({'nativeObservation':raw})[0];source=self.source31_tips(old)[0]
            for key in ('tooltipQuantityMethod','footerQuantityEvidence','quantity','footerLabelRows','footerLabelRegion'):target[key]=deepcopy(source[key])
        changes=(lambda r:r.update(tooltipQuantityMethod='existing_full_footer_v1'),
            lambda r:self.source31_tips({'nativeObservation':r})[0].update(tooltipQuantityMethod='existing_full_footer_v1'),
            lambda r:self.source31_tips({'nativeObservation':r})[0]['footerQuantityEvidence'].update(method='existing_full_footer_v1'),
            lambda r:self.source31_tips({'nativeObservation':r})[1].update(tooltipQuantityMethod='existing_full_footer_v1'),replace_first)
        for index,change in enumerate(changes):
            with self.subTest(change=index):
                q=deepcopy(p);change(q['nativeObservation'])
                with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_footer37_actual_timing_hash_and_model_proofs_remain_required(self):
        p,root=self.footer37_packet()
        changes=(lambda t:t['readTiming'].update(pairEvaluatedAt=t['observedAt']+1501),
            lambda t:t['sourceRegionModelEvidence']['rawDetectorAsset'].update(sha256='0'*64),
            lambda t:t['readTiming'].update(captureReturnedAt=t['observedAt']+1),lambda t:t['privateCapture'].update(nativePixelsSha256='short'))
        for index,change in enumerate(changes):
            with self.subTest(change=index):
                q=deepcopy(p);change(self.source31_tips(q)[1])
                with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_marker36_narrow_material_accepts_with_failed_old_diagnostic(self):
        p,root=self.marker36_packet();before=deepcopy(p)
        self.assertTrue(self.verify_modern(p,root));self.assertEqual(p,before)

    def test_marker36_method_roi_and_diagnostic_field_cannot_downgrade(self):
        changes=(lambda r:r['markerRoleEvidence'].pop('legacyMaterialHeading'),
                 lambda r:r['markerRoleEvidence'].update(legacyMaterialHeading=None),
                 lambda r:r['markerRoleEvidence']['roles'][1]['region'].update(x=870),
                 lambda r:r.update(previewMarkerMethod='whole_marker_required_roles_v1'),
                 lambda r:r['markerRoleEvidence']['roles'][1].update(rawText='所需材料C'),
                 lambda r:r['markerRoleEvidence']['roles'][1]['detectorRows'].append(row('C',1008,590,8,18)))
        for change in changes:
            with self.subTest(change=changes.index(change)):
                p,root=self.marker36_packet();change(self.timed_previews(p)[0])
                with self.assertRaises(ValueError):self.verify_modern(p,root)
        p,root=self.marker36_packet();p['nativeObservation']['previewMarkerMethod']='whole_marker_required_roles_v1'
        with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_marker36_old_diagnostic_geometry_row_and_frame_association(self):
        changes=(lambda d:d.update(role='confirm_label'),lambda d:d['region'].update(x=885),
                 lambda d:d.update(wholeRowIndex=0),lambda d:d.update(observedAt=d['observedAt']+1),
                 lambda d:d['detectorRows'][0]['bounds'].update(x=869),
                 lambda d:d['detectorRows'].append(row('C',1049,590,2,18)))
        for change in changes:
            with self.subTest(change=changes.index(change)):
                p,root=self.marker36_packet();change(self.timed_previews(p)[0]['markerRoleEvidence']['legacyMaterialHeading'])
                with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_marker36_two_pixel_margins_for_whole_and_narrow_detector_rows(self):
        for member in ('whole','detector'):
            for edge in (2,1):
                with self.subTest(member=member,edge=edge):
                    p,root=self.marker36_packet();f=self.timed_previews(p)[0]
                    box=(f['rows'][1] if member=='whole' else f['markerRoleEvidence']['roles'][1]['detectorRows'][0])['bounds']
                    box.update(x=885+edge,width=100)
                    if edge==2:self.assertTrue(self.verify_modern(p,root))
                    else:
                        with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_source31_reserved_payload_and_frame_proofs_cannot_downgrade(self):
        for key in ('previewMarkerMethod','tooltipQuantityMethod','tooltipTimingMethod','sourceRegionModelEvidence','markerRoleEvidence','footerQuantityEvidence'):
            for placement in ('payload','frame'):
                with self.subTest(field=key,placement=placement):
                    p=packet('芭芭拉');target=p['nativeObservation'] if placement=='payload' else p['nativeObservation']['evidence']['rawFrames'][-1]
                    target[key]=False
                    with self.assertRaises(ValueError):verify_talent_preview(p,'芭芭拉','元素战技',START,FINISH)

    def test_source31_rejects_zero_area_original_role_background_and_failed_initial_rows(self):
        p,root=self.source31_packet()
        for kind in ('mandatory','background','role','failed_initial'):
            for axis in ('width','height'):
                with self.subTest(kind=kind,axis=axis):
                    q=deepcopy(p);preview=self.timed_previews(q)[0]
                    if kind=='mandatory':preview['rows'][0]['bounds'][axis]=0
                    elif kind=='role':preview['markerRoleEvidence']['roles'][0]['detectorRows'][0]['bounds'][axis]=0
                    elif kind=='failed_initial':self.source31_tips(q)[0]['footerQuantityEvidence']['initialReading']['ocrRows'][0]['bounds'][axis]=0
                    else:
                        preview['rows'][4]['bounds'][axis]=0;b=preview['rows'][4]['bounds'];d=preview['markerRoleEvidence']['backgroundRows'][0]
                        d.update(rightMargin=1520-b['x']-b['width'],bottomMargin=985-b['y']-b['height'])
                    with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_source31_whole_footer_forbids_slash_geometry_and_complete_initial_clipped_edges(self):
        p,root=self.source31_packet()
        for member in ('quantity','initial'):
            for key,value in (('slashBounds',{'x':900,'y':900,'width':4,'height':10}),('numeratorRegion',{'x':900,'y':900,'width':20,'height':20}),
                    ('denominatorRegion',{'x':930,'y':900,'width':20,'height':20}),('splitRegionMethod','slash_vertical_band')):
                q=deepcopy(p);tip=self.source31_tips(q)[0];reading=tip['quantity'] if member=='quantity' else tip['footerQuantityEvidence']['initialReading']
                reading[key]=value
                with self.assertRaises(ValueError):self.verify_modern(q,root)
        for edge in ('top','bottom'):
            for margin in (1,2):
                q=deepcopy(p);tip=self.source31_tips(q)[0];initial=tip['footerQuantityEvidence']['initialReading']
                initial.update(complete=True,owned=32,required=99)
                initial['ocrRows'][0]['bounds'].update(x=900,y=890+margin if edge=='top' else 955-20-margin,width=180,height=20)
                if margin==2:self.assertTrue(self.verify_modern(q,root))
                else:
                    with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_source31_complete_fixed_footer_roles_and_real_pngs_preserve_failed_initial_and_aggregate(self):
        p,root=self.source31_packet();before=deepcopy(p)
        self.assertTrue(self.verify_modern(p,root));self.assertEqual(p,before)
        self.assertEqual(p['costs']['materials'][0]['required'],3)
        self.assertEqual(self.source31_tips(p)[0]['quantity']['required'],99)
        self.assertIsNone(self.source31_tips(p)[0]['footerQuantityEvidence']['initialReading']['owned'])
        self.assertEqual(self.timed_previews(p)[0]['rows'][-1]['bounds']['x'],419)
        self.assertFalse(p['nativeObservation']['confirmationSubmitted']);self.assertEqual(p['completedUpgrades'],0)

    def test_source31_partial_payload_and_any_frame_claim_cannot_downgrade(self):
        p,root=self.source31_packet()
        changes=[lambda r:r.pop('previewMarkerMethod'),lambda r:r.update(tooltipQuantityMethod=None),lambda r:r.update(tooltipTimingMethod='legacy'),
            lambda r:self.timed_previews({'nativeObservation':r})[0].update(markerRoleEvidence=None),
            lambda r:self.source31_tips({'nativeObservation':r})[0].update(footerQuantityEvidence=None),
            lambda r:self.source31_tips({'nativeObservation':r})[0].update(sourceRegionModelEvidence=None)]
        for change in changes:
            q=deepcopy(p);change(q['nativeObservation'])
            with self.assertRaises(ValueError):self.verify_modern(q,root)
        for key in ('previewMarkerMethod','tooltipQuantityMethod','sourceRegionModelEvidence','markerRoleEvidence','footerQuantityEvidence'):
            q=packet('芭芭拉');q['nativeObservation']['evidence']['rawFrames'][0][key]=False
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify(q)

    def test_source31_marker_exhaustive_signed_background_rows_never_claim_title_or_input(self):
        p,root=self.source31_packet()
        for change in (lambda f:f['markerRoleEvidence']['backgroundRows'].pop(),lambda f:f['markerRoleEvidence']['backgroundRows'].reverse(),
                lambda f:f['markerRoleEvidence']['backgroundRows'][1].update(insideWholeSource=True),
                lambda f:f['markerRoleEvidence']['backgroundRows'][1].update(leftMargin=0),
                lambda f:f['markerRoleEvidence']['backgroundRows'][0].update(claimsTitleOrInputEvidence=True),
                lambda f:f['markerRoleEvidence']['backgroundRows'][0].update(wholeRowIndex=True)):
            q=deepcopy(p);change(self.timed_previews(q)[0])
            with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_source31_roles_reject_duplicate_swapped_misplaced_or_clipped_mandatory_source(self):
        p,root=self.source31_packet()
        changes=(lambda f:f['rows'].append(deepcopy(f['rows'][0])),lambda f:f['rows'][0]['bounds'].update(x=419),
            lambda f:f['rows'][2].update(text='确认'),lambda f:f['markerRoleEvidence']['roles'][0].update(wholeRowIndex=True),
            lambda f:f['markerRoleEvidence']['roles'][0]['region'].update(x=871),
            lambda f:f['markerRoleEvidence']['roles'][0].update(observedAt=f['observedAt']+1),
            lambda f:f['markerRoleEvidence']['roles'][0].update(rawText='属性'),
            lambda f:f['markerRoleEvidence']['roles'][0]['detectorRows'][0]['bounds'].update(x=871),
            lambda f:f['markerRoleEvidence']['roles'][0]['detectorRows'].append(deepcopy(f['markerRoleEvidence']['roles'][0]['detectorRows'][0])))
        for change in changes:
            q=deepcopy(p);change(self.timed_previews(q)[0])
            with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_source31_source_rectangles_require_actual_ints_and_consistent_native_derived_fields(self):
        p,root=self.source31_packet()
        for value in (True,870.0,'870'):
            q=deepcopy(p);self.timed_previews(q)[0]['markerRoleEvidence']['roles'][0]['region']['x']=value
            with self.assertRaises(ValueError):self.verify_modern(q,root)
        q=deepcopy(p);box=self.timed_previews(q)[0]['markerRoleEvidence']['roles'][0]['region']
        box.update(top=295,bottom=365,left=870,right=1050,location=dict(x=870,y=295),size=dict(width=180,height=70),topLeft=dict(x=870,y=295),bottomRight=dict(x=1050,y=365))
        self.assertTrue(self.verify_modern(q,root));box['bottom']=364
        with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_source31_two_pixel_role_and_footer_boundaries_remain_exact(self):
        p,root=self.source31_packet()
        for edge in (1,2):
            q=deepcopy(p);self.timed_previews(q)[0]['markerRoleEvidence']['roles'][0]['detectorRows'][0]['bounds'].update(x=870+edge)
            if edge==2:self.assertTrue(self.verify_modern(q,root))
            else:
                with self.assertRaises(ValueError):self.verify_modern(q,root)
            q=deepcopy(p);tip=self.source31_tips(q)[0];tip['quantity']['ocrRows'][0]['bounds'].update(y=890+edge,height=40)
            tip['footerLabelRows']=deepcopy(tip['quantity']['ocrRows'])
            if edge==2:self.assertTrue(self.verify_modern(q,root))
            else:
                with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_source31_footer_eight_fields_and_fixed_actual_source_geometry_are_required(self):
        p,root=self.source31_packet()
        for key in ('method','oldRegion','sourceRegion','initialReading','initialWholeRawText','initialWholeDetectorText','wholeRawText','wholeDetectorText'):
            q=deepcopy(p);self.source31_tips(q)[0]['footerQuantityEvidence'].pop(key)
            with self.subTest(key=key),self.assertRaises(ValueError):self.verify_modern(q,root)
        for change in (lambda t:t['footerQuantityEvidence']['oldRegion'].update(x=884),lambda t:t['quantity']['bounds'].update(x=877,width=311),
                lambda t:t['footerQuantityEvidence']['initialReading'].update(observedAt=t['observedAt']+1),
                lambda t:t['footerQuantityEvidence']['initialReading'].update(owned=32),lambda t:t['footerQuantityEvidence']['sourceRegion'].update(width=True)):
            q=deepcopy(p);change(self.source31_tips(q)[0])
            with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_source31_whole_prefix_ambiguity_repair_extra_rows_and_split_proof_borrowing_reject(self):
        p,root=self.source31_packet()
        for change in (lambda t:t['footerQuantityEvidence'].update(wholeRawText='32/99'),
                lambda t:t['footerQuantityEvidence'].update(wholeRawText='培养需求培养需求32/99'),
                lambda t:t['footerQuantityEvidence'].update(wholeDetectorText='培养需求32/98'),
                lambda t:t['quantity']['ocrRows'].append(deepcopy(t['quantity']['ocrRows'][0])),
                lambda t:t['quantity'].update(splitRawModel='V6'),lambda t:t['quantity']['ocrRows'][0].update(text='培养需32/99')):
            q=deepcopy(p);change(self.source31_tips(q)[0])
            with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_source31_complete_initial_conflict_rejects_while_failed_initial_raw_never_becomes_owned(self):
        p,root=self.source31_packet();t=self.source31_tips(p)[0];i=t['footerQuantityEvidence']['initialReading']
        i.update(complete=True,owned=33,required=99,raw='33/99',detectorRaw='33/99');i['ocrRows']=[row('培养需求33/99',893,897,180,40)]
        t['footerQuantityEvidence'].update(initialWholeRawText='培养需求33/99',initialWholeDetectorText='培养需求33/99')
        with self.assertRaisesRegex(ValueError,'conflicts'):self.verify_modern(p,root)

    def test_source31_same_six_asset_scope_and_actual_bytes_cannot_be_borrowed_or_changed(self):
        p,root=self.source31_packet();q=deepcopy(p);self.source31_tips(q)[0]['sourceRegionModelEvidence']['rawDetectorAsset']['sha256']='0'*64
        with self.assertRaises(ValueError):self.verify_modern(q,root)
        (root/RAW_DETECTOR).write_bytes(b'SYNTHETIC-ALTERED-SOURCE-MODEL')
        with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_source31_tooltip_timings_png_order_originals_and_cross_kind_path_reuse_reject(self):
        p,root=self.source31_packet()
        for change in (lambda t:t.update(readTiming=None),lambda t:t['readTiming'].update(pairAccepted=False),
                lambda t:t['readTiming'].update(pairEvaluatedAt=t['observedAt']+1501),
                lambda t:t['readTiming'].update(readerStartedAt=True),
                lambda t:t['readTiming'].update(diagnosticPngCompletedAt=BASE+2700)):
            q=deepcopy(p);change(self.source31_tips(q)[1])
            with self.assertRaises(ValueError):self.verify_modern(q,root)
        q=deepcopy(p);tip=self.source31_tips(q)[0];tip['privateCapture']={**deepcopy(self.timed_previews(q)[0]['privateCapture']),'observedAt':tip['observedAt']}
        with self.assertRaisesRegex(ValueError,'reused'):self.verify_modern(q,root)
        q=deepcopy(p);tip=self.source31_tips(q)[0];Path(tip['privateCapture']['path']).write_bytes(b'SYNTHETIC-NOT-PNG')
        with self.assertRaises(ValueError):self.verify_modern(q,root)

    def test_source31_new_protocol_unknown_keeps_raw_null_costs_and_no_consumption(self):
        p,root=self.source31_packet();p['nativeObservation']['status']='unknown';p.update(evidenceVerified=False,costs=None);before=deepcopy(p)
        self.assertFalse(self.verify_modern(p,root));self.assertEqual(p,before)

    def test_source31_all_null_new_fields_keep_legacy_and_unmarked_clipped_rows_still_reject(self):
        p=packet('芭芭拉');raw=p['nativeObservation'];raw.update(previewMarkerMethod=None,tooltipQuantityMethod=None,tooltipTimingMethod=None)
        for f in raw['evidence']['rawFrames']:
            f.update(sourceRegionModelEvidence=None,markerRoleEvidence=None,footerQuantityEvidence=None)
        self.assertTrue(self.verify(p));self.timed_previews(p)[0]['rows'].append(row('匿名旧截断背景',419,400,90,25))
        with self.assertRaises(ValueError):self.verify(p)

    def test_timing29_real_synthetic_full_pngs_and_fixed_models_match_without_bitblt_or_consumer_claim(self):
        p,root=self.timed_packet();before=deepcopy(p)
        self.assertTrue(self.verify_modern(p,root));self.assertEqual(p,before)
        self.assertFalse(p['nativeObservation']['confirmationSubmitted']);self.assertEqual(p['completedUpgrades'],0)
        self.assertNotIn('actualCapture',self.timed_previews(p)[0]);self.assertNotIn('sessionAfterVerified',p['costs'])

    def test_timing29_all_null_fields_keep_only_legacy_readonly_compatibility(self):
        p=packet('芭芭拉');p['nativeObservation']['previewTimingMethod']=None
        for f in self.timed_previews(p):f['readTiming']=None
        self.assertTrue(self.verify(p));self.assertFalse(p['nativeObservation']['confirmationSubmitted'])

    def test_timing29_any_nonnull_timing_or_marker_requires_every_pair_without_downgrade(self):
        for mutate in (lambda raw:raw.pop('previewTimingMethod'),lambda raw:raw.update(previewTimingMethod=None),
                       lambda raw:raw.update(previewTimingMethod='legacy'),lambda raw:raw.update(previewTimingMethod=True),
                       lambda raw:self.timed_previews({'nativeObservation':raw})[0].update(readTiming=None),
                       lambda raw:self.timed_previews({'nativeObservation':raw})[-1].pop('readTiming')):
            p,root=self.timed_packet();mutate(p['nativeObservation'])
            with self.assertRaises(ValueError):self.verify_modern(p,root)
        p=packet('芭芭拉');p['nativeObservation']['previewTimingMethod']='capture_read_evaluate_then_private_png_v1'
        with self.assertRaises(ValueError):self.verify(p)

    def test_timing29_exact_dictionary_shape_actual_integers_and_first_null_second_true_are_required(self):
        fields=('captureCallStartedAt','captureReturnedAt','readerStartedAt','readerCompletedAt','pairEvaluatedAt','diagnosticPngCompletedAt','pairAccepted')
        for key in fields:
            for value in (None,True,False,{},1.5):
                if key=='pairAccepted' and value is True:continue
                p,root=self.timed_packet();self.timed_previews(p)[1]['readTiming'][key]=value
                with self.subTest(key=key,value=value),self.assertRaises(ValueError):self.verify_modern(p,root)
            p,root=self.timed_packet();self.timed_previews(p)[1]['readTiming'].pop(key)
            with self.assertRaises(ValueError):self.verify_modern(p,root)
        p,root=self.timed_packet();self.timed_previews(p)[0]['readTiming']['pairAccepted']=False
        with self.assertRaises(ValueError):self.verify_modern(p,root)
        p,root=self.timed_packet();self.timed_previews(p)[0]['readTiming']['pairEvaluatedAt']=BASE+1500
        with self.assertRaises(ValueError):self.verify_modern(p,root)
        p,root=self.timed_packet();self.timed_previews(p)[1]['readTiming']['syntheticNow']=BASE+1800
        with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_timing29_capture_reader_evaluation_and_two_png_write_order_cannot_be_rewritten(self):
        for mutate in (lambda a,b:a.update(captureCallStartedAt=a['captureReturnedAt']+1),
                       lambda a,b:a.update(readerStartedAt=a['captureReturnedAt']-1),
                       lambda a,b:a.update(readerCompletedAt=b['captureCallStartedAt']),
                       lambda a,b:b.update(pairEvaluatedAt=b['readerCompletedAt']-1),
                       lambda a,b:a.update(diagnosticPngCompletedAt=b['pairEvaluatedAt']-1),
                       lambda a,b:b.update(diagnosticPngCompletedAt=a['diagnosticPngCompletedAt']-1),
                       lambda a,b:a.update(captureCallStartedAt=BASE-1),
                       lambda a,b:b.update(diagnosticPngCompletedAt=BASE+4001),
                       lambda a,b:b.update(captureReturnedAt=b['captureReturnedAt']+1)):
            p,root=self.timed_packet();a,b=(f['readTiming'] for f in self.timed_previews(p)[:2]);mutate(a,b)
            with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_timing29_original_evaluation_freshness_accepts1500_and_rejects1501(self):
        for age in (1500,1501):
            p,root=self.timed_packet();previews=self.timed_previews(p);a,b=(f['readTiming'] for f in previews[-2:])
            b['pairEvaluatedAt']=previews[-1]['observedAt']+age;a['diagnosticPngCompletedAt']=b['pairEvaluatedAt']+1;b['diagnosticPngCompletedAt']=b['pairEvaluatedAt']+2
            for world,at in zip((f for f in p['nativeObservation']['evidence']['rawFrames'] if f.get('phase')=='world_restore'),(5000,5300)):
                world['observedAt']=BASE+at
            finish=datetime.fromtimestamp((BASE+6000)/1000,timezone.utc).isoformat()
            if age==1500:self.assertTrue(verify_talent_preview(p,'芭芭拉','元素战技',START,finish,trusted_runtime_root=root))
            else:
                with self.assertRaises(ValueError):verify_talent_preview(p,'芭芭拉','元素战技',START,finish,trusted_runtime_root=root)

    def test_timing29_pair_png_cannot_finish_after_next_tooltip_cleanup_or_next_preview_capture(self):
        for cleanup in (False,True):
            p,root=self.timed_packet();previews=self.timed_previews(p)
            second=previews[-1] if cleanup else previews[1]
            following=next(f for f in p['nativeObservation']['evidence']['rawFrames'] if f['observedAt']>second['observedAt'])
            second['readTiming']['diagnosticPngCompletedAt']=following['observedAt']+1
            with self.assertRaisesRegex(ValueError,'next original capture'):self.verify_modern(p,root)
        p,root=self.timed_packet();previews=self.timed_previews(p);frames=p['nativeObservation']['evidence']['rawFrames']
        # A later same-cost preview is the next real capture; its start predates its return.
        extra=[deepcopy(previews[2]),deepcopy(previews[3])]
        for f,at in zip(extra,(2080,2090)):
            f['observedAt']=BASE+at
            for q in (f['materials'][0]['quantity'],f['mora']):q['observedAt']=f['observedAt']
            f['privateCapture']['observedAt']=f['observedAt']
        extra[0]['readTiming'].update(captureCallStartedAt=BASE+2040,captureReturnedAt=BASE+2080,readerStartedAt=BASE+2080,readerCompletedAt=BASE+2081,
            diagnosticPngCompletedAt=BASE+2093)
        extra[1]['readTiming'].update(captureCallStartedAt=BASE+2085,captureReturnedAt=BASE+2090,readerStartedAt=BASE+2090,readerCompletedAt=BASE+2091,
            pairEvaluatedAt=BASE+2092,diagnosticPngCompletedAt=BASE+2094)
        insert=frames.index(previews[1])+1;frames[insert:insert]=extra
        with self.assertRaisesRegex(ValueError,'next original capture'):self.verify_modern(p,root)

    def test_timing29_requires_two_full_original_pngs_trusted_log_and_exact_observed_origin(self):
        for mutate in (lambda f:f.update(privateCapture=None),lambda f:f.pop('privateCapture'),
                       lambda f:f['privateCapture'].update(observedAt=f['observedAt']+1),
                       lambda f:f['privateCapture'].update(observedAt=True),lambda f:f['privateCapture'].update(pixelType='CV_8UC4'),
                       lambda f:f['privateCapture'].update(width=1280),lambda f:f['privateCapture'].update(width=1920.0),
                       lambda f:f['privateCapture'].update(source='actual_synchronous_BitBltCapture'),
                       lambda f:f['privateCapture'].update(pngSha256='0'*64),lambda f:f['privateCapture'].update(nativePixelsSha256='0'*64)):
            p,root=self.timed_packet();mutate(self.timed_previews(p)[0])
            with self.assertRaises(ValueError):self.verify_modern(p,root)
        p,root=self.timed_packet();f=self.timed_previews(p)[0];source=Path(f['privateCapture']['path']);outside=root/'state/foreign.png';outside.parent.mkdir();outside.write_bytes(source.read_bytes());f['privateCapture']['path']=str(outside)
        with self.assertRaisesRegex(ValueError,'trusted runtime log'):self.verify_modern(p,root)
        p,root=self.timed_packet()
        with self.assertRaisesRegex(ValueError,'trusted BetterGI runtime root'):self.verify(p)
        p,root=self.timed_packet();a,b=self.timed_previews(p)[:2];b['privateCapture']={**deepcopy(a['privateCapture']),'observedAt':b['observedAt']}
        with self.assertRaisesRegex(ValueError,'reused'):self.verify_modern(p,root)

    def test_timing29_actual_png_bytes_color_dimensions_and_pixel_hash_cannot_be_forged(self):
        for mode,size in (('RGBA',(1920,1080)),('RGB',(1280,720))):
            p,root=self.timed_packet();pixels=self.timed_previews(p)[0]['privateCapture'];path=Path(pixels['path'])
            with Image.new(mode,size) as image:image.save(path,format='PNG')
            pixels['pngSha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):self.verify_modern(p,root)
        p,root=self.timed_packet();pixels=self.timed_previews(p)[0]['privateCapture'];path=Path(pixels['path']);path.write_bytes(path.read_bytes()+b'changed')
        with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_timing29_png_pixel_changes_and_incomplete_stream_reject_even_with_new_file_hash(self):
        for change_pixels in (False,True):
            p,root=self.timed_packet();pixels=self.timed_previews(p)[0]['privateCapture'];path=Path(pixels['path'])
            if change_pixels:
                with Image.new('RGB',(1920,1080),(90,80,70)) as image:image.save(path,format='PNG')
            else:path.write_bytes(path.read_bytes()+b'synthetic-trailing-data')
            pixels['pngSha256']=hashlib.sha256(path.read_bytes()).hexdigest()
            with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_timing29_original_files_cannot_be_reused_through_hardlink_or_path_alias(self):
        for hardlink in (False,True):
            p,root=self.timed_packet();a,b=self.timed_previews(p)[:2]
            source=Path(a['privateCapture']['path'])
            if hardlink:
                alias=source.with_name('synthetic-hardlink.png');os.link(source,alias)
            else:alias=source.parent/'nested'/ '..'/source.name
            if not hardlink:(source.parent/'nested').mkdir()
            b['privateCapture']={**deepcopy(a['privateCapture']),'path':str(alias),'observedAt':b['observedAt']}
            with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_timing29_every_actual_asset_byte_is_rehashed_under_the_trusted_root(self):
        for unused,path in [*COUNT_MODEL_ASSETS,('PpOcrDetV6',RAW_DETECTOR)]:
            p,root=self.timed_packet();(root/path).write_bytes(b'SYNTHETIC-CHANGED-ASSET')
            with self.subTest(path=path),self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_timing29_mixed_second_and_millisecond_clocks_cannot_pass(self):
        p,root=self.timed_packet();self.timed_previews(p)[1]['readTiming']['readerStartedAt']//=1000
        with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_timing29_cannot_wrap_legacy_cost_method_or_drop_any_pinned_material_model(self):
        for mutate in (lambda raw:raw.update(costQuantityMethod='legacy_observed_ratio'),
                       lambda raw:self.timed_previews({'nativeObservation':raw})[0].update(costQuantityMethod='legacy_observed_ratio'),
                       lambda raw:self.timed_previews({'nativeObservation':raw})[0]['materials'][0]['quantity'].update(splitModelEvidence=None)):
            p,root=self.timed_packet();mutate(p['nativeObservation'])
            with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_timing29_unknown_packet_preserves_raw_and_new_timing_never_promotes_it_to_success(self):
        p,root=self.timed_packet();p.update(evidenceVerified=False,costs=None);p['nativeObservation']['status']='unknown';before=deepcopy(p)
        self.assertFalse(self.verify_modern(p,root));self.assertEqual(p,before)

    def test_modern26_pinned_split_independently_hashes_six_fixed_runtime_assets(self):
        p,root=self.modern_packet();before=deepcopy(p)
        self.assertTrue(self.verify_modern(p,root));self.assertEqual(p,before)
        self.assertFalse(p['nativeObservation']['confirmationSubmitted']);self.assertEqual(p['completedUpgrades'],0)

    def test_modern26_requires_trusted_root_and_rejects_other_runtime_bytes(self):
        p,root=self.modern_packet()
        with self.assertRaisesRegex(ValueError,'trusted BetterGI runtime root'):self.verify(p)
        other,unused=self.split_runtime();(other/COUNT_MODEL_ASSETS[0][1]).write_bytes(b'different actual model')
        with self.assertRaises(ValueError):self.verify_modern(p,other)

    def test_modern26_any_nonnull_metadata_requires_every_field_and_exact_readback(self):
        for key in ('splitRawModel','splitDetectorModel','splitModelEvidence','splitRawPaddleReadback'):
            for removal in (True,False):
                with self.subTest(key=key,removal=removal):
                    p,root=self.modern_packet();q=p['nativeObservation']['evidence']['preview']['materials'][0]['quantity']
                    if removal:q.pop(key)
                    else:q[key]=None
                    with self.assertRaises(ValueError):self.verify_modern(p,root)
        for change in ({'splitRawModel':'V4'},{'splitDetectorModel':'V6'},{'splitRawPaddleReadback':True},
                       {'splitRawPaddleReadback':8.0},{'splitRawPaddleReadback':7}):
            p,root=self.modern_packet();p['nativeObservation']['evidence']['preview']['materials'][0]['quantity'].update(change)
            with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_modern26_cannot_fall_back_to_whole_ratio_legacy_geometry_or_clipped_digits(self):
        for change in ({'slashPixelVerified':False},{'splitRegionMethod':None},{'splitRegionMethod':'legacy'},
                       {'splitOcrScale':3},{'splitVerticalPaddingReference':4},{'prefix':'培养需求'}):
            p,root=self.modern_packet();p['nativeObservation']['evidence']['preview']['materials'][0]['quantity'].update(change)
            with self.assertRaises(ValueError):self.verify_modern(p,root)
        p,root=self.modern_packet();p['nativeObservation']['evidence']['preview']['materials'][0]['quantity']['numeratorRows'][0]['bounds']['y']=715
        with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_modern26_payload_popup_marker_and_every_material_proof_must_agree(self):
        for mutate in (lambda raw:raw.pop('costQuantityMethod'),lambda raw:raw.update(costQuantityMethod='legacy_observed_ratio'),
                       lambda raw:raw['evidence']['preview'].pop('costQuantityMethod'),
                       lambda raw:raw['evidence']['preview']['materials'][0]['quantity'].update(splitRawModel=None,splitDetectorModel=None,splitModelEvidence=None,splitRawPaddleReadback=None)):
            p,root=self.modern_packet();mutate(p['nativeObservation'])
            with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_modern26_rejects_wrong_model_paths_versions_hash_shapes_or_missing_sixth_asset(self):
        for mutate in (lambda e:e.update(provider='Cuda'),lambda e:e.update(rawModel='V4'),lambda e:e.pop('rawDetectorAsset'),
                       lambda e:e['countModels'].update(rawPaddleConfig=True),lambda e:e['countModels'].update(fixedDetectorName='V6'),
                       lambda e:e['countModels']['assets'][0].update(relativePath='../actual.onnx'),
                       lambda e:e['countModels']['assets'][1].update(modelName='PpOcrRecV6'),
                       lambda e:e['countModels']['assets'][2].update(length=True),lambda e:e['countModels']['assets'][3].update(sha256='0'*63),
                       lambda e:e['rawDetectorAsset'].update(relativePath=COUNT_MODEL_ASSETS[0][1]),
                       lambda e:e['countModels']['assets'].append(deepcopy(e['rawDetectorAsset']))):
            p,root=self.modern_packet();mutate(p['nativeObservation']['evidence']['preview']['materials'][0]['quantity']['splitModelEvidence'])
            with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_modern26_every_actual_model_byte_config_and_hash_or_length_change_rejects(self):
        for name,path in [*COUNT_MODEL_ASSETS,('PpOcrDetV6',RAW_DETECTOR)]:
            with self.subTest(model=name):
                p,root=self.modern_packet();asset=root/path;original=asset.read_bytes();asset.write_bytes(b'X'+original[1:])
                with self.assertRaises(ValueError):self.verify_modern(p,root)
        p,root=self.modern_packet();(root/'User/Config.json').write_text(json.dumps({'otherConfig':{'ocrConfig':{'paddleOcrModelConfig':7}}}))
        with self.assertRaises(ValueError):self.verify_modern(p,root)
        for key,value in (('sha256','0'*64),('length',1)):
            p,root=self.modern_packet();p['nativeObservation']['evidence']['preview']['materials'][0]['quantity']['splitModelEvidence']['rawDetectorAsset'][key]=value
            with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_modern26_non_material_or_other_quantity_proof_cannot_borrow_model_attestation(self):
        p,root=self.modern_packet();raw=p['nativeObservation'];proof=deepcopy(raw['evidence']['preview']['materials'][0]['quantity']['splitModelEvidence'])
        raw['evidence']['preview']['mora'].update(splitRawModel='V6',splitDetectorModel='V4',splitModelEvidence=proof,splitRawPaddleReadback=8)
        with self.assertRaises(ValueError):self.verify_modern(p,root)
        p,root=self.modern_packet();p['nativeObservation']['evidence']['materialTooltips'][0][0]['quantity']['splitRawModel']='V6'
        with self.assertRaises(ValueError):self.verify_modern(p,root)
        p=self.variant17();p['nativeObservation']['evidence']['preview']['materials'][0]['quantity']['initialReading']['splitRawModel']='V6'
        with self.assertRaises(ValueError):self.verify(p)

    def test_modern26_all_null_metadata_is_legacy_readonly_compatibility_only(self):
        p=packet('芭芭拉');raw=p['nativeObservation'];raw['costQuantityMethod']='legacy_observed_ratio'
        for f in (f for f in raw['evidence']['rawFrames'] if 'materials' in f):
            f.update(costQuantityMethod='legacy_observed_ratio')
            for q in (f['materials'][0]['quantity'],f['mora']):q.update(splitRawModel=None,splitDetectorModel=None,splitModelEvidence=None,splitRawPaddleReadback=None)
        self.assertTrue(self.verify(p));self.assertFalse(raw['confirmationSubmitted']);self.assertEqual(p['completedUpgrades'],0)

    def test_modern26_all_materials_and_popup_frames_use_one_identical_model_proof(self):
        for second_material in (False,True):
            p,root=self.modern_packet();frames=[f for f in p['nativeObservation']['evidence']['rawFrames'] if 'materials' in f]
            f=frames[0] if second_material else frames[-1]
            if second_material:
                another=deepcopy(f['materials'][0]);another['name']='合成测试第二材料';f['materials'].append(another)
            f['materials'][-1]['quantity']['splitModelEvidence']['rawDetectorAsset']['sha256']='0'*64
            with self.assertRaisesRegex(ValueError,'model proofs must be identical'):self.verify_modern(p,root)

    def test_modern26_missing_null_or_nonobject_material_quantity_fails_closed(self):
        for value in (None,[],True,'native-summary'):
            p,root=self.modern_packet();p['nativeObservation']['evidence']['preview']['materials'][0]['quantity']=value
            with self.assertRaises(ValueError):self.verify_modern(p,root)
        p,root=self.modern_packet();p['nativeObservation']['evidence']['preview']['materials'][0].pop('quantity')
        with self.assertRaises(ValueError):self.verify_modern(p,root)

    def test_modern26_cultivation_passes_actual_trusted_runtime_root_and_byte_failure_stays_unknown(self):
        from scripts.cultivation import verify_cultivation_report
        from tests.test_cultivation import CultivationTests
        p,root=self.modern_packet();helper=CultivationTests();report=helper.report()
        report['target']['characterName']='芭芭拉'
        report.update(profile=None,inventory={},plan=None,requiredScanIds=[],manualInventoryIds=[],steps=[],
            metadata={'diagnostic':'talent-upgrade-preview-only'},talentPreview=p,startedAt=START,finishedAt=FINISH,
            policy={'originalResinBudget':0,'condensedResinBudget':0,'maxMinutes':3})
        path=root/'User/JsScript/AutoGameCultivation/record/test-run.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps(report,ensure_ascii=False),encoding='utf-8');archive=root/'logs/offline-run';archive.mkdir(parents=True)
        def check():return verify_cultivation_report(helper.event(),root,'test-run','scan',report['target'],archive,expected_talent_type='元素战技')
        with patch('scripts.talent_preview.verify_talent_preview',wraps=verify_talent_preview) as verifier:
            result=check();self.assertEqual(result['status'],'success',result['reason'])
            self.assertEqual(verifier.call_args.kwargs['trusted_runtime_root'],root.resolve())
        self.assertTrue(result['cultivation']['talentPreviewVerified']);self.assertEqual(result['cultivation']['completedUpgrades'],0)
        (root/RAW_DETECTOR).write_bytes(b'changed synthetic actual runtime bytes')
        result=check();self.assertEqual(result['status'],'unknown');self.assertIn('V6 detector',result['reason'])
    def variant17(self):
        p=packet('芭芭拉')
        for preview in (f for f in p['nativeObservation']['evidence']['rawFrames'] if 'materials' in f):
            preview.update(coinVariant='real_background_padding_8_reference_53',coinRegion=rect(845,791,53,53),
                initialCoinRegion=rect(853,799,37,37),initialCoinName='摩拉',initialCoinScore=.52)
            item=preview['materials'][0];initial=deepcopy(item['quantity']);initial.update(complete=False,owned=None,required=None,raw='3213')
            item.update(card=rect(741,602,116,146),iconRegion=rect(741,602,116,112))
            item['quantity'].update(bounds=rect(742,710,114,35),initialReading=initial,
                cropMethod='source_count_row_pad20x5_intersect_card',sourceCountRow=row('32/3',762,715,74,25))
            initial_mora=deepcopy(preview['mora']);initial_mora.update(complete=False,owned=None,required=None,raw='123456112500')
            source=deepcopy(initial_mora['ocrRows'][0])
            preview['mora'].update(bounds=rect(899,792,283,65),initialReading=initial_mora,
                cropMethod='unique_initial_detector_row_pad12',sourceCountRow=source)
        return p
    def entry19(self):
        p=packet('芭芭拉');raw=p['nativeObservation'];e=raw['evidence'];seen=set()
        def shift(value):
            if not isinstance(value,(dict,list)) or id(value) in seen:return
            seen.add(id(value))
            if isinstance(value,dict):
                if type(value.get('observedAt')) is int and value['observedAt']>=BASE+800:value['observedAt']+=1200
                for child in value.values():shift(child)
            else:
                for child in value:shift(child)
        shift(e);raw['observedAt']=datetime.fromtimestamp((BASE+4200)/1000,timezone.utc).isoformat()
        entries=[]
        for at in (800,1100,1400):
            character=deepcopy(e['characterIdentity'][0]);character['observedAt']=BASE+at
            candidates=[row('Lv.2',1600,220,70,25),row('Lv.1',1600,330,70,25),row('Lv.3',1600,440,70,25)]
            entries.append({'phase':'talent_entry_observation','observedAt':BASE+at,'width':1920,'height':1080,
                'focused':True,'overview':True,'promptVisible':False,'reviveVisible':False,'character':character,
                'region':rect(1536,0,384,900),'rows':deepcopy(candidates),'candidates':deepcopy(candidates),'failureReason':'verified_entries'})
        e['rawFrames'][3:3]=entries;e['twoPickedEntryFrames']=entries[:2];e['entryClickFrame']=entries[2]
        finish=datetime.fromtimestamp((BASE+5200)/1000,timezone.utc).isoformat()
        return p,finish
    def test_replacement_character_and_base1_next2_with_fixed_bonus_are_independently_verified(self):
        for bonus in (False,True):
            p=packet('芭芭拉',bonus=bonus);self.assertTrue(self.verify(p))
            self.assertEqual(p['costs']['materials'][0]['required'],3)
            self.assertEqual(p['nativeObservation']['evidence']['materialTooltips'][0][0]['quantity']['required'],99)

    def rolling20(self):
        p,unused=self.entry19();raw=p['nativeObservation'];e=raw['evidence'];seen=set()
        def shift(value):
            if not isinstance(value,(dict,list)) or id(value) in seen:return
            seen.add(id(value))
            if isinstance(value,dict):
                if type(value.get('observedAt')) is int:value['observedAt']+=600
                for child in value.values():shift(child)
            else:
                for child in value:shift(child)
        shift(e)
        for n,at in zip(e['characterIdentity'],(400,700,1000)):
            n.update(observedAt=BASE+at,phase='character_identity_observation',nameRegion=rect(1420,110,360,68))
        bad=deepcopy(e['characterIdentity'][0]);bad.update(observedAt=BASE+100,name='芭芭拉。');bad['nameRows'][0]['text']='芭芭拉。'
        e['rawFrames'].insert(0,bad);e.update(characterIdentityMethod='bounded_rolling_exact_triple',characterIdentityObservationLimitMs=12000,
            characterIdentityPollMs=300,characterIdentityTrials=e['rawFrames'][:4])
        raw['observedAt']=datetime.fromtimestamp((BASE+4800)/1000,timezone.utc).isoformat()
        return p,datetime.fromtimestamp((BASE+5800)/1000,timezone.utc).isoformat()

    def test_rolling20_retains_bad_punctuation_and_accepts_only_first_consecutive_exact_final_triple(self):
        p,finish=self.rolling20();snapshot=deepcopy(p['nativeObservation'])
        self.assertTrue(verify_talent_preview(p,'芭芭拉','元素战技',START,finish))
        self.assertEqual(p['nativeObservation'],snapshot)
        self.assertEqual(p['nativeObservation']['evidence']['characterIdentityTrials'][0]['name'],'芭芭拉。')

    def global21(self):
        p,finish=self.rolling20();e=p['nativeObservation']['evidence'];e['talentEntryIdentitySource']='talent_global_header'
        for n in e['characterIdentityTrials']:n.update(nameSource='attribute_right_full_name',nameBoxMethod='actual_name_ocr_box')
        for f in (v for v in e['rawFrames'] if v.get('phase')=='talent_entry_observation'):
            n=f['character'];n.update(name='芭芭拉',nameSource='talent_global_header',nameBoxMethod='whole_header_ocr_box_contains_name',
                nameRegion=rect(130,20,320,85),nameRows=[row('水元素 / 芭芭拉',150,40,260,35)],headerRaw='水元素 / 芭芭拉',headerElement='水')
            f.update(menuRegion=rect(40,390,320,100),menuRows=[row('天赋',80,410,100,30)])
        return p,finish

    def test_global21_complete_current_header_derives_name_without_reusing_attribute_or_caller(self):
        p,finish=self.global21();snapshot=deepcopy(p['nativeObservation'])
        self.assertTrue(verify_talent_preview(p,'芭芭拉','元素战技',START,finish))
        self.assertEqual(p['nativeObservation'],snapshot)
        self.assertEqual(p['nativeObservation']['evidence']['characterIdentity'][0]['nameRegion'],rect(1420,110,360,68))

    def rolling_entry22(self):
        p,unused=self.global21();raw=p['nativeObservation'];e=raw['evidence'];seen=set()
        def shift(value):
            if not isinstance(value,(dict,list)) or id(value) in seen:return
            seen.add(id(value))
            if isinstance(value,dict):
                if type(value.get('observedAt')) is int and value['observedAt']>=BASE+2600:value['observedAt']+=1500
                for child in value.values():shift(child)
            else:
                for child in value:shift(child)
        shift(e);entries=[f for f in e['rawFrames'] if f.get('phase')=='talent_entry_observation']
        for f,at in zip(entries,(1400,1740,2080)):
            f.update(observedAt=BASE+at,readCompletedAt=BASE+at+40);f['character']['observedAt']=BASE+at
        more=[deepcopy(entries[1]) for i in range(3)]
        for f,at in zip(more,(2420,2760,3100)):
            f.update(observedAt=BASE+at,readCompletedAt=BASE+at+40);f['character']['observedAt']=BASE+at
        entries[2]['rows'][-1]['text']='Lv.';entries[2]['candidates'].pop();entries[2]['failureReason']='wrong_candidate_count'
        e['rawFrames'][7:7]=more;e['twoPickedEntryFrames']=more[:2];e['entryClickFrame']=more[2]
        e.update(talentEntryObservationMethod='bounded_contiguous_entry_triple',talentEntryObservationLimitMs=12000,talentEntryObservationPollMs=300)
        raw['observedAt']=datetime.fromtimestamp((BASE+6300)/1000,timezone.utc).isoformat()
        return p,datetime.fromtimestamp((BASE+7300)/1000,timezone.utc).isoformat()

    def test_rolling_entry22_retains_bad_third_and_clicks_first_later_complete_contiguous_triple(self):
        p,finish=self.rolling_entry22();snapshot=deepcopy(p['nativeObservation'])
        self.assertTrue(verify_talent_preview(p,'芭芭拉','元素战技',START,finish));self.assertEqual(p['nativeObservation'],snapshot)
        entries=[f for f in snapshot['evidence']['rawFrames'] if f.get('phase')=='talent_entry_observation']
        self.assertEqual(len(entries),6);self.assertEqual(entries[2]['rows'][-1]['text'],'Lv.');self.assertEqual(len(entries[2]['candidates']),2)

    def test_rolling_entry22_cannot_pick_old_pair_extend_deadline_or_continue_after_legal_triple_or_abort(self):
        def entries(e):return [f for f in e['rawFrames'] if f.get('phase')=='talent_entry_observation']
        for mutate in (lambda e:e.pop('talentEntryObservationMethod'),lambda e:e.update(talentEntryObservationLimitMs=15000),
            lambda e:e.update(talentEntryObservationPollMs=200),lambda e:e.update(twoPickedEntryFrames=entries(e)[:2]),
            lambda e:e['entryClickFrame'].pop('readCompletedAt'),lambda e:entries(e)[2].update(focused=False),
            lambda e:entries(e)[2].update(promptVisible=True),lambda e:entries(e)[2].update(reviveVisible=True),
            lambda e:entries(e)[2].update(readCompletedAt=BASE+2100,observedAt=BASE+2000),
            lambda e:e['entryClickFrame'].update(readCompletedAt=BASE+4800),
            lambda e:entries(e)[2].update(readCompletedAt=BASE+2079)):
            p,finish=self.rolling_entry22();mutate(p['nativeObservation']['evidence'])
            with self.assertRaises(ValueError):verify_talent_preview(p,'芭芭拉','元素战技',START,finish)
        p,finish=self.rolling_entry22();e=p['nativeObservation']['evidence'];bad=entries(e)[2]
        bad['rows'][-1]['text']='Lv.3';bad['candidates']=deepcopy(bad['rows'])
        with self.assertRaisesRegex(ValueError,'first legal'):verify_talent_preview(p,'芭芭拉','元素战技',START,finish)
        p,unused=self.rolling_entry22();e=p['nativeObservation']['evidence'];tail=entries(e)[-3:]
        for f,at in zip(tail,(BASE+12700,BASE+13040,BASE+13380)):
            f.update(observedAt=at,readCompletedAt=at+40);f['character']['observedAt']=at
        for f in e['rawFrames'][10:]:f['observedAt']+=12000
        with self.assertRaises(ValueError):verify_talent_preview(p,'芭芭拉','元素战技',START,datetime.fromtimestamp((BASE+20000)/1000,timezone.utc).isoformat())

    def test_global21_header_source_row_name_menu_geometry_and_attribute_substitution_reject(self):
        for mutate in (lambda e:e.pop('talentEntryIdentitySource'),lambda e:e.update(talentEntryIdentitySource='previous_attribute'),
            lambda e:e['entryClickFrame']['character'].update(nameSource='attribute_right_full_name'),
            lambda e:e['entryClickFrame']['character'].update(nameBoxMethod='substring_estimated_box'),
            lambda e:e['entryClickFrame']['character'].update(headerElement='火'),
            lambda e:e['entryClickFrame']['character'].update(headerRaw='水元素/芭芭拉'),
            lambda e:e['entryClickFrame']['character']['nameRows'][0].update(text='水元素 / 丽莎'),
            lambda e:e['entryClickFrame']['character']['nameRows'][0].update(text='水元素 / 芭芭拉。'),
            lambda e:e['entryClickFrame']['character']['nameRows'][0]['bounds'].update(x=131),
            lambda e:e['entryClickFrame']['character']['nameRows'][0]['bounds'].update(y=21),
            lambda e:e['entryClickFrame']['character']['nameRegion'].update(width=380),
            lambda e:e['entryClickFrame']['character']['nameRows'].append(row('Q',420,40,20,30)),
            lambda e:e['entryClickFrame'].pop('menuRows'),lambda e:e['entryClickFrame']['menuRows'][0].update(text='天赋详情'),
            lambda e:e['entryClickFrame']['menuRows'][0]['bounds'].update(x=41),lambda e:e['entryClickFrame']['menuRegion'].update(width=200),
            lambda e:e['entryClickFrame']['character'].update(observedAt=BASE+100),
            lambda e:e['characterIdentityTrials'][0].update(nameSource='talent_global_header'),
            lambda e:e['characterIdentityTrials'][0].update(nameBoxMethod='whole_header_ocr_box_contains_name')):
            p,finish=self.global21();mutate(p['nativeObservation']['evidence'])
            with self.assertRaises(ValueError):verify_talent_preview(p,'芭芭拉','元素战技',START,finish)
        for text in ('水元素｜芭芭拉','水元素/芭芭拉/额外','合成测试天赋','水元素/芭芭拉。'):
            p,finish=self.global21();n=p['nativeObservation']['evidence']['entryClickFrame']['character']
            n['headerRaw']=text;n['nameRows'][0]['text']=text
            with self.assertRaises(ValueError):verify_talent_preview(p,'芭芭拉','元素战技',START,finish)
        p,finish=self.global21();n=p['nativeObservation']['evidence']['entryClickFrame']['character']
        n.update(headerRaw='火元素 / 芭芭拉',headerElement='火');n['nameRows'][0]['text']=n['headerRaw']
        with self.assertRaisesRegex(ValueError,'changed between'):verify_talent_preview(p,'芭芭拉','元素战技',START,finish)

    def test_rolling20_method_reference_poll_raw_and_downgrade_forgery_reject(self):
        for mutate in (lambda e:e.pop('characterIdentityMethod'),lambda e:e.update(characterIdentityObservationLimitMs=15000),
            lambda e:e.update(characterIdentityPollMs=200),lambda e:e.pop('characterIdentityTrials'),
            lambda e:e.update(characterIdentityTrials=e['characterIdentity']),
            lambda e:e['characterIdentityTrials'][0].update(name='芭芭拉'),
            lambda e:e['characterIdentity'][0]['nameRows'][0]['bounds'].update(x=1421),
            lambda e:e['characterIdentityTrials'][0].update(observedAt=BASE+200),
            lambda e:e.update(characterIdentity=e['characterIdentityTrials'][:3]),
            lambda e:e['rawFrames'].pop(0),lambda e:e['characterIdentityTrials'][0].pop('phase'),
            lambda e:e.update(characterSelectionAfterIdentity=True)):
            p,finish=self.rolling20();mutate(p['nativeObservation']['evidence'])
            with self.assertRaises(ValueError):verify_talent_preview(p,'芭芭拉','元素战技',START,finish)
        p,finish=self.rolling20();e=p['nativeObservation']['evidence'];e['characterIdentityTrials'][0].update(name='芭芭拉');e['characterIdentityTrials'][0]['nameRows'][0]['text']='芭芭拉'
        with self.assertRaisesRegex(ValueError,'first verified'):verify_talent_preview(p,'芭芭拉','元素战技',START,finish)

    def test_wrong_target_type_or_claimed_completion_never_pass(self):
        for mutate in (lambda p:p['nativeObservation'].update(characterName='梦见月瑞希'),lambda p:p.update(selectedTalentType='元素爆发'),
            lambda p:p.update(completedUpgrades=1),lambda p:p['nativeObservation'].update(confirmationSubmitted=True),
            lambda p:p['nativeObservation'].update(currentBaseLevel=True),lambda p:p['nativeObservation'].pop('observedAt')):
            p=packet('芭芭拉');mutate(p)
            with self.assertRaises(ValueError):self.verify(p)

    def test_weak_mora_model_clipped_integer_duplicated_frame_partialname_and_wrong_owned_block(self):
        for mutate in (lambda r:r['evidence']['preview'].update(coinScore=.52),
            lambda r:r['evidence']['preview']['mora']['ocrRows'][0]['bounds'].update(x=903),
            lambda r:r['evidence']['rawFrames'][-1].update(observedAt=r['evidence']['rawFrames'][-2]['observedAt']),
            lambda r:r['evidence']['materialTooltips'][0][1]['nameRows'][0].update(text='自由'),
            lambda r:r['evidence']['materialTooltips'][0][1]['quantity'].update(owned=33)):
            p=packet('芭芭拉');mutate(p['nativeObservation'])
            with self.assertRaises(ValueError):self.verify(p)

    def test_bonus_color_conflict_and_tooltip_aggregate_requirement_cannot_be_next_cost(self):
        p=packet('芭芭拉',bonus=True);p['nativeObservation']['evidence']['detailIdentityCarryover']['bonusRaw']='天赋等级+2'
        with self.assertRaises(ValueError):self.verify(p)
        p=packet('芭芭拉');p['nativeObservation']['materials'][0]['required']=99
        with self.assertRaises(ValueError):self.verify(p)

    def test_known_geometric_slash_uses_complete_split_integers_without_rewriting_whole_ocr(self):
        q={'observedAt':BASE+1400,'width':1920,'height':1080,'bounds':rect(754,710,90,35),'complete':True,
            'owned':32,'required':3,'prefix':'','slashPixelVerified':True,'raw':'3213','detectorRaw':'3213','ocrRows':[],
            'splitOcrScale':4,'slashBounds':rect(794,720,4,10),'slashCorrelation':-.9,'slashInkPixels':12,
            'numeratorRegion':rect(754,710,39,35),'denominatorRegion':rect(799,710,45,35),
            'numeratorRaw':'32','denominatorRaw':'3','numeratorRows':[row('32',760,717,26,20)],'denominatorRows':[row('3',810,717,18,20)]}
        self.assertEqual(quantity(q,BASE,BASE+4000),(32,3))
        q['slashCorrelation']=0
        with self.assertRaises(ValueError):quantity(q,BASE,BASE+4000)

    def test_explicit_slash_glyph_band_rebuilds_regions_and_keeps_complete_four_edge_digits(self):
        q={'observedAt':BASE+1400,'width':1920,'height':1080,'bounds':rect(754,710,90,35),'complete':True,
            'owned':32,'required':3,'prefix':'','slashPixelVerified':True,'raw':'3213','detectorRaw':'3213','ocrRows':[],
            'splitOcrScale':4,'splitRegionMethod':'slash_vertical_band','splitVerticalPaddingReference':6,
            'slashBounds':rect(794,720,4,10),'slashCorrelation':-.9,'slashInkPixels':12,
            'numeratorRegion':rect(754,714,39,22),'denominatorRegion':rect(799,714,45,22),
            'numeratorRaw':'32','denominatorRaw':'3','numeratorRows':[row('32',760,717,26,16)],'denominatorRows':[row('3',810,717,18,16)]}
        self.assertEqual(quantity(q,BASE,BASE+4000),(32,3));self.assertEqual(q['raw'],'3213')
        for mutate in (lambda r:r.update(splitVerticalPaddingReference=4),lambda r:r.update(splitRegionMethod='auto_guess'),
            lambda r:r['numeratorRegion'].update(y=710,height=35),lambda r:r['numeratorRows'][0]['bounds'].update(y=715),
            lambda r:r['denominatorRows'][0].update(text='3万'),lambda r:r.update(slashCorrelation=-.74),
            lambda r:r.update(complete=False,owned=None,required=None)):
            bad=deepcopy(q);mutate(bad)
            with self.assertRaises(ValueError):quantity(bad,BASE,BASE+4000)
        p=packet('芭芭拉');p.update(evidenceVerified=False,costs=None)
        failed=deepcopy(q);failed.update(complete=False,owned=None,required=None,numeratorRaw='bad OCR')
        p['nativeObservation']['evidence']['preview']['materials'][0]['quantity']=failed
        self.assertFalse(self.verify(p));self.assertTrue(failed['slashPixelVerified']);self.assertEqual(failed['numeratorRaw'],'bad OCR')

    def test_unknown_preserves_all_raw_with_no_known_costs(self):
        p=packet('芭芭拉');p.update(evidenceVerified=False,costs=None)
        self.assertFalse(self.verify(p));self.assertTrue(p['nativeObservation']['evidence']['rawFrames'])
        p['costs']={'materials':[]}
        with self.assertRaises(ValueError):self.verify(p)

    def test_inspection15_fullname_roi_is_whitelisted_but_unknown_box_or_vertical_crop_is_not(self):
        p=packet('芭芭拉')
        for n in p['nativeObservation']['evidence']['characterIdentity']:n['nameRegion']=rect(1460,124,264,52)
        self.assertTrue(self.verify(p))
        p['nativeObservation']['evidence']['characterIdentity'][0]['nameRegion']['width']=300
        with self.assertRaises(ValueError):self.verify(p)
        p=packet('芭芭拉')
        p['nativeObservation']['evidence']['characterIdentity'][0]['nameRows'][0]['bounds']['y']=131
        with self.assertRaisesRegex(ValueError,'four ROI edges'):self.verify(p)

    def test_inspection16_fullname_roi_keeps_full_edge_identity_proof(self):
        p=packet('芭芭拉')
        for n in p['nativeObservation']['evidence']['characterIdentity']:n['nameRegion']=rect(1420,110,360,68)
        self.assertTrue(self.verify(p))
        p['nativeObservation']['evidence']['characterIdentity'][0]['nameRows'][0]['bounds']['x']=1421
        with self.assertRaises(ValueError):self.verify(p)

    def test_variant17_fixed_coin_and_actual_derived_boxes_preserve_initial_failure(self):
        p=self.variant17();self.assertTrue(self.verify(p))
        preview=p['nativeObservation']['evidence']['preview']
        self.assertIsNone(preview['mora']['initialReading']['owned'])
        self.assertEqual(preview['mora']['initialReading']['raw'],'123456112500')
        self.assertEqual(preview['materials'][0]['quantity']['initialReading']['raw'],'3213')
        self.assertEqual(p['costs']['mora']['required'],12500)

    def test_variant17_currency_conflict_no_max_selection_and_initial_row_or_crop_forgery_reject(self):
        for mutate in (lambda f:f.update(initialCoinName='原石',initialCoinScore=.95),
            lambda f:f.update(coinScore=.52,initialCoinScore=.99),lambda f:f.update(coinVariant='choose_highest_score'),
            lambda f:f['mora']['sourceCountRow']['bounds'].update(x=900),
            lambda f:f['mora']['initialReading']['ocrRows'][0]['bounds'].update(x=903),
            lambda f:f['mora']['initialReading'].update(observedAt=BASE),
            lambda f:f['mora']['bounds'].update(width=275),
            lambda f:f['mora']['ocrRows'][0]['bounds'].update(x=899),
            lambda f:f['materials'][0]['quantity']['bounds'].update(width=116),
            lambda f:f['materials'][0]['quantity'].update(cropMethod='unclamped_pad20'),
            lambda f:f['materials'][0]['quantity'].pop('initialReading'),lambda f:f['mora'].pop('initialReading')):
            p=self.variant17();mutate(p['nativeObservation']['evidence']['preview'])
            with self.assertRaises(ValueError):self.verify(p)

    def test_variant17_positive_primary_is_required_even_when_diagnostic_capture_is_present(self):
        p=self.variant17();preview=p['nativeObservation']['evidence']['preview']
        preview['privateCapture']={'source':'diagnostic_only_lossless_native_srcmat_no_resize','pngSha256':'0'*64}
        preview['coinScore']=.52
        with self.assertRaises(ValueError):self.verify(p)

    def test_explicit_entry19_pair_and_fresh_click_bind_requested_index_with_original_name_triple(self):
        p,finish=self.entry19();self.assertTrue(verify_talent_preview(p,'芭芭拉','元素战技',START,finish))
        self.assertEqual(len(p['nativeObservation']['evidence']['twoPickedEntryFrames']),2)

    def test_entry19_new_fields_cannot_downgrade_or_forge_rows_geometry_name_or_requested_index(self):
        for mutate in (lambda e:e.pop('twoPickedEntryFrames'),lambda e:e.update(twoPickedEntryFrames=[]),
            lambda e:e['entryClickFrame'].update(focused=False),lambda e:e['entryClickFrame'].update(promptVisible=True),
            lambda e:e['entryClickFrame']['character'].update(name='别的角色'),
            lambda e:e['entryClickFrame']['rows'][1].update(text='Lv.2'),
            lambda e:e['entryClickFrame']['candidates'][1]['bounds'].update(x=1537),
            lambda e:e['entryClickFrame']['candidates'][1]['bounds'].update(y=340),
            lambda e:e.update(entryClickFrame=deepcopy(e['twoPickedEntryFrames'][1])),
            lambda e:e['entryClickFrame']['region'].update(width=400),
            lambda e:e.update(characterIdentity=e['characterIdentity'][:2])):
            p,finish=self.entry19();mutate(p['nativeObservation']['evidence'])
            with self.assertRaises(ValueError):verify_talent_preview(p,'芭芭拉','元素战技',START,finish)

if __name__=='__main__':unittest.main()
