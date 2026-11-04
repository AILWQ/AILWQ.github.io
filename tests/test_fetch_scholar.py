import json
import tempfile
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from scripts.fetch_scholar import SCHOLAR_ID, collect_metrics, fetch_page, parse_page, update_snapshot


def profile_page(ids=("paper1",), values=("273", "272", "9", "9", "9", "9"), more=False):
    cells = "".join(f'<td class="gsc_rsb_std">{value}</td>' for value in values)
    rows = "".join(
        f'<tr class="gsc_a_tr"><td><a class="gsc_a_at" '
        f'href="/citations?citation_for_view={SCHOLAR_ID}:{paper_id}">Paper</a></td></tr>'
        for paper_id in ids
    )
    disabled = "" if more else ' disabled=""'
    return (
        '<div id="gsc_prf_in">Wenqiang Li</div>'
        f'<table id="gsc_rsb_st"><tr>{cells}</tr></table>'
        f'<table><tbody id="gsc_a_b">{rows}</tbody></table>'
        f'<button id="gsc_bpf_more"{disabled}>Show more</button>'
    )


class ScholarTests(unittest.TestCase):
    def test_decodes_response_charset(self):
        headers = Message()
        headers["Content-Type"] = "text/html; charset=ISO-8859-1"
        response = Mock(headers=headers)
        response.read.return_value = "Scholar\u00a0profile".encode("iso-8859-1")
        with patch("scripts.fetch_scholar.urlopen") as open_url:
            open_url.return_value.__enter__.return_value = response
            self.assertEqual(fetch_page(0), "Scholar\u00a0profile")

    def test_uses_all_time_metrics(self):
        metrics, ids, more = parse_page(profile_page())
        self.assertEqual(metrics, {"citations": 273, "h_index": 9, "i10_index": 9})
        self.assertEqual(ids, [f"{SCHOLAR_ID}:paper1"])
        self.assertFalse(more)

    def test_number_separators_and_zero(self):
        for text in ("1,234", "1\u00a0234", "1\u202f234"):
            metrics, _, _ = parse_page(profile_page(values=(text, "1", "0", "0", "0", "0")))
            self.assertEqual(metrics["citations"], 1234)
            self.assertEqual(metrics["h_index"], 0)

    def test_counts_every_page(self):
        fetch = Mock(side_effect=[
            profile_page(ids=tuple(f"paper{i}" for i in range(100)), more=True),
            profile_page(ids=("paper100", "paper101")),
        ])
        snapshot = collect_metrics(fetch)
        self.assertEqual(snapshot["metrics"]["publications"], 102)
        self.assertEqual([call.args[0] for call in fetch.call_args_list], [0, 100])

    def test_rejects_blocked_changed_and_invalid_pages(self):
        pages = (
            '<html><h1>Sorry, unusual traffic</h1></html>',
            profile_page(values=("273",)),
            profile_page(values=("N/A", "0", "9", "0", "9", "0")),
            profile_page(ids=()),
            profile_page().replace(SCHOLAR_ID, "another-profile"),
            profile_page().replace('id="gsc_bpf_more"', 'id="changed"'),
        )
        for page in pages:
            with self.subTest(page=page), self.assertRaises(ValueError):
                collect_metrics(lambda start: page)

    def test_rejects_partial_or_duplicate_pages(self):
        with self.assertRaises(ValueError):
            collect_metrics(lambda start: profile_page(more=True))
        with self.assertRaises(ValueError):
            collect_metrics(lambda start: profile_page(ids=("same", "same")))
        fetch = Mock(side_effect=[
            profile_page(ids=tuple(f"paper{i}" for i in range(100)), more=True),
            profile_page(ids=("paper0",)),
        ])
        with self.assertRaises(ValueError):
            collect_metrics(fetch)

    def test_failed_update_preserves_previous_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "scholar.json"
            original = '{"existing": "snapshot"}\n'
            output.write_text(original)
            for error in (ValueError("Invalid page"), HTTPError("https://scholar.google.com", 429, "Limited", {}, None)):
                with self.subTest(error=error), self.assertRaises(type(error)):
                    update_snapshot(output, Mock(side_effect=error))
                self.assertEqual(output.read_text(), original)
                self.assertFalse(output.with_suffix(".tmp").exists())

    def test_success_writes_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data" / "scholar.json"
            update_snapshot(output, lambda start: profile_page(ids=("a", "b")))
            snapshot = json.loads(output.read_text())
            self.assertEqual(snapshot["scholar_id"], SCHOLAR_ID)
            self.assertEqual(snapshot["metrics"]["publications"], 2)
            self.assertIn("updated_at", snapshot)


if __name__ == "__main__":
    unittest.main()
