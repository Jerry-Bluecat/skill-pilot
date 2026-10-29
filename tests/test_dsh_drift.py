import unittest
from unittest.mock import patch

from tests import test_operations
from skill_pilot import codex_config, operations, store
from skill_pilot.sync import visibility


class DshDriftTests(unittest.TestCase):
    setUp = test_operations.OperationsTests.setUp
    skill = test_operations.OperationsTests.skill
    assign = test_operations.OperationsTests.assign
    fingerprint = test_operations.OperationsTests.fingerprint

    def external_link(self):
        path = self.home / '.dsh/skills/grilling'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.symlink_to(self.home / '.skill-pilot/store/grilling', target_is_directory=True)
        return path

    def test_withdraw_preserves_unrelated_external_skill_and_disabled_settings(self):
        self.withdraw(False)

    def test_dashboard_withdraw_preserves_external_skill_and_disabled_settings(self):
        self.withdraw(True)

    def withdraw(self, recheck):
        self.assign('other', 'dsh')
        external = self.external_link()
        config = self.home / '.codex/config.toml'
        original = config.read_bytes()
        before = self.fingerprint()
        changes = [{'skill': 'other', 'agent': 'dsh', 'enabled': False}]
        review = operations.preview_assign(changes, self.home, recheck=recheck)
        result = operations.apply_assign(changes, expected=review.get('revision'), confirmed=True, home=self.home, recheck=recheck)
        self.assertNotIn('other', visibility(self.home)['dsh']['available'])
        self.assertIn('grilling', visibility(self.home)['dsh']['available'])
        self.assertTrue(external.is_symlink())
        self.assertEqual(config.read_bytes(), original)
        operations.undo(result['id'], home=self.home)
        self.assertEqual(self.fingerprint(), before)

    def test_real_sync_failure_still_rolls_back(self):
        self.external_link()
        before = self.fingerprint()
        with patch.object(operations, 'reconcile_assignments'):
            with self.assertRaisesRegex(ValueError, '实际技能名单'):
                self.assign('other', 'dsh')
        self.assertEqual(self.fingerprint(), before)

    def test_array_table_disables_survive_assignment_and_withdrawal(self):
        config = self.home / '.codex/config.toml'
        original = b'# keep\r\n[[skills.config]]\r\nname = "plugin:original"\r\nenabled = false\r\n[other]\r\nvalue = "keep"\r\n'
        config.write_bytes(original)
        self.assign('other', 'codex', False)
        result = self.assign('other', 'dsh')
        self.assertNotIn('other', visibility(self.home)['codex']['available'])
        self.assertIn('other', visibility(self.home)['dsh']['available'])
        self.assertTrue(config.read_bytes().startswith(original))
        changes = [{'skill': 'other', 'agent': 'dsh', 'enabled': False}]
        review = operations.preview_assign(changes, self.home, recheck=True)
        self.assertEqual(review['conflicts'], [])
        removed = operations.apply_assign(changes, review['revision'], True, self.home, recheck=True)
        self.assertNotIn('other', visibility(self.home)['dsh']['available'])
        operations.undo(removed['id'], home=self.home)
        operations.undo(result['id'], home=self.home)
        self.assertEqual(config.read_bytes(), original)

    def test_array_table_owned_edits_are_still_protected(self):
        original = b'[[skills.config]]\nname="user"\nenabled=false\n'
        changed, owner = codex_config.render(original, {}, ['one', 'two'])
        restored, _ = codex_config.render(changed, owner, [])
        self.assertEqual(restored, original)
        with self.assertRaisesRegex(ValueError, '外部改过'):
            codex_config.render(changed.replace(b'name = "one"', b'name = "edited"'), owner, [])
