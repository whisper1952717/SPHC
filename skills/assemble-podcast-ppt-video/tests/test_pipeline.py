import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import build_slideshow_timeline as builder
import render_slideshow as renderer


class ExistingBehaviorTests(unittest.TestCase):
    def test_full_simplified_normalization(self):
        self.assertEqual(builder.normalized('關鍵資訊與採購預算'), '关键资讯与采购预算')

    def test_caption_never_breaks_key_information(self):
        rows = builder.split_captions('结果见面聊了一个小时气氛特别好出门一复盘才发现关键信息一个没拿到下一步也没约成。', 25)
        self.assertEqual(''.join(rows), '结果见面聊了一个小时气氛特别好出门一复盘才发现关键信息一个没拿到下一步也没约成。')
        self.assertFalse(any(a.endswith('关键') and b.startswith('信息') for a,b in zip(rows, rows[1:])))

    def test_semantic_override_preserves_text(self):
        self.assertEqual(builder.reviewed_captions('关键信息一个没拿到。', ['关键信息，', '一个没拿到。']), ['关键信息，', '一个没拿到。'])
        with self.assertRaises(ValueError):
            builder.reviewed_captions('关键信息一个没拿到。', ['改写内容。'])

    def test_render_limits_every_input_and_exact_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            rows = [{'file':'a.png','start':0,'end':6,'duration':6}, {'file':'b.png','start':6,'end':12,'duration':6}]
            cmd = renderer.build_command(p, p, rows, 'audio.wav', 'captions.ass', p/'result.mp4', .7, 8)
            for i, arg in enumerate(cmd):
                if arg == '-i':
                    self.assertIn('-threads', cmd[max(0,i-10):i])
            self.assertEqual(cmd[cmd.index('-t',cmd.index('-c:a'))+1], '12.000')
            self.assertNotIn('-shortest', cmd)


class GuardTests(unittest.TestCase):
    def setUp(self):
        import pipeline_common
        self.p = pipeline_common

    def test_cut_mapping_and_cross_cut_words(self):
        cuts = [[2,5],[9,13]]
        mapped = self.p.retime_transcript({'segments':[{'words':[{'start':4.8,'end':9.2,'word':'跨剪接'}]}]}, cuts)
        words = [w for s in mapped['segments'] for w in s['words']]
        self.assertEqual(words, [])
        self.assertAlmostEqual(self.p.source_to_edited(10,cuts),4)
        self.assertEqual(self.p.join_points(cuts),[3])
        self.assertAlmostEqual(self.p.edited_duration(cuts),7)

    def test_invalid_cuts_are_rejected(self):
        for cuts in ([[2,5],[4,6]], [[5,2]], [[-1,3]]):
            with self.assertRaises(ValueError):
                self.p.validate_intervals(cuts, 10)

    def test_long_missing_run_blocks_even_with_high_global_coverage(self):
        matches = {i:(i,i+.1) for i in range(1000) if not 100<=i<125}
        report = self.p.alignment_health(1000,matches,max_unmatched_run=20)
        self.assertGreater(report['coverage'],.95)
        self.assertFalse(report['passed'])

    def test_active_audio_missing_words_is_flagged_but_silence_is_not(self):
        samples = [0.0]*1000 + [.1,-.1]*1500 + [0.0]*1000
        rows = [{'words':[{'start':0,'end':.5,'word':'开头'}]}]
        report = self.p.coverage_health(samples,1000,rows,min_gap=2)
        self.assertFalse(report['passed'])
        self.assertTrue(report['uncovered_active_ranges'])
        self.assertTrue(self.p.coverage_health([0.0]*5000,1000,[],min_gap=2)['passed'])

    def test_small_internal_unmatched_run_is_allowed_but_opening_is_not(self):
        good = {i:(i,i+.1) for i in range(50) if not 20<=i<23}
        self.assertTrue(self.p.alignment_health(50,good)['passed'])
        head = {i:(i,i+.1) for i in range(50) if i>=8}
        self.assertFalse(self.p.alignment_health(50,head)['passed'])

    def test_hash_binding_rejects_stale_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'source'; f.write_text('old')
            record=self.p.file_record(f)
            self.p.verify_records([record])
            f.write_text('new')
            with self.assertRaises(ValueError):
                self.p.verify_records([record])

    def test_short_visual_states_are_rejected_not_delayed(self):
        starts=[0,3,9]
        with self.assertRaises(ValueError):
            self.p.validate_slide_timing(starts,16)
        self.assertEqual(starts,[0,3,9])

    def test_windows_and_wsl_paths_can_bind_same_file(self):
        import os
        if os.name!='nt':
            self.skipTest('Windows alias test')
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/'source';f.write_text('same')
            record=self.p.file_record(f)
            resolved=Path(record['path']).as_posix()
            record['path']='/mnt/'+resolved[0].lower()+'/'+resolved[3:]
            self.assertTrue(self.p.bound_to(f,[record]))

    def test_renderer_refuses_changed_sources_before_starting_ffmpeg(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'source';source.write_text('original')
            report={'passed':True,'sources':[self.p.file_record(source)],'outputs':[self.p.file_record(source)]}
            (root/'alignment_check.json').write_text(json.dumps(report))
            source.write_text('edited after check')
            with patch.object(sys,'argv',['render','--project',str(root),'--images',str(root),'--output','new.mp4']):
                with patch.object(renderer.subprocess,'run') as run:
                    with self.assertRaises(ValueError):
                        renderer.main()
                    run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
