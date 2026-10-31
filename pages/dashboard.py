"""BusFinder 대시보드 화면(UI) 모듈 - 팀원 4 담당

PyScript에서 실행됩니다. dashboard.html의 버튼/입력창을 id로 찾아서
- 주소 검색, 내 위치 가져오기는 팀원 2의 ExternalLocationAPI(external_api.py)를 쓰고
- 정류장 계산은 `calculator` 함수(나중에 팀원 1의 StationManager로 교체)를 쓰고
- 지도는 `map_renderer` 함수(나중에 팀원 3의 MapRenderer로 교체)를 씁니다.

화면(HTML)을 바꾸는 일만 이 파일이 맡고, 계산이나 지도는 직접 하지 않습니다.
"""
from html import escape
from math import radians, sin, cos, asin, sqrt

from pyscript import document
from pyodide.ffi import create_proxy

from external_api import ExternalLocationAPI


# --------------------------------------------------------------------
# 1) 임시(데모) 계산기: StationManager가 연결되기 전에 화면을 확인하기 위한 것
#    ★ 통합할 때 이 함수를 StationManager 호출로 바꾸세요.
#    반환 형식: [{"name", "type", "latitude", "longitude", "distance_m"}, ...] (가까운 순)
# --------------------------------------------------------------------
DEMO_STATIONS = [
    {"name": "서울시청앞", "type": "일반도로", "latitude": 37.5663, "longitude": 126.9779},
    {"name": "덕수궁",     "type": "일반도로", "latitude": 37.5655, "longitude": 126.9753},
    {"name": "을지로입구", "type": "일반도로", "latitude": 37.5660, "longitude": 126.9824},
    {"name": "명동성당",   "type": "마을버스", "latitude": 37.5633, "longitude": 126.9876},
    {"name": "남대문시장", "type": "마을버스", "latitude": 37.5594, "longitude": 126.9773},
    {"name": "서울역",     "type": "일반도로", "latitude": 37.5547, "longitude": 126.9707},
    {"name": "광화문",     "type": "일반도로", "latitude": 37.5759, "longitude": 126.9769},
    {"name": "종각",       "type": "마을버스", "latitude": 37.5702, "longitude": 126.9830},
]


def haversine_m(lat1, lon1, lat2, lon2):
    """두 좌표 사이 거리(m)"""
    la1, lo1, la2, lo2 = map(radians, (lat1, lon1, lat2, lon2))
    a = sin((la2 - la1) / 2) ** 2 + cos(la1) * cos(la2) * sin((lo2 - lo1) / 2) ** 2
    return 6371000 * 2 * asin(sqrt(a))


def demo_calculator(lat, lon, count, types):
    picked = []
    for s in DEMO_STATIONS:
        if s["type"] in types:
            picked.append(dict(s, distance_m=haversine_m(lat, lon, s["latitude"], s["longitude"])))
    picked.sort(key=lambda s: s["distance_m"])
    return picked[:count]


# --------------------------------------------------------------------
# 2) 화면에 보여줄 HTML 조각 만들기 (DOM 없이도 테스트 가능한 순수 함수)
# --------------------------------------------------------------------
def format_distance(meters):
    return f"{int(meters)}m" if meters < 1000 else f"{meters / 1000:.1f}km"


def tag_class(stop_type):
    return "village" if stop_type == "마을버스" else "road"


def build_ratio_html(results, types):
    """선택한 도로 종류별 개수와 비율(막대 그래프)"""
    total = len(results)
    parts = []
    for t in types:
        c = sum(1 for s in results if s["type"] == t)
        percent = round(c / total * 100) if total else 0
        parts.append(
            f'<div class="ratio-item">'
            f'<div class="ratio-label"><span>{escape(t)}</span>'
            f'<strong>{c}개 · {percent}%</strong></div>'
            f'<div class="bar"><div class="bar-fill {tag_class(t)}" style="width:{percent}%"></div></div>'
            f'</div>'
        )
    return "".join(parts)


