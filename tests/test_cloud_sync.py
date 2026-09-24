from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.cloud_sync import CloudStore, collect, recipients, send_pending, validate_alert_config
from app.email_smoke import main as email_smoke


ITEM = {
    "external_id": "bll:sample",
    "source": "BLL",
    "municipality_code": "2928604",
    "municipality": "Santo Amaro",
    "title": "Link dedicado em fibra",
    "description": "Link dedicado em fibra",
    "score": 80,
    "status": "aberta",
}
DESTINATIONS = {
    ("email", "one@example.com"), ("email", "two@example.com"),
    ("whatsapp", "5575000000001"), ("whatsapp", "5575000000002"),
}


class FakeStore:
    def __init__(self, notified_at=None, alert_baselined_at=None):
        self.notified_at = notified_at
        self.alert_baselined_at = alert_baselined_at
        self.logged = []
        self.marked = []
        self.baselined = []
        self.delivered = set()
        self.finished = None

    def start_run(self):
        return 1

    def upsert(self, item):
        return "inserted", {**item, "id": 12, "notified_at": self.notified_at, "alert_baselined_at": self.alert_baselined_at}

    def log_notification(self, opportunity_id, result):
        self.logged.append((opportunity_id, result))

    def mark_notified(self, opportunity_id):
        self.marked.append(opportunity_id)

    def mark_baselined(self, opportunity_id):
        self.baselined.append(opportunity_id)

    def delivered_recipients(self, opportunity_id):
        return self.delivered

    def finish_run(self, run_id, status, totals, detail=""):
        self.finished = (run_id, status, totals, detail)


