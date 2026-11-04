"""BusFinder 통합 테스트 (scr/*.py, pages/external_api.py)

실행 방법 (어느 위치에서 실행해도 됩니다):
    python test/test.py            # 전체 테스트 (그래프 창 없음)
    python test/test.py --show     # 테스트 후 통합 데모 실행: 지도는 브라우저로, 그래프는 창으로 표시
    python -m unittest test/test.py -v

통합 테스트(IntegrationTest)는 CSV 로드 → StationManager 검색 → ShowMap/ShowGraph 까지
모듈들이 실제로 연동되는지 확인하고, 결과물을 test/output/ 에 저장합니다.
(nearest_map.html, graph_distance.png, graph_node.png, graph_type.png)

- 외부 라이브러리(folium, matplotlib, seaborn, pandas)가 없으면 해당 테스트만 건너뜁니다.
- external_api.py는 브라우저(PyScript) 전용이라 pyscript / 카카오 SDK를 가짜(mock)로 대체합니다.
"""

import csv
import importlib
import math
import os
import sys
import tempfile
import types
import unittest
from unittest import mock

# ---------------------------------------------------------------------------
# 경로 설정: test/ 기준으로 scr, pages, data 위치를 계산
# ---------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCR_DIR = os.path.join(ROOT, "scr")
PAGES_DIR = os.path.join(ROOT, "pages")
CSV_PATH = os.path.join(ROOT, "data", "busStop.csv")