def build_results_html(results, origin, mode):
    """가까운 정류장 리스트(<li> 모음). 각 줄에 길찾기 링크 포함"""
    items = []
    for i, s in enumerate(results, start=1):
        try:
            url = ExternalLocationAPI.directions_url(
                {"latitude": origin[0], "longitude": origin[1], "name": "현재 위치"},
                {"latitude": s["latitude"], "longitude": s["longitude"], "name": s["name"]},
                mode,
            )
            route = f'<a class="route-link" href="{escape(url)}" target="_blank" rel="noopener">길찾기</a>'
        except Exception:
            route = ""
        nearest = ' class="nearest"' if i == 1 else ""
        items.append(
            f'<li{nearest}><span class="rank">{i}</span>'
            f'<div class="info"><div class="name">{escape(s["name"])}</div>'
            f'<span class="tag {tag_class(s["type"])}">{escape(s["type"])}</span></div>'
            f'<div class="dist">{format_distance(s["distance_m"])}</div>{route}</li>'
        )
    return "".join(items)


# --------------------------------------------------------------------
# 3) 화면 컨트롤러: 버튼 클릭 → 객체 호출 → 화면 갱신
# --------------------------------------------------------------------
class DashboardUI:
    def __init__(self, api=None, calculator=None, map_renderer=None):
        self.api = api or ExternalLocationAPI()       # 팀원 2: 주소/내 위치
        self.calculator = calculator or demo_calculator  # 팀원 1로 교체 예정
        self.map_renderer = map_renderer               # 팀원 3: fn(lat, lon, results) 형태
        self._proxies = []                             # 이벤트 함수가 사라지지 않게 보관

    # ----- DOM 도우미 -----
    @staticmethod
    def _el(element_id):
        return document.getElementById(element_id)

    def set_status(self, message, error=False):
        el = self._el("status")
        el.textContent = message
        el.className = "status error" if error else "status"

    def _selected_types(self):
        boxes = document.querySelectorAll('input[name="types"]:checked')
        return [box.value for box in boxes]

    def _coords(self):
        lat, lng = self._el("lat").value, self._el("lng").value
        if lat == "" or lng == "":
            return None
        return float(lat), float(lng)

    def _on(self, element_id, handler):
        proxy = create_proxy(lambda event: handler())
        self._proxies.append(proxy)
        self._el(element_id).addEventListener("click", proxy)

    # ----- 시작 -----
    def bind(self):
        self._on("search-btn", self.search_address)
        self._on("location-btn", self.use_my_location)
        self._on("calc-btn", self.calculate)
        for element_id in ("search-btn", "location-btn", "calc-btn"):
            self._el(element_id).disabled = False
        self.set_status("준비 완료! 주소를 입력하거나 [내 위치 가져오기]를 눌러주세요.")

    # ----- 위치 입력 -----
    def search_address(self, then=None):
        address = self._el("address").value.strip()
        if not address:
            self.set_status("주소를 입력하세요.", error=True)
            return
        self.set_status("주소 검색 중...")
        self.api.address_to_coordinates(
            address, lambda point: self._got_point(point, then), self._on_error)

    def use_my_location(self):
        self.set_status("현재 위치 확인 중... (브라우저의 위치 권한을 허용해 주세요)")
        self.api.get_current_location(
            lambda point: self._got_point(point, None), self._on_error)

    def _got_point(self, point, then):
        self._el("lat").value = f'{point["latitude"]:.6f}'
        self._el("lng").value = f'{point["longitude"]:.6f}'
        if point.get("address"):
            self._el("address").value = point["address"]
        self.set_status("위치를 확인했어요. [계산 실행]을 눌러주세요.")
        if then:
            then()

    def _on_error(self, message):
        self.set_status(str(message), error=True)

    # ----- 계산 실행 -----
    def calculate(self):
        coords = self._coords()
        if coords is None:
            # 좌표가 없으면 주소를 먼저 검색하고, 성공하면 이어서 계산
            self.search_address(then=self.calculate)
            return
        types = self._selected_types()
        if not types:
            self.set_status("도로 종류를 하나 이상 선택하세요.", error=True)
            return
        count = int(self._el("count").value)
        mode = self._el("mode").value

        results = self.calculator(coords[0], coords[1], count, types)
        self.render(results, coords, types, mode)

    # ----- 화면 갱신 -----
    def render(self, results, coords, types, mode):
        self._el("ratio-content").innerHTML = build_ratio_html(results, types)
        self._el("result-list").innerHTML = (
            build_results_html(results, coords, mode)
            if results else '<li class="empty">조건에 맞는 정류장이 없어요.</li>')
        self._el("result-count").textContent = f"{len(results)}개"
        self._el("ratio-box").hidden = False
        self._el("result-box").hidden = False
        if self.map_renderer:
            self.map_renderer(coords[0], coords[1], results)
        self.set_status(f"가까운 정류장 {len(results)}개를 찾았어요.")


ui = DashboardUI()
ui.bind()
