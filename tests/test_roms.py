import unittest

from romm_companion.api import RommResponseError
from romm_companion.api.roms import fetch_library_items, iter_library_item_pages


def make_rom(**overrides: object) -> dict[str, object]:
    rom: dict[str, object] = {
        "id": 7,
        "name": "Chrono Trigger",
        "fs_name": "Chrono Trigger (USA).sfc",
        "fs_name_no_tags": "Chrono Trigger",
        "platform_display_name": "SNES",
        "summary": "A time-travelling RPG.",
        "metadatum": {
            "first_release_date": 795830400000,
            "genres": ["Role-playing (RPG)", "Adventure"],
        },
    }
    rom.update(overrides)
    return rom


class FakeClient:
    def __init__(self, responses: list[object]) -> None:
        self.responses = list(responses)
        self.requests: list[tuple[str, dict[str, object]]] = []

    def get_json(self, endpoint: str, *, params: dict[str, object] | None = None):
        self.requests.append((endpoint, dict(params or {})))
        return self.responses.pop(0)


class FetchLibraryItemsTest(unittest.TestCase):
    def test_maps_complete_records(self):
        client = FakeClient([{"items": [make_rom()], "total": 1}])

        items = fetch_library_items(client)

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item.identifier, "7")
        self.assertEqual(item.title, "Chrono Trigger")
        self.assertEqual(item.platform, "SNES")
        self.assertEqual(item.release_year, "1995")
        self.assertEqual(item.genre, "Role-playing (RPG), Adventure")
        self.assertEqual(item.description, "A time-travelling RPG.")
        self.assertEqual(client.requests[0][0], "roms")
        self.assertEqual(client.requests[0][1]["offset"], 0)

    def test_falls_back_to_file_names_and_skips_unusable_records(self):
        client = FakeClient(
            [
                {
                    "items": [
                        make_rom(id=1, name=None),
                        make_rom(id=2, name=None, fs_name_no_tags="", fs_name=" "),
                        make_rom(id=None),
                        "not a record",
                    ],
                    "total": 4,
                }
            ]
        )

        items = fetch_library_items(client)

        self.assertEqual(
            [(item.identifier, item.title) for item in items],
            [("1", "Chrono Trigger")],
        )

    def test_tolerates_missing_metadata(self):
        client = FakeClient(
            [
                {
                    "items": [
                        make_rom(
                            id=1,
                            platform_display_name=None,
                            summary=None,
                            metadatum=None,
                        ),
                        make_rom(
                            id=2,
                            metadatum={"first_release_date": True, "genres": "RPG"},
                        ),
                        make_rom(
                            id=3,
                            metadatum={"first_release_date": 10**18},
                        ),
                    ],
                    "total": 3,
                }
            ]
        )

        items = fetch_library_items(client)

        self.assertEqual(items[0].platform, "")
        self.assertEqual(items[0].release_year, "")
        self.assertEqual(items[0].genre, "")
        self.assertEqual(items[0].description, "")
        self.assertEqual(items[1].release_year, "")
        self.assertEqual(items[1].genre, "")
        self.assertEqual(items[2].release_year, "")

    def test_fetches_every_page(self):
        client = FakeClient(
            [
                {"items": [make_rom(id=1), make_rom(id=2)], "total": 3},
                {"items": [make_rom(id=3)], "total": 3},
            ]
        )

        items = fetch_library_items(client)

        self.assertEqual([item.identifier for item in items], ["1", "2", "3"])
        self.assertEqual([params["offset"] for _, params in client.requests], [0, 2])

    def test_yields_each_page_before_requesting_the_next_one(self):
        client = FakeClient(
            [
                {"items": [make_rom(id=1)], "total": 2},
                {"items": [make_rom(id=2)], "total": 2},
            ]
        )
        pages = iter_library_item_pages(client)

        first_page = next(pages)

        self.assertEqual([item.identifier for item in first_page], ["1"])
        self.assertEqual([params["offset"] for _, params in client.requests], [0])

        second_page = next(pages)

        self.assertEqual([item.identifier for item in second_page], ["2"])
        self.assertEqual(
            [params["offset"] for _, params in client.requests],
            [0, 1],
        )
        self.assertEqual(list(pages), [])

    def test_stops_on_an_empty_page(self):
        client = FakeClient([{"items": [], "total": 10}])

        self.assertEqual(fetch_library_items(client), [])
        self.assertEqual(len(client.requests), 1)

    def test_rejects_unexpected_payloads(self):
        for payload in ([make_rom()], {"items": "not a list"}, None):
            with self.subTest(payload=payload), self.assertRaises(RommResponseError):
                fetch_library_items(FakeClient([payload]))


if __name__ == "__main__":
    unittest.main()
