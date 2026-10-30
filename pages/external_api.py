"""BusFinder 외부 API 연동 — PyScript에서 실행되는 Python 모듈.

JavaScript SDK/브라우저 API는 PyScript FFI를 통해 호출하며,
이 모듈에는 JavaScript 애플리케이션 로직이 필요하지 않습니다.
"""

from urllib.parse import quote
from pyscript import ffi, window


class ExternalLocationAPI:
    MODES = {"walk", "car", "traffic", "bicycle"}

    def __init__(self):
        # HTML에서 카카오 지도 SDK를 libraries=services 옵션으로 먼저 로드해야 합니다.
        try:
            self._geocoder = window.kakao.maps.services.Geocoder.new()
        except Exception as exc:
            raise RuntimeError(
                "카카오 지도 SDK를 사용할 수 없습니다. JavaScript 키, "
                "허용 도메인, 카카오맵 활성화, libraries=services를 확인하세요."
            ) from exc

    @staticmethod
    def _coordinate(point):
        """공통 좌표 형식: {latitude, longitude, name(선택)}"""
        if not isinstance(point, dict):
            raise ValueError("좌표는 딕셔너리여야 합니다.")
        try:
            lat = float(point["latitude"])
            lon = float(point["longitude"])
        except (KeyError, ValueError, TypeError) as exc:
            raise ValueError("latitude와 longitude 숫자가 필요합니다.") from exc
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("위도 또는 경도 범위를 벗어났습니다.")
        return lat, lon

    def address_to_coordinates(self, address, on_success, on_error):
        """비동기 주소 검색. 성공 시 {latitude, longitude, address} 전달."""
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
                    "latitude": float(first.y),  # 카카오 y = 위도
                    "longitude": float(first.x), # 카카오 x = 경도
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
        """사용자 허용 후 브라우저 위치를 전달. 보통 HTTPS/localhost 필요."""
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
        """외부 카카오맵 길찾기 링크 만들기. 서버/API 호출 없음."""
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

    def open_directions(self, start, end, mode="walk"):
        """클릭 이벤트에서 직접 호출해야 팝업 차단 가능성이 낮습니다."""
        url = self.directions_url(start, end, mode)
        window.open(url, "_blank", "noopener,noreferrer")
        return url
