import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
import io
from server.benchmark import topic_ablation_review as r,weight_space as w


class ReviewTests(unittest.TestCase):
    def test_literal_signal_does_not_confuse_marker_removal_with_no_copy(self):
        for previous in ('準備はいいですか？','準備はいいですか。','（シエルから利用者への過去の質問）準備はいいですか？'):
            history=[dict(content=previous),dict(content='latest')]
            self.assertTrue(r.literal_question_reuse(history,'準備はいいですか？'))
            self.assertFalse(r.literal_question_reuse(history,'着手できる状態でしょうか？'))

    def test_binding_missing_and_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);report=root/'report.json';out=root/'review'
            trials=[dict(id=case,arm=arm,repeat=repeat,status='ok',messages=[dict(content='Ready?')])
                    for arm in ('base','candidate') for case in ('pending','needed-question') for repeat in (0,1)]
            w.write(report,dict(completion='complete',arms=['base','candidate'],trials=trials))
            r.prepare(report,out)
            cards=w.read(out/'cards.json');self.assertEqual(len(cards['cards']),2)
            with self.assertRaises(ValueError):r.score(report,out)
            for c in cards['cards']:
                c.update(unnecessary_question_spans=['Ready?'] if c['case']=='pending' else [],
                         old_execution_resume=False,latest_content_0_4=4,note='Reviewed')
            w.write(out/'cards.json',cards)
            with redirect_stdout(io.StringIO()):r.score(report,out)
            summary=w.read(out/'summary.json')
            self.assertEqual(summary['summary']['base']['unnecessary_question_replies'],2)
            self.assertEqual(len(summary['rows']),8)
            cards['cards'][0]['text']='modified'
            w.write(out/'cards.json',cards)
            with self.assertRaises(ValueError):r.score(report,out)
            report.write_text(report.read_text()+'\n')
            with self.assertRaises(ValueError):r.score(report,out)