for path in (SCR_DIR, PAGES_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

# --show 가 없으면 그래프를 화면에 띄우지 않고 테스트 (matplotlib import 전에 설정)
SHOW = "--show" in sys.argv
if SHOW:
    sys.argv.remove("--show")  # unittest 가 모르는 옵션이라 제거
else:
    os.environ.setdefault("MPLBACKEND", "Agg")

OUTPUT_DIR = os.path.join(ROOT, "test", "output")

from stationmanager import (  # noqa: E402
    BusStop,
    DistanceCalculator,
    HaversineCalculator,
    StationDataLoader,
    StationManager,
)

# 광운대 새빛관 (stationmanager.py 실행 예시와 동일한 좌표)
KW_LAT, KW_LON = 37.619774, 127.060926


def _has(module_name):
    try:
        importlib.import_module(module_name)
        return True
    except ImportError:
        return False


HAS_MAP_LIBS = all(_has(m) for m in ("folium", "matplotlib", "seaborn", "pandas"))
HAS_CSV = os.path.exists(CSV_PATH)


def make_stations():
    """CSV 없이 쓰는 작은 테스트용 정류장 목록 (이름이 같은 정류장 포함)."""
    return [
        BusStop("S1", "광운대역", 127.0610, 37.6200, "N1", "일반차로"),
        BusStop("S2", "광운대역", 127.0612, 37.6202, "N2", "일반차로"),  # 이름 중복
        BusStop("S3", "월계역", 127.0650, 37.6300, "N3", "마을버스"),
        BusStop("S4", "노원역", 127.0560, 37.6550, "N4", "중앙차로"),
        BusStop("S5", "서울역", 126.9720, 37.5550, "N5", "중앙차로"),
    ]


# ===========================================================================
# 1. BusStop
# ===========================================================================
class BusStopTest(unittest.TestCase):
    def test_fields(self):
        s = BusStop("123", "테스트", 127.0, 37.5, "00001", "일반차로")
        self.assertEqual(s.station_no, "123")
        self.assertEqual(s.name, "테스트")
        self.assertEqual(s.longitude, 127.0)
        self.assertEqual(s.latitude, 37.5)
        self.assertEqual(s.node, "00001")
        self.assertEqual(s.type, "일반차로")

    def test_id_alias(self):
        """개발 가이드의 BusStop.id 명세와 호환되어야 한다."""
        self.assertEqual(BusStop("123", "x", 127.0, 37.5, "n", "t").id, "123")


# ===========================================================================
# 2. StationDataLoader
# ===========================================================================
class StationDataLoaderTest(unittest.TestCase):
    def _write_csv(self, rows):
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".csv", delete=False, encoding="utf-8-sig", newline=""
        )
        writer = csv.writer(tmp)
        writer.writerow(["정류소번호", "정류소명", "X좌표", "Y좌표", "노드_ID", "정류장_유형"])
        writer.writerow(["sttn_no", "sttn_nm", "xcrdnt", "ycrdnt", "node_id", "sttn_type"])
        writer.writerows(rows)
        tmp.close()
        self.addCleanup(os.remove, tmp.name)
        return tmp.name

    def test_skips_english_header_row(self):
        path = self._write_csv([["1", "A", "127.1", "37.5", "n1", "t1"]])
        stations = StationDataLoader(path).load_data()
        self.assertEqual(len(stations), 1)
        self.assertEqual(stations[0].station_no, "1")

    def test_x_is_longitude_y_is_latitude(self):
        path = self._write_csv([["1", "A", "127.1", "37.5", "n1", "t1"]])
        s = StationDataLoader(path).load_data()[0]
        self.assertAlmostEqual(s.longitude, 127.1)
        self.assertAlmostEqual(s.latitude, 37.5)

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            StationDataLoader("no_such_file.csv").load_data()

    def test_invalid_coordinate_raises(self):
        path = self._write_csv([["1", "A", "abc", "37.5", "n1", "t1"]])
        with self.assertRaises(ValueError):
            StationDataLoader(path).load_data()

    @unittest.skipUnless(HAS_CSV, "data/busStop.csv 없음")
    def test_default_path_works_from_any_cwd(self):
        """실행 위치(cwd)와 무관하게 기본 경로로 CSV를 읽어야 한다."""
        old = os.getcwd()
        try:
            os.chdir(tempfile.gettempdir())
            stations = StationDataLoader().load_data()
        finally:
            os.chdir(old)
        self.assertGreater(len(stations), 0)

    @unittest.skipUnless(HAS_CSV, "data/busStop.csv 없음")
    def test_real_data_sanity(self):
        stations = StationDataLoader(CSV_PATH).load_data()
        self.assertGreater(len(stations), 10000)
        for s in stations:
            # 서울/수도권 범위: 위도·경도가 뒤바뀌면 여기서 걸린다
            self.assertTrue(36 < s.latitude < 39, (s.station_no, s.latitude))
            self.assertTrue(125 < s.longitude < 128, (s.station_no, s.longitude))
        self.assertEqual(len({s.station_no for s in stations}), len(stations))


# ===========================================================================
# 3. 거리 계산
# ===========================================================================
class DistanceCalculatorTest(unittest.TestCase):
    def test_base_class_is_abstract(self):
        with self.assertRaises(NotImplementedError):
            DistanceCalculator().calculate_distance(0, 0, 0, 0)

    def test_haversine_same_point_is_zero(self):
        self.assertEqual(HaversineCalculator().calculate_distance(37.5, 127.0, 37.5, 127.0), 0)

    def test_haversine_one_degree_latitude(self):
        d = HaversineCalculator().calculate_distance(37.0, 127.0, 38.0, 127.0)
        self.assertAlmostEqual(d, 111.19, delta=0.1)  # 위도 1도 ≈ 111.19km

    def test_haversine_seoul_to_busan(self):
        d = HaversineCalculator().calculate_distance(37.5665, 126.9780, 35.1796, 129.0756)
        self.assertAlmostEqual(d, 325, delta=5)  # 직선거리 약 325km

    def test_haversine_symmetric(self):
        calc = HaversineCalculator()
        a = calc.calculate_distance(37.5, 127.0, 37.6, 127.1)
        b = calc.calculate_distance(37.6, 127.1, 37.5, 127.0)
        self.assertAlmostEqual(a, b)

    def test_haversine_antipodal_does_not_crash(self):
        d = HaversineCalculator().calculate_distance(0, 0, 0, 180)
        self.assertAlmostEqual(d, math.pi * 6371, places=3)


