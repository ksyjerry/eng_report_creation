# 교차 검증 (Cross-Check)

## 개요
재무제표 간의 논리적 일관성을 검증한다.
재무제표는 서로 연결되어 있으므로, 하나의 숫자가 여러 곳에서 일치해야 한다.

## BS 균형 검증

### 기본 등식
```
자산총계 = 부채총계 + 자본총계
Total assets = Total liabilities + Total equity
```

이 등식은 **반드시** 성립해야 한다 (허용 오차: 1).
성립하지 않으면 어딘가 숫자가 틀린 것이다.

### 하위 등식
```
유동자산 + 비유동자산 = 자산총계
유동부채 + 비유동부채 = 부채총계
```

## IS 내부 검증

```
매출총이익 = 매출액 - 매출원가
Gross profit = Revenue - Cost of sales

영업이익 = 매출총이익 - 판매비와관리비 + 기타수익 - 기타비용
Operating profit = Gross profit - Selling expenses + Other income - Other expenses

법인세비용차감전순이익 = 영업이익 + 금융수익 - 금융비용 ± 기타
Profit before tax = Operating profit + Finance income - Finance costs ± Others

당기순이익 = 법인세비용차감전순이익 - 법인세비용
Profit for the year = Profit before tax - Income tax expense
```

주의: IS 하위 등식은 항목 구성이 회사마다 다를 수 있어 완벽히 맞지 않을 수 있음.
자산총계=부채+자본 같은 절대 등식이 아님.

## CF 균형 검증

### 기본 등식
```
기말현금 = 기초현금 + 영업CF + 투자CF + 재무CF + 환율효과
Cash(end) = Cash(begin) + Operating + Investing + Financing + FX effect
```

### BS와의 연결
```
CF의 기말현금 = BS의 현금및현금성자산
```

이것도 반드시 성립해야 한다.

## CE 검증

### 기본 등식
```
기말잔액 = 기초잔액 + 당기변동
합계열 = 각 항목열의 합
```

### BS와의 연결
```
CE의 기말 자본총계 = BS의 자본총계
CE의 기말 자본금 = BS의 자본금
CE의 기말 이익잉여금 = BS의 이익잉여금
```

### IS와의 연결
```
CE의 당기순이익 = IS의 당기순이익
CE의 기타포괄손익 = IS의 기타포괄손익
```

## 재무제표 간 연결 요약

```
        BS ←→ CE (자본 항목 일치)
        ↕        ↕
        CF ←→ IS (순이익 일치)
        ↕
    BS 현금 = CF 기말현금
    CE 순이익 = IS 순이익
    CE 기말 자본 = BS 자본총계
```

## 검증 우선순위

1. **BS 균형** (자산 = 부채 + 자본) — 절대적
2. **CF 기말현금 = BS 현금** — 거의 절대적
3. **CE 기말 자본 = BS 자본총계** — 거의 절대적
4. **CE 순이익 = IS 순이익** — 반드시 일치
5. **IS 내부 합산** — 항목 구성에 따라 다를 수 있음
6. **CF 내부 합산** — 항목 구성에 따라 다를 수 있음

## 검증 실패 시 진단

```
BS 균형 불일치:
  → 자산 쪽이 큰가, 부채+자본 쪽이 큰가?
  → 차이 금액과 같은 값을 가진 행을 찾아봄 (누락 행 가능성)
  → 최근 변경한 행을 다시 확인

CF-BS 불일치:
  → CF 기말현금 값 확인
  → BS 현금및현금성자산 값 확인
  → 둘 중 하나가 업데이트 안 됐을 가능성

CE-BS 불일치:
  → CE 마지막 행(기말잔액) 확인
  → BS 자본 섹션 확인
```
