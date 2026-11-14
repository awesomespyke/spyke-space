"""Offline regression tests: python -m unittest discover -s scripts -p test_transmission_edits.py"""
import tempfile
import unittest
from pathlib import Path
from album_journal import Journal
from transmission_edits import caption_block, replace_caption, EditableCaptionError

class CaptionTests(unittest.TestCase):
    def test_caption_update_keeps_media(self):
        body = caption_block(17, 'Original') + '\n\n![Transmission photograph](/transmissions/a.jpg)\n'
        changed = replace_caption(body, 17, 'Revised')
        self.assertIn('Revised', changed)
        self.assertNotIn('Original', changed)
        self.assertIn('/transmissions/a.jpg', changed)
        self.assertEqual(changed, replace_caption(changed, 17, 'Revised'))

    def test_album_only_changes_target(self):
        body = caption_block(17, 'First') + '\n\n' + caption_block(18, 'Second')
        changed = replace_caption(body, 18, 'Updated', is_album=True)
        self.assertIn('First', changed)
        self.assertNotIn('Second', changed)
        self.assertIn('Updated', changed)

    def test_legacy_album_refuses(self):
        with self.assertRaises(EditableCaptionError):
            replace_caption('First\n\nSecond', 18, 'Changed', is_album=True)

    def test_legacy_single_preserves_media(self):
        body = 'Old caption\n\n{{< transmission-audio src="/transmissions/a.ogg" >}}\n'
        changed = replace_caption(body, 7, 'New caption')
        self.assertIn('New caption', changed)
        self.assertIn('a.ogg', changed)
        self.assertNotIn('Old caption', changed)

    def test_empty_caption_keeps_marker(self):
        changed = replace_caption(caption_block(3, 'Something'), 3, '')
        self.assertIn('spyke-caption:3:start', changed)
        self.assertEqual(changed, replace_caption(changed, 3, ''))

    def test_edited_update_remains_single_in_journal(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = Journal(Path(directory) / 'journal.json')
            journal.ingest([{'update_id': 5, 'edited_message': {'message_id': 8, 'media_group_id': 'album1'}},
                            {'update_id': 6, 'message': {'message_id': 9, 'media_group_id': 'album1'}}], now=100)
            ready = journal.ready(now=120, quiet_seconds=10)
            self.assertEqual([len(x) for x in ready], [1, 1])

if __name__ == '__main__':
    unittest.main()
