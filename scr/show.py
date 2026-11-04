import html
import io
import warnings
from collections import Counter

import folium
from folium.plugins import MarkerCluster
from matplotlib import font_manager, rcParams
from matplotlib.figure import Figure

# ==========================================================
# 시각화 모듈 (scr/show.py)
#
# 설계 원칙 (DIP / SRP)
#   - 이 모듈은 정류장을 "검색하지 않는다". 검색은 StationManager 담당이고,
#     여기서는 이미 만들어진 데이터를 전달받아 그리기만 한다.
#       * 전체 지도      : stations = [BusStop, ...]
#       * 근처 지도/그래프: result   = [(BusStop, 거리 km), ...]  (find_nearest_stations 반환값)
#   - StationManager를 import 하지 않는다. station.station_no / name / latitude /
#     longitude / node / type 속성만 가지고 있으면 어떤 객체든 받을 수 있다.
#   - 화면에 직접 띄우지 않고(plt.show 없음) 객체를 반환한다.
#       * 지도   -> folium.Map   (.save('파일.html') 로 바로 html 생성)
#       * 그래프 -> matplotlib Figure (figure_to_png_bytes 로 png 변환)
# ==========================================================


# 한글 깨짐 방지: 설치된 폰트 중 처음 발견되는 한글 폰트를 사용 (Windows / macOS / Linux)
def _setup_korean_font():
    candidates = ['Malgun Gothic', 'AppleGothic', 'NanumGothic',
                  'Noto Sans CJK KR', 'Noto Sans KR']
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            rcParams['font.family'] = name
            break
    else:
        warnings.warn('한글 폰트를 찾지 못했습니다. 그래프의 한글이 깨져 보일 수 있습니다.')
    rcParams['axes.unicode_minus'] = False


_setup_korean_font()


# matplotlib Figure -> PNG 바이트 (파일 저장 / HTTP 응답용)
def figure_to_png_bytes(fig, dpi=150):
    buffer = io.BytesIO()
    fig.savefig(buffer, format='png', dpi=dpi, bbox_inches='tight')
    return buffer.getvalue()


# 지도 시각화 클래스 (folium.Map 반환)
class ShowMap:

    # 가까운 정류장 지도의 확대 수준 (16 = 동네 골목이 보이는 정도, 17 = 건물 단위)
    NEARBY_ZOOM = 16
    NEARBY_MAX_ZOOM = 17

    # 전체 지도 생성: 전달받은 모든 정류장을 클러스터(묶음) 마커로 표시하고,
    # 전체(서울시 전체)가 한 화면에 보이게 맞춤
    #   - 멀리서 보면: 묶음 원 + 개수 / 확대하면: 개별 정류장 파란 핀으로 풀림
    #   - 정류장 수가 많으면 생성이 느리고 html 파일이 커진다.
    def show_map(self, stations):
        m = folium.Map(location=[37.5665, 126.9780], zoom_start=11)

        if not stations:
            return m

        cluster = MarkerCluster().add_to(m)
        for s in stations:
            folium.Marker(
                location=[s.latitude, s.longitude],
                popup=html.escape(f'{s.name} ({s.station_no})'),
                icon=folium.Icon(color='blue')
            ).add_to(cluster)

        lats = [s.latitude for s in stations]
        lons = [s.longitude for s in stations]
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

        return m

    # 가까운 정류장 지도 생성: 전달받은 위치 주변으로 확대해서 표시 (서울시 전체가 아님)
    # result: [(BusStop, 거리 km), ...]  (StationManager.find_nearest_stations 반환값)
    def show_nearest_station(self, result, latitude, longitude):
        m = folium.Map(location=[latitude, longitude], zoom_start=self.NEARBY_ZOOM)

        # 현재 위치 마커
        folium.Marker(
            location=[latitude, longitude],
            popup='현재 위치',
            icon=folium.Icon(color='red')
        ).add_to(m)

        points = [[latitude, longitude]]

        for station, distance in result:
            folium.Marker(
                location=[station.latitude, station.longitude],
                popup=f'{html.escape(station.name)} (거리: {distance * 1000:.0f}m)',
                icon=folium.Icon(color='orange')
            ).add_to(m)
            points.append([station.latitude, station.longitude])

        # 현재 위치와 정류장이 모두 보이는 범위로 맞추되, 너무 가까이 확대되지 않게 제한
        if len(points) > 1:
            m.fit_bounds(points, padding=(30, 30), max_zoom=self.NEARBY_MAX_ZOOM)

        return m


