"""external_api.py 독립 테스트용 PyScript 앱."""

from pyscript import document, ffi
from external_api import ExternalLocationAPI

service = ExternalLocationAPI()
current_location = None
selected_destination = None
handlers = []  # JS 이벤트 리스너가 사용하는 Python 프록시를 유지


def status(message):
    document.getElementById("status").textContent = str(message)


def update_route_button():
    document.getElementById("route-btn").disabled = not (
        current_location is not None and selected_destination is not None
    )


def on_search(event):
    address = document.getElementById("address").value.strip()
    status("주소를 검색하고 있습니다...")

    def success(data):
        global selected_destination
        selected_destination = {**data, "name": data["address"]}
        status(
            f"목적지: {data['address']} / "
            f"위도 {data['latitude']:.6f}, 경도 {data['longitude']:.6f}"
        )
        update_route_button()

    service.address_to_coordinates(address, success, status)


def on_current_location(event):
    status("현재 위치를 확인하고 있습니다. 위치 권한을 허용하세요.")

    def success(data):
        global current_location
        current_location = {**data, "name": "현재 위치"}
        status(
            f"현재 위치: 위도 {data['latitude']:.6f}, "
            f"경도 {data['longitude']:.6f}"
        )
        update_route_button()

    service.get_current_location(success, status)


def on_route(event):
    if current_location is None or selected_destination is None:
        status("현재 위치와 목적지를 모두 지정하세요.")
        return
    mode = str(document.getElementById("mode").value)
    try:
        url = service.open_directions(current_location, selected_destination, mode)
        status(f"카카오맵 길찾기를 열었습니다. 팝업이 차단되었다면 확인하세요. {url}")
    except Exception as exc:
        status(f"길찾기 연결 실패: {exc}")


def bind(element_id, fn):
    proxy = ffi.create_proxy(fn)
    handlers.append(proxy)
    element = document.getElementById(element_id)
    element.addEventListener("click", proxy)
    element.disabled = False


bind("search-btn", on_search)
bind("location-btn", on_current_location)
bind("route-btn", on_route)
update_route_button()
status("준비 완료: 주소를 검색하거나 내 위치를 가져오세요.")
