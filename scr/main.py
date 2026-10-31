import csv
import math
import warnings
from urllib.parse import quote, parse_qs, urlparse

# 1. 빨간색 UserWarning 경고 박스 출력 원천 차단
warnings.filterwarnings("ignore")

import matplotlib
# 2. 브라우저 DOM 충돌(parentNode NoneType 에러) 방지용 Agg 백엔드 고정
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pyodide.http import pyfetch
from pyscript import document, window, when, display
try:
    from pyscript import ffi
except ImportError:
    from pyodide import ffi

from map import ShowMap, ShowGraph


# ==========================================================
# 1. 외부 API 연동 클래스 (ExternalLocationAPI)
# ==========================================================

class ExternalLocationAPI:
    MODES = {"walk", "car", "traffic", "bicycle"}

    def __init__(self):
        # 카카오 JS 키가 아직 없어도 GPS 위치 및 길찾기 링크는 동작하도록 처리
        try:
            self._geocoder = window.kakao.maps.services.Geocoder.new()
        except Exception:
            self._geocoder = None

    @staticmethod
    def _coordinate(point):
        if not isinstance(point, dict):
            raise ValueError("좌표는 딕셔너리여야 합니다.")
        lat = float(point["latitude"])
        lon = float(point["longitude"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("위도 또는 경도 범위를 벗어났습니다.")
        return lat, lon

    def address_to_coordinates(self, address, on_success, on_error):
        if self._geocoder is None:
            on_error("카카오 지도 SDK가 로드되지 않았습니다. HTML의 카카오 JS 키를 확인하세요.")
            return

        address = str(address).strip()
        if not address:
            on_error("주소를 입력하세요.")
            return

        proxy = None

        def received(results, status):
            try:
                expected = window.kakao.maps.services.Status.OK
                if status != expected or len(results) == 0:
                    on_error("주소를 찾을 수 없습니다. 정확한 도로명/지번 주소를 입력하세요.")
                    return
                first = results[0]
                on_success({
                    "latitude": float(first.y),
                    "longitude": float(first.x),
                    "address": str(first.address_name),
                })
            except Exception as exc:
                on_error(f"주소 검색 결과 처리 실패: {exc}")
            finally:
                proxy.destroy()

        proxy = ffi.create_proxy(received)
        try:
            self._geocoder.addressSearch(address, proxy)
        except Exception as exc:
            proxy.destroy()
            on_error(f"카카오 API 요청 실패: {exc}")

    def get_current_location(self, on_success, on_error):
        if not hasattr(window.navigator, "geolocation"):
            on_error("브라우저가 위치 정보 기능을 지원하지 않습니다.")
            return

        success_proxy = None
        error_proxy = None

        def release():
            success_proxy.destroy()
            error_proxy.destroy()

        def succeeded(position):
            try:
                on_success({
                    "latitude": float(position.coords.latitude),
                    "longitude": float(position.coords.longitude),
                })
            finally:
                release()

        def failed(error):
            try:
                on_error(f"현재 위치를 가져오지 못했습니다: {error.message}")
            finally:
                release()

        success_proxy = ffi.create_proxy(succeeded)
        error_proxy = ffi.create_proxy(failed)

        try:
            window.navigator.geolocation.getCurrentPosition(
                success_proxy,
                error_proxy,
                ffi.to_js({"enableHighAccuracy": True, "timeout": 10000}),
            )
        except Exception as exc:
            release()
            on_error(f"위치 요청 실패: {exc}")

    @classmethod
    def directions_url(cls, start, end, mode="walk"):
        if mode not in cls.MODES:
            raise ValueError("이동수단은 walk/car/traffic/bicycle 중 하나여야 합니다.")
        start_lat, start_lon = cls._coordinate(start)
        end_lat, end_lon = cls._coordinate(end)

        def item(point, lat, lon, fallback):
            name = quote(str(point.get("name") or fallback), safe="")
            return f"{name},{lat},{lon}"

        origin = item(start, start_lat, start_lon, "현재 위치")
        target = item(end, end_lat, end_lon, "목적지")
        return f"https://map.kakao.com/link/by/{mode}/{origin}/{target}"


# ==========================================================
# 2. 핵심 데이터 및 거리 계산 클래스 (BusStop / StationManager)
# ==========================================================

class BusStop:
    def __init__(self, station_no, name, longitude, latitude, node, type):
        self.id = station_no          # map.py의 station.id 참조 호환용
        self.station_no = station_no
        self.name = name
        self.longitude = longitude
        self.latitude = latitude
        self.node = node
        self.type = type


class StationDataLoader:
    def __init__(self, file_name="busStop.csv"):
        self.file_name = file_name

    def load_data(self):
        stations = []
        with open(self.file_name, "r", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)
            for row in reader:
                if row["정류소번호"] == "sttn_no":
                    continue
                station = BusStop(
                    row["정류소번호"],
                    row["정류소명"],
                    float(row["X좌표"]),
                    float(row["Y좌표"]),
                    row["노드_ID"],
                    row["정류장_유형"],
                )
                stations.append(station)
        return stations


class DistanceCalculator:
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        raise NotImplementedError


class HaversineCalculator(DistanceCalculator):
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        )
        a = max(0.0, min(1.0, a))
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return R * c


class StationManager:
    def __init__(self, stations, calculator):
        self.stations = stations
        self.calculator = calculator

    def find_nearest_stations(self, user_lat, user_lon, count=10):
        result = []
        for station in self.stations:
            distance = self.calculator.calculate_distance(
                user_lat, user_lon, station.latitude, station.longitude
            )
            result.append((station, distance))
        result.sort(key=lambda x: x[1])
        return result[:count]


# ==========================================================
# 3. PyScript DOM 연결 및 이벤트 바인딩
# ==========================================================

# plt.show() 호출 시 Agg 백엔드로 그려진 Figure를 #graph-container에 안전하게 삽입
def _pyscript_plt_show(*args, **kwargs):
    fig = plt.gcf()
    if document.querySelector("#graph-container") is not None:
        display(fig, target="graph-container", append=True)
    plt.clf()  # close(fig) 대신 clf()로 초기화해 parentNode 에러 방지

plt.show = _pyscript_plt_show

loader = StationDataLoader("busStop.csv")
stations = loader.load_data()
calculator = HaversineCalculator()
manager = StationManager(stations, calculator)

api = ExternalLocationAPI()
map_visualizer = ShowMap()
graph_visualizer = ShowGraph()


def show_error(msg):
    window.alert(msg)


def render_dashboard(user_coord):
    lat = user_coord["latitude"]
    lon = user_coord["longitude"]

    map_el = document.querySelector("#map-container")
    if map_el is None:
        window.location.href = f"./dashboard.html?lat={lat}&lon={lon}"
        return

    # 가까운 10개 정류장 검색
    nearest_result = manager.find_nearest_stations(lat, lon, count=10)

    # Folium 지도 렌더링 (상단 'Make this Notebook Trusted' 문구 숨김 처리)
    nearest_map = map_visualizer.show_nearest_station(manager, lat, lon)
    map_el.innerHTML = nearest_map._repr_html_()
    trusted_span = map_el.querySelector("span")
    if trusted_span is not None:
        trusted_span.style.display = "none"

    # 정류소 TOP 10 리스트 및 길찾기 링크 렌더링
    list_el = document.querySelector("#station-list")
    if list_el is not None:
        list_el.innerHTML = ""
        for i, (station, distance) in enumerate(nearest_result, start=1):
            stop_point = {
                "latitude": station.latitude,
                "longitude": station.longitude,
                "name": station.name,
            }
            walk_url = api.directions_url(user_coord, stop_point, mode="walk")
            dist_m = distance * 1000

            li = document.createElement("li")
            li.innerHTML = (
                f"{i}. <strong>{station.name}</strong> "
                f"(번호: {station.station_no} / 유형: {station.type}) - {dist_m:.1f}m "
                f"<a href='{walk_url}' target='_blank' rel='noopener noreferrer'>[길찾기]</a>"
            )
            list_el.appendChild(li)

    # 통계 그래프 3종 렌더링
    graph_el = document.querySelector("#graph-container")
    if graph_el is not None:
        graph_el.innerHTML = ""
        graph_visualizer.show_nearest_station_graph(manager, lat, lon)


async def _init_page():
    # PyScript 가상 환경에 나눔고딕 폰트 자동 다운로드 및 적용 (Malgun Gothic 대체)
    try:
        resp = await pyfetch(
            "https://raw.githubusercontent.com/google/fonts/main/ofl/nanumgothic/NanumGothic-Regular.ttf"
        )
        if resp.ok:
            with open("NanumGothic.ttf", "wb") as f:
                f.write(await resp.bytes())
            fm.fontManager.addfont("NanumGothic.ttf")
            plt.rcParams["font.family"] = "NanumGothic"
    except Exception:
        pass

    if document.querySelector("#map-container") is None:
        return
    query = parse_qs(urlparse(window.location.href).query)
    if "lat" in query and "lon" in query:
        lat = float(query["lat"][0])
        lon = float(query["lon"][0])
    else:
        lat, lon = 37.619774, 127.060926
    render_dashboard({"latitude": lat, "longitude": lon})

import asyncio
asyncio.ensure_future(_init_page())


@when("click", "#btn-search-address")
def on_address_search(event):
    addr = document.querySelector("#input-address").value
    api.address_to_coordinates(addr, render_dashboard, show_error)


@when("click", "#btn-current-location")
def on_gps_search(event):
    api.get_current_location(render_dashboard, show_error)