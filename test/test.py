import sys

# __pycache__ 생성 방지: scr 모듈을 import 하기 "전에" 설정해야 한다.
sys.dont_write_bytecode = True

from pathlib import Path

# ----------------------------------------------------------
# 경로 설정
#   프로젝트/
#   ├─ scr/   (show.py, stationmanager.py)
#   ├─ data/  (busStop.csv)
#   └─ test/
#      ├─ test.py
#      └─ output/  <- 모든 결과가 여기에 저장됨
# ----------------------------------------------------------
TEST_DIR = Path(__file__).resolve().parent      # test 폴더
ROOT_DIR = TEST_DIR.parent                      # scr, test의 상위 폴더
OUTPUT_DIR = TEST_DIR / "output"                # 결과 저장 폴더
OUTPUT_DIR.mkdir(exist_ok=True)
sys.path.insert(0, str(ROOT_DIR))               # 'scr'를 패키지로 import 가능하게 함

from scr.stationmanager import (
    StationDataLoader, HaversineCalculator, StationManager
)
from scr.show import ShowMap, ShowGraph, figure_to_png_bytes


# 테스트 위치: 광운대 새빛관
USER_LAT = 37.619774
USER_LON = 127.060926
COUNT = 10


def main():
    # 1. 데이터 로드 + 검색 (StationManager)
    #    old StationDataLoader는 기본 경로가 없으므로 data/busStop.csv 경로를 직접 전달
    csv_path = ROOT_DIR / "data" / "busStop.csv"
    stations = StationDataLoader(str(csv_path)).load_data()
    manager = StationManager(stations, HaversineCalculator())
    result = manager.find_nearest_stations(USER_LAT, USER_LON, COUNT)

    # 2. 간단한 검증
    assert len(stations) > 0, "정류장 데이터가 비어 있습니다."
    assert len(result) == COUNT, "검색 결과 개수가 count와 다릅니다."
    distances = [d for _, d in result]
    assert distances == sorted(distances), "거리 오름차순 정렬이 아닙니다."
    print("검증 통과")

    # 3. 텍스트 결과 저장
    lines = [f"불러온 정류장 수: {len(stations)}",
             f"\n가장 가까운 정류장 {COUNT}개"]
    for i, (s, d) in enumerate(result, start=1):
        lines.append(f"{i}. {s.name} (정류소번호: {s.station_no}) - {d * 1000:.1f}m")
    (OUTPUT_DIR / "result.txt").write_text("\n".join(lines), encoding="utf-8")

    # 4. 지도 저장 (folium이 바로 html 파일로 저장)
    show_map = ShowMap()
    show_map.show_map(stations).save(str(OUTPUT_DIR / "map_all.html"))
    show_map.show_nearest_station(result, USER_LAT, USER_LON).save(
        str(OUTPUT_DIR / "map_nearest.html"))

    # 5. 그래프 저장 (matplotlib Figure -> png)
    figs = ShowGraph().show_nearest_station_graph(result)
    for name, fig in figs.items():
        (OUTPUT_DIR / f"graph_{name}.png").write_bytes(figure_to_png_bytes(fig))

    print(f"완료: 결과가 {OUTPUT_DIR} 에 저장되었습니다.")
    print(" - result.txt / map_all.html / map_nearest.html")
    print(" - graph_distance.png / graph_table.png / graph_type.png")


if __name__ == "__main__":
    main()