# ===========================================================================
# 4. StationManager
# ===========================================================================
class StationManagerTest(unittest.TestCase):
    def setUp(self):
        self.manager = StationManager(make_stations(), HaversineCalculator())

    def test_returns_requested_count_sorted(self):
        result = self.manager.find_nearest_stations(KW_LAT, KW_LON, 3)
        self.assertEqual(len(result), 3)
        distances = [d for _, d in result]
        self.assertEqual(distances, sorted(distances))

    def test_nearest_is_correct(self):
        result = self.manager.find_nearest_stations(37.6200, 127.0610, 1)
        self.assertEqual(result[0][0].station_no, "S1")

    def test_default_count_is_five(self):
        self.assertEqual(len(self.manager.find_nearest_stations(KW_LAT, KW_LON)), 5)

    def test_count_larger_than_data(self):
        self.assertEqual(len(self.manager.find_nearest_stations(KW_LAT, KW_LON, 100)), 5)

    def test_empty_stations(self):
        self.assertEqual(StationManager([], HaversineCalculator()).find_nearest_stations(0, 0), [])

    def test_calculator_is_replaceable(self):
        """DIP/OCP: 다른 계산기를 주입해도 검색 로직이 그대로 동작해야 한다."""

        class ManhattanCalculator(DistanceCalculator):
            def calculate_distance(self, lat1, lon1, lat2, lon2):
                return abs(lat1 - lat2) + abs(lon1 - lon2)

        manager = StationManager(make_stations(), ManhattanCalculator())
        result = manager.find_nearest_stations(37.6200, 127.0610, 2)
        self.assertEqual([s.station_no for s, _ in result], ["S1", "S2"])

    @unittest.skipUnless(HAS_CSV, "data/busStop.csv 없음")
    def test_real_data_nearest_to_kwangwoon(self):
        manager = StationManager(StationDataLoader(CSV_PATH).load_data(), HaversineCalculator())
        result = manager.find_nearest_stations(KW_LAT, KW_LON, 10)
        self.assertEqual(len(result), 10)
        self.assertLess(result[0][1], 0.5)  # 가장 가까운 정류장은 500m 이내


# ===========================================================================
# 5. 지도 / 그래프 시각화 (scr/map.py)
# ===========================================================================
@unittest.skipUnless(HAS_MAP_LIBS, "folium / matplotlib / seaborn / pandas 필요")
class MapTest(unittest.TestCase):
    def setUp(self):
        import map as map_module  # scr/map.py

        self.map_module = map_module
        self.manager = StationManager(make_stations(), HaversineCalculator())

    @staticmethod
    def _markers(folium_map):
        import folium

        return [c for c in folium_map._children.values() if isinstance(c, folium.Marker)]

    def test_show_map_has_marker_per_station(self):
        m = self.map_module.ShowMap().show_map(make_stations())
        self.assertEqual(len(self._markers(m)), 5)

    def test_show_nearest_station_markers(self):
        m = self.map_module.ShowMap().show_nearest_station(self.manager, KW_LAT, KW_LON)
        self.assertEqual(len(self._markers(m)), 1 + 5)  # 현재 위치 1 + 정류장 5(데이터가 5개뿐)

    def test_show_nearest_station_popup_has_unit(self):
        m = self.map_module.ShowMap().show_nearest_station(self.manager, KW_LAT, KW_LON)
        html = m.get_root().render()
        self.assertIn("m)", html)  # 거리 단위가 표시되어야 한다

    def test_to_dataframe_columns_and_values(self):
        result = self.manager.find_nearest_stations(KW_LAT, KW_LON, 3)
        df = self.map_module.ShowGraph()._to_dataframe(result)
        self.assertEqual(
            list(df.columns),
            ["id", "name", "latitude", "longitude", "node", "type", "distance"],
        )
        self.assertEqual(len(df), 3)
        self.assertEqual(df.loc[0, "id"], result[0][0].station_no)

    def test_distance_graph_draws_one_bar_per_station_even_with_duplicate_names(self):
        import matplotlib.pyplot as plt

        result = self.manager.find_nearest_stations(KW_LAT, KW_LON, 5)  # '광운대역' 2개 포함
        with mock.patch.object(plt, "show"):
            self.map_module.ShowGraph().show_distance_by_station(result)
        ax = plt.gcf().axes[0]
        self.assertEqual(len(ax.patches), 5)
        self.assertEqual(len(ax.get_xticks()), 5)
        plt.close("all")

    def test_all_graphs_run_without_error(self):
        import matplotlib.pyplot as plt

        with mock.patch.object(plt, "show"):
            self.map_module.ShowGraph().show_nearest_station_graph(self.manager, KW_LAT, KW_LON)
        plt.close("all")

    @unittest.skipUnless(HAS_CSV, "data/busStop.csv 없음")
    def test_real_data_graphs(self):
        import matplotlib.pyplot as plt

        manager = StationManager(StationDataLoader(CSV_PATH).load_data(), HaversineCalculator())
        with mock.patch.object(plt, "show"):
            self.map_module.ShowGraph().show_nearest_station_graph(manager, KW_LAT, KW_LON)
        plt.close("all")


