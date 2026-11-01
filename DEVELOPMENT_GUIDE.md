# OOP-kwangwoon 가이드 라인
본 문서는 BusFinder 프로그램의 원활한 개발과 충돌을 방지하기 위한 가이드 문서입니다.

## 개발 순서 (완료되면 체크해주세요)
- [ ] 핵심 로직 및 데이터
- [x] 지도 시각화
- [ ] 외부 API 연동
- [ ] 웹 UX/UI 디자인
- [ ] 통합 및 테스트
- [ ] 배포

## 파일 관리 (다음을 기준으로 합니다)
폴더 | 파일
---|---
data | csv
pages | html, css, js
scr | py
test | 테스트 파일 관리

## 버스 데이터 명세
    class BusStop:
        def __init__(self, id, name, latitude, longitude, node, type):
            self.id = id
            self.name = name
            self.latitude = latitude
            self.longitude = longitude
            self.node = node
            self.type = type