# 그래프 시각화 클래스 (matplotlib Figure 반환)
# 모든 메서드는 result = [(BusStop, 거리 km), ...] 를 전달받는다.
class ShowGraph:

    # 정류소 이름별 막대그래프 (가까울수록 막대가 길다, 가까운 정류장이 위쪽)
    #   막대 길이 = (가장 먼 거리 x 1.1) - 거리. 가장 먼 정류장도 막대가 보이도록 여유를 둔다.
    #   실제 거리(m)는 막대 끝에 숫자로 표시한다.
    def show_distance_by_station(self, result):
        rows = sorted(result, key=lambda x: x[1])
        names = [station.name for station, _ in rows]
        distances = [distance * 1000 for _, distance in rows]  # m
        lengths = [max(distances) * 1.1 - d for d in distances]

        fig = Figure(figsize=(10, 6))
        ax = fig.add_subplot(111)
        ax.barh(range(len(rows)), lengths, color='skyblue')
        ax.set_yticks(range(len(rows)))
        ax.set_yticklabels(names)
        ax.invert_yaxis()  # 가장 가까운 정류장이 맨 위
        for i, (length, d) in enumerate(zip(lengths, distances)):
            ax.text(length, i, f' {d:.0f}m', va='center')
        ax.set_xlim(0, max(lengths) * 1.15)
        ax.set_xticks([])
        ax.set_xlabel('가까운 정도 (막대가 길수록 가까움)')
        ax.set_title('가까운 정류장 (거리 기준)')
        fig.tight_layout()
        return fig

    # 이름 / 노드 / 거리 표 (가까운 정류장이 위쪽)
    def show_station_table(self, result):
        rows = sorted(result, key=lambda x: x[1])
        cells = [
            [station.name, station.node, f'{distance * 1000:.1f} m']
            for station, distance in rows
        ]

        fig = Figure(figsize=(10, 0.5 * len(cells) + 1.5))
        ax = fig.add_subplot(111)
        ax.axis('off')
        table = ax.table(
            cellText=cells,
            colLabels=['정류소 이름', '노드 ID', '거리'],
            loc='center',
            cellLoc='center'
        )
        table.auto_set_font_size(False)
        table.set_fontsize(11)
        table.scale(1, 1.6)
        for col in range(3):  # 머리글 행 강조
            header = table[0, col]
            header.set_facecolor('#dbe7fb')
            header.set_text_props(weight='bold')
        ax.set_title('가까운 정류장 목록 (가까운 순)')
        return fig

    # 정류장 유형 원그래프 (유형별 정류장 개수)
    def show_graph_by_type(self, result):
        counts = Counter(station.type for station, _ in result)
        total = sum(counts.values())

        fig = Figure(figsize=(7, 7))
        ax = fig.add_subplot(111)
        ax.pie(
            list(counts.values()),
            labels=list(counts.keys()),
            autopct=lambda p: f'{round(p * total / 100)}개',
            startangle=90,
            counterclock=False
        )
        ax.set_title('정류장 유형별 분포')
        return fig

    # 통합 시각화 메서드: {'distance': Figure, 'table': Figure, 'type': Figure} 반환
    def show_nearest_station_graph(self, result):
        return {
            'distance': self.show_distance_by_station(result),
            'table': self.show_station_table(result),
            'type': self.show_graph_by_type(result),
        }