# ===========================================================================
# 5-2. 통합 테스트: CSV -> StationManager -> ShowMap / ShowGraph 연동
# ===========================================================================
@unittest.skipUnless(HAS_MAP_LIBS and HAS_CSV, "라이브러리 또는 data/busStop.csv 없음")
class IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import map as map_module

        cls.map_module = map_module
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        # 1) 데이터 로드 -> 2) 거리 계산기 주입 -> 3) 관리자 생성 (실제 앱과 같은 순서)
        cls.stations = StationDataLoader(CSV_PATH).load_data()
        cls.manager = StationManager(cls.stations, HaversineCalculator())
        cls.nearest = cls.manager.find_nearest_stations(KW_LAT, KW_LON, 10)

    def test_pipeline_result_shape(self):
        self.assertEqual(len(self.nearest), 10)
        for station, distance in self.nearest:
            self.assertIsInstance(station, BusStop)
            self.assertGreaterEqual(distance, 0)

    def test_map_saved_and_contains_nearest_stations(self):
        m = self.map_module.ShowMap().show_nearest_station(self.manager, KW_LAT, KW_LON)
        path = os.path.join(OUTPUT_DIR, "nearest_map.html")
        m.save(path)

        self.assertTrue(os.path.getsize(path) > 0)
        with open(path, encoding="utf-8") as f:
            html = f.read()
        self.assertIn("현재 위치", html)
        # 검색된 정류장 이름이 모두 지도(팝업)에 들어갔는지 확인
        for station, _ in self.nearest:
            self.assertIn(station.name, html)

    def test_graphs_saved_as_png(self):
        import matplotlib.pyplot as plt

        names = iter(["graph_distance.png", "graph_node.png", "graph_type.png"])

        def save_instead_of_show():
            plt.savefig(os.path.join(OUTPUT_DIR, next(names)))
            plt.close()

        with mock.patch.object(plt, "show", side_effect=save_instead_of_show):
            self.map_module.ShowGraph().show_nearest_station_graph(self.manager, KW_LAT, KW_LON)

        for name in ("graph_distance.png", "graph_node.png", "graph_type.png"):
            path = os.path.join(OUTPUT_DIR, name)
            self.assertTrue(os.path.exists(path), name)
            self.assertGreater(os.path.getsize(path), 1000, name)

    def test_swapped_coordinates_would_be_detected(self):
        """위도/경도가 뒤바뀌면 가장 가까운 정류장이 수십 km 밖으로 나온다 (연동 오류 감지용)."""
        swapped = self.manager.find_nearest_stations(KW_LON, KW_LAT, 1)
        self.assertGreater(swapped[0][1], 100)


