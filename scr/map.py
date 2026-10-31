import folium
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

# 한글 깨짐 방지 설정 (Windows 환경 기준)
plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False


# 지도 시각화 클래스 (html 반환)
class ShowMap:

    # 기본 지도 생성
    def show_map(self, stations):
        m = folium.Map(location=[37.5665, 126.9780], zoom_start=12)

        # 정류장 마커 추가
        for station in stations:
            folium.Marker(
                location=[station.latitude, station.longitude],
                popup=station.name,
                icon=folium.Icon(color='blue')
            ).add_to(m)

        return m

    # 가까운 정류장 지도 생성 (현제 위치 기준 지도 제공 / 가까운 10개의 정류장만 표시)
    def show_nearest_station(self, stations, latitude, longitude):
        m = folium.Map(location=[latitude, longitude], zoom_start=12)

        # 현재 위치 마커
        folium.Marker(
            location=[latitude, longitude],
            popup='현재 위치',
            icon=folium.Icon(color='red')
        ).add_to(m)

        # 가장 가까운 정류장 찾기
        result = stations.find_nearest_stations(latitude, longitude, count=10)

        # 가장 가까운 정류장 마커 추가
        for station, distance in result:
            folium.Marker(
                location=[station.latitude, station.longitude],
                popup=f'{station.name} (거리: {distance:.2f} )',
                icon=folium.Icon(color='orange')
            ).add_to(m)

        return m


# 그래프 시각화 클래스 (이미지 반환)
class ShowGraph:

    # 공통 데이터 변환 헬퍼 메서드 ((BusStop, 거리) 리스트 -> DataFrame)
    def _to_dataframe(self, result):
        data = []
        for station, distance in result:
            data.append({
                'id': station.id,
                'name': station.name,
                'latitude': station.latitude,
                'longitude': station.longitude,
                'node': station.node,
                'type': station.type,
                'distance': distance
            })
        return pd.DataFrame(data)

    # 정류장별(ID/이름) 거리 비교 그래프 (막대 그래프)
    def show_distance_by_station(self, result):
        df = self._to_dataframe(result)
        
        plt.figure(figsize=(12, 6))
        plt.bar(df['name'], df['distance'], color='skyblue')
        plt.xlabel('정류장 이름')
        plt.ylabel('거리')
        plt.title('가까운 정류장별 거리 비교')
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        plt.show()

    # Node별 정류장 분포 그래프
    def show_graph_by_node(self, result):
        df = self._to_dataframe(result)
        
        plt.figure(figsize=(10, 5))
        sns.countplot(data=df, x='node', palette='viridis', hue='node', legend=False)
        plt.title('Node별 정류장 분포')
        plt.xlabel('Node')
        plt.ylabel('정류장 개수')
        plt.tight_layout()
        plt.show()

    # Type별 정류장 분포 그래프
    def show_graph_by_type(self, result):
        df = self._to_dataframe(result)
        
        plt.figure(figsize=(10, 5))
        sns.countplot(data=df, x='type', palette='Set2', hue='type', legend=False)
        plt.title('Type별 정류장 분포')
        plt.xlabel('Type')
        plt.ylabel('정류장 개수')
        plt.tight_layout()
        plt.show()

    # 통합 시각화 메서드
    def show_nearest_station_graph(self, stations, latitude, longitude):
        # 가장 가까운 정류장 찾기
        result = stations.find_nearest_stations(latitude, longitude, count=10)
        
        # 각각의 그래프 호출
        self.show_distance_by_station(result)
        self.show_graph_by_node(result)
        self.show_graph_by_type(result)
