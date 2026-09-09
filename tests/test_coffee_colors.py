from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from app.coffee_colors import COFFEE_COLOR_PALETTE, contrast_ratio, next_coffee_color
from fastapi.testclient import TestClient
from test_api import bootstrap, build_client


def test_automatic_colors_extend_without_reassignment_and_support_dark_surfaces():
    colors = list(COFFEE_COLOR_PALETTE)
    for _ in range(100):
        color = next_coffee_color(colors)
        assert color not in colors
        assert contrast_ratio(color, "#FFFDFC") >= 3
        colors.append(color)
    assert colors[:8] == list(COFFEE_COLOR_PALETTE)
    assert next_coffee_color(colors) == next_coffee_color(reversed(colors))
    dark = []
    for _ in range(12):
        color = next_coffee_color(dark, surface="#241C19")
        assert color not in dark
        assert contrast_ratio(color, "#241C19") >= 3
        dark.append(color)


def test_concurrent_coffee_creation_allocates_distinct_colors(tmp_path: Path):
    with build_client(tmp_path) as client:
        _, headers = bootstrap(client)
        gate = Barrier(2)

        def create(index: int):
            other = TestClient(client.app)
            other.cookies.update(client.cookies)
            try:
                gate.wait(timeout=10)
                return other.post(
                    "/api/v1/coffees",
                    headers=headers,
                    json={"roaster": "Results", "name": f"Concurrent bag {index}"},
                )
            finally:
                other.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(create, range(2)))
        assert [response.status_code for response in responses] == [200, 200]
        assert responses[0].json()["chart_color"] != responses[1].json()["chart_color"]