class CloudSyncTests(unittest.TestCase):
    def test_email_smoke_sends_only_to_configured_emails(self):
        with patch("app.email_smoke.enabled_channels", return_value={"email"}), \
                patch("app.email_smoke.validate_alert_config"), \
                patch("app.email_smoke.recipients", return_value={
                    ("email", "one@example.com"), ("email", "two@example.com"),
                }), \
                patch("app.email_smoke.send_email", return_value={"status": "sent"}) as email, \
                patch("builtins.print"):
            email_smoke()
        self.assertEqual(email.call_count, 2)
        self.assertTrue(all(call.kwargs["subject"].startswith("TESTE") for call in email.call_args_list))

    def test_email_only_config_ignores_whatsapp(self):
        configured = SimpleNamespace(
            email_to="one@example.com,two@example.com",
            whatsapp_numbers="5575000000001,5575000000002",
            smtp_host="mail.example.com",
            smtp_from="",
            smtp_user="alerts@example.com",
            smtp_password="test-password",
            evolution_api_url="",
            evolution_instance="",
            evolution_api_key="",
        )
        with patch.dict(os.environ, {"RADAR_NOTIFICATION_CHANNELS": "email"}), patch("app.cloud_sync.settings", configured):
            self.assertEqual(recipients(), {
                ("email", "one@example.com"),
                ("email", "two@example.com"),
            })
            validate_alert_config()

    def test_invalid_notification_channel_is_rejected(self):
        with patch.dict(os.environ, {"RADAR_NOTIFICATION_CHANNELS": "email,sms"}):
            with self.assertRaisesRegex(RuntimeError, "canais de alerta válidos"):
                recipients()

    def test_email_only_sends_separately_to_two_addresses(self):
        configured = SimpleNamespace(
            email_to="one@example.com,two@example.com",
            whatsapp_numbers="5575000000001,5575000000002",
        )
        with patch.dict(os.environ, {"RADAR_NOTIFICATION_CHANNELS": "email"}), \
                patch("app.cloud_sync.settings", configured), \
                patch("app.cloud_sync.send_email", return_value={"channel": "email", "status": "sent"}) as email, \
                patch("app.cloud_sync.send_whatsapp") as whatsapp:
            results = send_pending(ITEM, set())
        self.assertEqual(email.call_count, 2)
        whatsapp.assert_not_called()
        self.assertEqual({result["recipient"] for result in results}, {"one@example.com", "two@example.com"})

    def test_new_secret_key_is_not_used_as_bearer_token(self):
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SECRET_KEY": "sb_secret_test",
        }):
            store = CloudStore()
        self.assertEqual(store.session.headers["apikey"], "sb_secret_test")
        self.assertNotIn("Authorization", store.session.headers)

    def test_first_run_stores_without_sending_alerts_by_default(self):
        store = FakeStore()
        with patch.dict(os.environ, {"RADAR_NOTIFICATIONS_ENABLED": ""}):
            result = collect(store, fetcher=lambda: [ITEM], notifier=lambda item: self.fail("unexpected alert"))
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(store.logged, [])
        self.assertEqual(store.baselined, [12])
        self.assertEqual(store.finished[1], "success")

    def test_baselined_opportunity_is_not_emailed_later(self):
        store = FakeStore(alert_baselined_at="2026-09-24T10:00:00Z")
        with patch.dict(os.environ, {"RADAR_NOTIFICATIONS_ENABLED": "1", "RADAR_NOTIFICATION_CHANNELS": "email"}):
            collect(store, fetcher=lambda: [ITEM], notifier=lambda item, delivered: self.fail("unexpected alert"))
        self.assertEqual(store.logged, [])
        self.assertEqual(store.marked, [])

    def test_sends_only_once_for_eligible_opportunity(self):
        alerts = []
        def notifier(item, delivered):
            alerts.append(item)
            return [{"channel": channel, "recipient": recipient, "status": "sent"} for channel, recipient in DESTINATIONS]

        with patch.dict(os.environ, {"RADAR_NOTIFICATIONS_ENABLED": "1"}), patch("app.cloud_sync.recipients", return_value=DESTINATIONS):
            store = FakeStore()
            collect(store, fetcher=lambda: [ITEM], notifier=notifier)
            already_notified = FakeStore(notified_at="2026-09-24T10:00:00Z")
            collect(already_notified, fetcher=lambda: [ITEM], notifier=notifier)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]["id"], 0)
        self.assertEqual(store.marked, [12])
        self.assertEqual(len(store.logged), 4)
        self.assertEqual(already_notified.marked, [])

    def test_does_not_mark_partially_delivered_alert_as_complete(self):
        with patch.dict(os.environ, {"RADAR_NOTIFICATIONS_ENABLED": "1"}), patch("app.cloud_sync.recipients", return_value=DESTINATIONS):
            store = FakeStore()
            with self.assertRaisesRegex(RuntimeError, "Coleta incompleta"):
                collect(store, fetcher=lambda: [ITEM], notifier=lambda item, delivered: [
                    {"channel": "email", "recipient": "one@example.com", "status": "sent"},
                    {"channel": "email", "recipient": "two@example.com", "status": "sent"},
                    {"channel": "whatsapp", "recipient": "5575000000001", "status": "sent"},
                    {"channel": "whatsapp", "recipient": "5575000000002", "status": "error"},
                ])
        self.assertEqual(store.marked, [])
        self.assertEqual(len(store.logged), 4)
        self.assertEqual(store.finished[1], "partial")

    def test_retry_only_contacts_missing_destination(self):
        sent = []
        def fake_whatsapp(item, message, opportunity_id, numbers):
            sent.extend(numbers)
            return [{"channel": "whatsapp", "status": "sent"}]
        with patch("app.cloud_sync.recipients", return_value=DESTINATIONS), patch("app.cloud_sync.send_whatsapp", side_effect=fake_whatsapp), patch("app.cloud_sync.send_email") as email:
            results = send_pending(ITEM, DESTINATIONS - {("whatsapp", "5575000000002")})
        self.assertEqual(sent, ["5575000000002"])
        email.assert_not_called()
        self.assertEqual(results[0]["recipient"], "5575000000002")


if __name__ == "__main__":
    unittest.main()