def run_demo():
    """--show: 실제 화면으로 결과를 확인하는 데모 (지도는 브라우저, 그래프는 창)."""
    import webbrowser

    import map as map_module

    stations = StationDataLoader(CSV_PATH).load_data()
    manager = StationManager(stations, HaversineCalculator())

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, "nearest_map.html")
    map_module.ShowMap().show_nearest_station(manager, KW_LAT, KW_LON).save(path)
    print("지도 저장:", path)
    webbrowser.open("file://" + path.replace(os.sep, "/"))

    print("그래프 창 3개가 차례로 뜹니다. 하나를 닫으면 다음 그래프가 표시됩니다.")
    map_module.ShowGraph().show_nearest_station_graph(manager, KW_LAT, KW_LON)


# ===========================================================================
# 6. 외부 API (pages/external_api.py) — pyscript / 카카오 SDK mock
# ===========================================================================
class FakeProxy:
    def __init__(self, fn):
        self.fn = fn
        self.destroyed = False

    def __call__(self, *args):
        return self.fn(*args)

    def destroy(self):
        self.destroyed = True


def load_external_api():
    """가짜 pyscript 모듈을 주입한 뒤 external_api를 새로 import."""
    fake = types.ModuleType("pyscript")
    fake.ffi = mock.MagicMock()
    fake.ffi.create_proxy.side_effect = FakeProxy
    fake.ffi.to_js.side_effect = lambda x: x
    fake.window = mock.MagicMock()
    fake.window.kakao.maps.services.Status.OK = "OK"
    sys.modules["pyscript"] = fake
    sys.modules.pop("external_api", None)
    module = importlib.import_module("external_api")
    return module, fake


