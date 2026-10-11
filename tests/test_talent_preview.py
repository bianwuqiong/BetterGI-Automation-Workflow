from copy import deepcopy
from datetime import datetime,timezone
import unittest
from scripts.talent_preview import verify_talent_preview,quantity
from tests.talent_preview_fixture import packet,START,FINISH,BASE,rect,row

class TalentPreviewTests(unittest.TestCase):
    def verify(self,p):return verify_talent_preview(p,'芭芭拉','元素战技',START,FINISH)
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
