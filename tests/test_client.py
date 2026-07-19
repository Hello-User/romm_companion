import unittest

import httpx

from romm_companion.api import (
    InsecureConnectionError,
    RommApiClient,
    RommAuthenticationError,
    RommNetworkError,
    RommPermissionError,
    RommResponseError,
    RommTimeoutError,
)
from romm_companion.api.connection import verify_connection
from romm_companion.config import ConnectionConfig

TOKEN = "rmm_" + ("a" * 64)


class RommApiClientTest(unittest.TestCase):
    def test_get_json_builds_an_authenticated_api_request(self):
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={"items": []},
            )

        config = ConnectionConfig.from_input("https://romm.example.test/root")
        with RommApiClient(
            config, TOKEN, transport=httpx.MockTransport(respond)
        ) as client:
            payload = client.get_json("roms", params={"limit": 20})

        self.assertEqual(payload, {"items": []})
        self.assertEqual(
            str(requests[0].url),
            "https://romm.example.test/root/api/roms?limit=20",
        )
        self.assertEqual(requests[0].headers["authorization"], f"Bearer {TOKEN}")
        self.assertEqual(requests[0].headers["accept"], "application/json")

    def test_get_image_bytes_builds_an_authenticated_resource_request(self):
        requests: list[httpx.Request] = []

        def respond(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(
                200,
                headers={"content-type": "image/png; charset=binary"},
                content=b"image data",
            )

        config = ConnectionConfig.from_input("https://romm.example.test/root")
        with RommApiClient(
            config, TOKEN, transport=httpx.MockTransport(respond)
        ) as client:
            content = client.get_image_bytes(
                "/assets/romm/resources/roms/3/7/cover/small.png?ts=updated"
            )

        self.assertEqual(content, b"image data")
        self.assertEqual(
            str(requests[0].url),
            "https://romm.example.test/assets/romm/resources/roms/3/7/cover/"
            "small.png?ts=updated",
        )
        self.assertEqual(requests[0].headers["authorization"], f"Bearer {TOKEN}")
        self.assertEqual(requests[0].headers["accept"], "image/*")

    def test_get_image_bytes_rejects_untrusted_resource_paths(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "image/png"},
                content=b"image data",
            )
        )
        with RommApiClient(
            ConnectionConfig.from_input("https://romm.example.test"),
            TOKEN,
            transport=transport,
        ) as client:
            paths = (
                "https://other.example.test/cover.png",
                "//other.example.test/cover.png",
                "/api/roms/7/cover",
                "/assets/romm/resources/../secrets",
                "/assets/romm/resources/%2e%2e/secrets",
                "/assets/romm/resources/cover.png#fragment",
            )
            for path in paths:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    client.get_image_bytes(path)

    def test_get_image_bytes_rejects_non_images_and_oversized_content(self):
        responses = (
            httpx.Response(
                200,
                headers={"content-type": "text/html"},
                content=b"not an image",
            ),
            httpx.Response(
                200,
                headers={"content-type": "image/png", "content-length": "5"},
                content=b"12345",
            ),
            httpx.Response(
                200,
                headers={"content-type": "image/png"},
                stream=httpx.ByteStream(b"12345"),
            ),
        )

        for response in responses:
            with self.subTest(headers=response.headers):
                transport = httpx.MockTransport(
                    lambda request, response=response: response
                )
                with (
                    RommApiClient(
                        ConnectionConfig.from_input("https://romm.example.test"),
                        TOKEN,
                        transport=transport,
                    ) as client,
                    self.assertRaises(RommResponseError),
                ):
                    client.get_image_bytes(
                        "/assets/romm/resources/cover.png",
                        max_bytes=4,
                    )

    def test_maps_authentication_and_permission_failures(self):
        cases = (
            (401, RommAuthenticationError),
            (403, RommPermissionError),
        )

        for status_code, error_type in cases:
            with self.subTest(status_code=status_code):
                transport = httpx.MockTransport(
                    lambda request, status_code=status_code: httpx.Response(status_code)
                )
                with (
                    RommApiClient(
                        ConnectionConfig.from_input("https://romm.example.test"),
                        TOKEN,
                        transport=transport,
                    ) as client,
                    self.assertRaises(error_type) as raised,
                ):
                    client.get_json("platforms")

                self.assertNotIn(TOKEN, str(raised.exception))

    def test_rejects_redirects_and_non_json_success_responses(self):
        responses = (
            httpx.Response(302, headers={"location": "https://login.example.test"}),
            httpx.Response(200, text="login page"),
        )

        for response in responses:
            with self.subTest(status_code=response.status_code):
                transport = httpx.MockTransport(
                    lambda request, response=response: response
                )
                with (
                    RommApiClient(
                        ConnectionConfig.from_input("https://romm.example.test"),
                        TOKEN,
                        transport=transport,
                    ) as client,
                    self.assertRaises(RommResponseError),
                ):
                    client.get_json("platforms")

    def test_maps_timeouts_without_exposing_request_details(self):
        def time_out(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("request details", request=request)

        with (
            RommApiClient(
                ConnectionConfig.from_input("https://romm.example.test"),
                TOKEN,
                transport=httpx.MockTransport(time_out),
            ) as client,
            self.assertRaisesRegex(RommTimeoutError, "Connection timed out"),
        ):
            client.get_json("platforms")

    def test_maps_transport_failures_without_exposing_request_details(self):
        def fail_to_connect(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("request details", request=request)

        with (
            RommApiClient(
                ConnectionConfig.from_input("https://romm.example.test"),
                TOKEN,
                transport=httpx.MockTransport(fail_to_connect),
            ) as client,
            self.assertRaisesRegex(RommNetworkError, "Could not reach RomM"),
        ):
            client.get_json("platforms")

    def test_rejects_absolute_traversal_and_inline_query_endpoints(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json=[],
            )
        )
        with RommApiClient(
            ConnectionConfig.from_input("https://romm.example.test"),
            TOKEN,
            transport=transport,
        ) as client:
            for endpoint in (
                "https://other.example.test/api/roms",
                "../roms",
                "roms?limit=20",
            ):
                with self.subTest(endpoint=endpoint), self.assertRaises(ValueError):
                    client.get_json(endpoint)

    def test_plain_http_requires_explicit_configuration(self):
        config = ConnectionConfig.from_input("http://romm.example.test")

        with self.assertRaises(InsecureConnectionError):
            RommApiClient(config, TOKEN)

        approved = ConnectionConfig.from_input(
            "http://romm.example.test", allow_insecure_http=True
        )
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json=[],
            )
        )
        with RommApiClient(approved, TOKEN, transport=transport) as client:
            self.assertEqual(client.get_json("platforms"), [])

    def test_connection_check_is_an_endpoint_specific_consumer(self):
        transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json=[],
            )
        )
        with RommApiClient(
            ConnectionConfig.from_input("https://romm.example.test"),
            TOKEN,
            transport=transport,
        ) as client:
            verify_connection(client)


if __name__ == "__main__":
    unittest.main()