@unittest.skipUnless(os.path.exists(os.path.join(PAGES_DIR, "external_api.py")), "pages/external_api.py 없음")
class ExternalApiTest(unittest.TestCase):
    def setUp(self):
        self.module, self.fake = load_external_api()
        self.api = self.module.ExternalLocationAPI()
        self.geocoder = self.api._geocoder

    # --- 좌표 검증 ---------------------------------------------------------
    def test_coordinate_valid(self):
        self.assertEqual(
            self.module.ExternalLocationAPI._coordinate({"latitude": "37.5", "longitude": 127}),
            (37.5, 127.0),
        )

    def test_coordinate_invalid(self):
        c = self.module.ExternalLocationAPI._coordinate
        for bad in (None, [], {"latitude": 1}, {"latitude": "a", "longitude": 1},
                    {"latitude": 91, "longitude": 0}, {"latitude": 0, "longitude": 181},
                    {"latitude": float("nan"), "longitude": 0}):
            with self.assertRaises(ValueError, msg=repr(bad)):
                c(bad)

    # --- 길찾기 URL ---------------------------------------------------------
    def test_directions_url(self):
        url = self.module.ExternalLocationAPI.directions_url(
            {"latitude": 37.5, "longitude": 127.0, "name": "현재 위치"},
            {"latitude": 37.6, "longitude": 127.1},
            "car",
        )
        self.assertTrue(url.startswith("https://map.kakao.com/link/by/car/"))
        self.assertIn(",37.5,127.0/", url)
        self.assertTrue(url.endswith(",37.6,127.1"))
        self.assertIn("%EB%AA%A9%EC%A0%81%EC%A7%80", url)  # 이름 없으면 '목적지' (URL 인코딩)

    def test_directions_url_encodes_comma_in_name(self):
        url = self.module.ExternalLocationAPI.directions_url(
            {"latitude": 1, "longitude": 1, "name": "a,b"},
            {"latitude": 2, "longitude": 2, "name": "c"},
        )
        self.assertIn("a%2Cb,1.0,1.0", url)

    def test_directions_url_rejects_bad_mode(self):
        with self.assertRaises(ValueError):
            self.module.ExternalLocationAPI.directions_url(
                {"latitude": 1, "longitude": 1}, {"latitude": 2, "longitude": 2}, "plane"
            )

    def test_open_directions_opens_new_tab(self):
        url = self.api.open_directions(
            {"latitude": 1, "longitude": 1}, {"latitude": 2, "longitude": 2}, "walk"
        )
        self.fake.window.open.assert_called_once_with(url, "_blank", "noopener,noreferrer")

    # --- 주소 검색 -----------------------------------------------------------
    def test_address_empty_calls_on_error(self):
        ok, err = mock.Mock(), mock.Mock()
        self.api.address_to_coordinates("   ", ok, err)
        err.assert_called_once()
        ok.assert_not_called()
        self.geocoder.addressSearch.assert_not_called()

    def test_address_success_parses_kakao_xy(self):
        first = types.SimpleNamespace(x="127.06", y="37.62", address_name="서울 노원구")
        self.geocoder.addressSearch.side_effect = lambda addr, cb: cb([first], "OK")
        ok, err = mock.Mock(), mock.Mock()
        self.api.address_to_coordinates("서울 노원구", ok, err)
        ok.assert_called_once_with({"latitude": 37.62, "longitude": 127.06, "address": "서울 노원구"})
        err.assert_not_called()

    def test_address_not_found(self):
        self.geocoder.addressSearch.side_effect = lambda addr, cb: cb([], "ZERO_RESULT")
        ok, err = mock.Mock(), mock.Mock()
        self.api.address_to_coordinates("없는 주소", ok, err)
        err.assert_called_once()
        ok.assert_not_called()

    def test_address_proxy_is_destroyed_after_callback(self):
        proxies = []
        self.fake.ffi.create_proxy.side_effect = lambda fn: proxies.append(FakeProxy(fn)) or proxies[-1]
        self.geocoder.addressSearch.side_effect = lambda addr, cb: cb([], "ZERO_RESULT")
        self.api.address_to_coordinates("x", mock.Mock(), mock.Mock())
        self.assertTrue(all(p.destroyed for p in proxies))

    def test_address_request_failure_reports_error(self):
        self.geocoder.addressSearch.side_effect = RuntimeError("boom")
        ok, err = mock.Mock(), mock.Mock()
        self.api.address_to_coordinates("x", ok, err)
        err.assert_called_once()

    # --- 현재 위치 -----------------------------------------------------------
    def test_current_location_success(self):
        pos = types.SimpleNamespace(coords=types.SimpleNamespace(latitude=37.5, longitude=127.0))
        self.fake.window.navigator.geolocation.getCurrentPosition.side_effect = (
            lambda ok_cb, err_cb, opts: ok_cb(pos)
        )
        ok, err = mock.Mock(), mock.Mock()
        self.api.get_current_location(ok, err)
        ok.assert_called_once_with({"latitude": 37.5, "longitude": 127.0})
        err.assert_not_called()

    def test_current_location_denied(self):
        error = types.SimpleNamespace(message="denied")
        self.fake.window.navigator.geolocation.getCurrentPosition.side_effect = (
            lambda ok_cb, err_cb, opts: err_cb(error)
        )
        ok, err = mock.Mock(), mock.Mock()
        self.api.get_current_location(ok, err)
        err.assert_called_once()
        self.assertIn("denied", err.call_args[0][0])
        ok.assert_not_called()

    def test_sdk_missing_raises_runtime_error(self):
        self.fake.window.kakao.maps.services.Geocoder.new.side_effect = Exception("no sdk")
        with self.assertRaises(RuntimeError):
            self.module.ExternalLocationAPI()


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False).result
    if SHOW:
        if result.wasSuccessful():
            run_demo()
        else:
            print("\n테스트가 실패해서 --show 데모는 실행하지 않았습니다.")
    sys.exit(not result.wasSuccessful())
