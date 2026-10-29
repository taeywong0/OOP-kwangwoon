import folium

# 지도 시각화 클래스
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