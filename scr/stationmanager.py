
import csv
import math


# ==========================================================
# 1. BusStop 클래스

# SOLID - S
#   하나의 버스 정류장 정보를 저장하고 표현하는 역할만 담당

# Input:
    # station_no: 정류소 번호 (str)
    # name: 정류소 이름 (str)
    # longitude: 경도 (float)
    # latitude: 위도 (float)
    # node: 노드 ID (str)
    # type: 정류장 유형 (str)

# Output:
    # BusStop 객체


class BusStop:
    def __init__(self, station_no, name, longitude, latitude, node, type):
        self.station_no = station_no
        self.name = name
        self.longitude = longitude
        self.latitude = latitude
        self.node = node
        self.type = type



# ==========================================================
# 2. StationDataLoader 클래스

# SOLID - S
#   CSV 파일을 읽고 BusStop 객체로 변환하는 역할만 담당

# Input: 
    # file_name (CSV 파일 경로, str)

# Output: 
    # StationDataLoader 객체


class StationDataLoader:
    def __init__(self, file_name="서울시 버스정류소 위치 정보.csv"):
        self.file_name = file_name

    def load_data(self):
        stations = []

        with open(self.file_name, "r", encoding="utf-8-sig") as file:
            reader = csv.DictReader(file)

            for row in reader:

                # 두 번째 줄의 영문 컬럼명 건너뛰기
                if row["정류소번호"] == "sttn_no":
                    continue

                station = BusStop(
                    row["정류소번호"],
                    row["정류소명"],
                    float(row["X좌표"]),
                    float(row["Y좌표"]),
                    row["노드_ID"],
                    row["정류장_유형"]
                )

                stations.append(station)

        return stations


# ==========================================================
# 3. DistanceCalculator 클래스 (일반 부모 클래스)

# SOLID: O
#   새로운 거리 계산 알고리즘을 자식 클래스로 추가 가능
#
# SOLID: I
#   거리 계산에 필요한 메서드만 정의
#
# SOLID: D
#   StationManager가 특정 거리 계산 방식에 의존하지 않도록
#   공통 부모 클래스 역할을 수행
#
# Input: 
    # 두 위치의 위도와 경도

# Output: 
    # 두 위치 사이의 거리 (float, km)


class DistanceCalculator:

    # Input: lat1, lon1, lat2, lon2 (float)
    # Output: 거리 (float, km)
    def calculate_distance(self, lat1, lon1, lat2, lon2):
        raise NotImplementedError(
            "자식 클래스에서 calculate_distance를 구현해야 합니다."
        )


# ==========================================================
# 4. HaversineCalculator 클래스

# SOLID: S
#   Haversine 공식을 사용한 거리 계산만 담당
#
# SOLID: OCP
#   기존 클래스를 수정하지 않고 다른 계산기 추가 가능
#
# SOLID: L
#   DistanceCalculator의 메서드를 같은 형식으로 구현
#   다른 거리 계산기 객체로 교체 가능
#
# Input: 
    # 두 위치의 위도와 경도

# Output: 
    # 두 위치 사이의 거리 (float, km)


class HaversineCalculator(DistanceCalculator):


    def calculate_distance(self, lat1, lon1, lat2, lon2):
        R = 6371  # 지구 반지름 (km)

        lat1 = math.radians(lat1)
        lon1 = math.radians(lon1)
        lat2 = math.radians(lat2)
        lon2 = math.radians(lon2)

        dlat = lat2 - lat1
        dlon = lon2 - lon1

        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1)
            * math.cos(lat2)
            * math.sin(dlon / 2) ** 2
        )

        # 부동소수점 오차 방지
        a = max(0.0, min(1.0, a))

        c = 2 * math.atan2(
            math.sqrt(a),
            math.sqrt(1 - a)
        )

        return R * c


# ==========================================================
# 5. StationManager 클래스

# SOLID: S
#   정류장 데이터를 관리하고 가까운 정류장을 검색
#   CSV 읽기와 거리 계산 공식 구현은 다른 클래스에 위임
#
# SOLID: O
#   거리 계산기를 교체해도 검색 로직 수정 불필요
#
# SOLID: D
#   특정 거리 계산기가 아닌 공통 계산 규약에 의존


class StationManager:

    # Input: 
        # stations (list), 
        # calculator (DistanceCalculator 계열 객체)

    # Output: 
        # StationManager 객체 초기화

    def __init__(self, stations, calculator):
        self.stations = stations
        self.calculator = calculator


    # Input:
        # user_lat: 사용자 위도 (float)
        # user_lon: 사용자 경도 (float)
        # count: 검색할 정류장 개수 (int, 기본값 5)

    # Output:
        # (BusStop 객체, 거리 km) 튜플로 이루어진 리스트
        
    def find_nearest_stations(self, user_lat, user_lon, count=5):
        result = []

        for station in self.stations:

            distance = self.calculator.calculate_distance(
                user_lat,
                user_lon,
                station.latitude,
                station.longitude
            )

            result.append((station, distance))

        # 거리 기준 오름차순 정렬
        result.sort(key=lambda x: x[1])

        return result[:count]


# ==========================================================
# 6. 실행 및 테스트
# ==========================================================
# SOLID: DIP (의존성 역전 원칙)
# - 외부에서 필요한 객체를 생성하고 연결 (의존성 주입)
#
# Input: CSV 파일, 사용자 위도 및 경도
# Output: 가까운 정류장 5개의 정보
# ==========================================================

if __name__ == "__main__":

    # 1. CSV 데이터 불러오기
    loader = StationDataLoader()
    stations = loader.load_data()

    print("불러온 정류장 수:", len(stations))

    # 2. 거리 계산기 생성
    calculator = HaversineCalculator()

    # 3. 정류장 관리자 생성
    manager = StationManager(stations, calculator)

    # 4. 테스트용 사용자 위치 (광운대 새빛관 기준)
    user_lat = 37.619774
    user_lon = 127.060926

    # 5. 가장 가까운 정류장 5개 검색
    nearest = manager.find_nearest_stations(
        user_lat,
        user_lon,
        10
    )

    # 6. 검색 결과 출력
    print("\n가장 가까운 정류장 5개")

    for i, (station, distance) in enumerate(nearest, start=1):
        print(
            f"{i}. {station.name} "
            f"(정류소번호: {station.station_no}) "
            f"- {distance * 1000:.1f}m"
        )
