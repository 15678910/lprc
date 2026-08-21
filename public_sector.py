"""공공부문 임금교섭 근거자료 — 알리오(공공기관 경영정보 공개시스템)

왜 만들었나
----------
④⑤⑥ 은 DART 공시에 기대므로 상장사만 다룬다. 공공기관 노동자·노조는
그 화면을 쓸 수 없다. 알리오는 355개 공공기관의 보수·인원·근속을
같은 서식으로 공시하므로, 상장사 쪽과 같은 구조의 카드를 하나 더 만든다.

키가 필요 없다. 알리오 단일항목 통계 화면이 쓰는 JSON 을 그대로 부른다.

  GET /statisticsSearch/findItemTreeList.json
      → 항목 트리. treeCode = "<reportFormNo>-<itemNo>"
  GET /statisticsSearch/findSingleItemSearchList.json
      ?pageNo=&countPerPage=&reportFormNo=&itemNo=
      → 전 기관 × 6개 연도. countPerPage 는 100 이 상한이라 여러 쪽을 돈다.

CSV 다운로드(statisticsDown.json)는 파일명 규칙을 서버가 쥐고 있어 재현이 어렵다.
화면이 실제로 쓰는 위 JSON 이 같은 값을 주고 파싱도 필요 없다.

연도 기준 (알리오 화면 각주 그대로)
  yy5..yy1 = alioYear-5 .. alioYear-1  → **결산** 기준
  yy0      = alioYear                  → **당해년도 예산편성** 기준
  섞어서 평균 내면 안 된다. 출력에 basis 로 구분해 둔다.

DART 에 없는 축이 여기 있다
  · 무기계약직 보수·인원이 따로 잡힌다
  · 1인당 평균보수와 평균근속연수가 **성별로** 나온다
    → 성별 격차를 근속 차이로 얼마나 설명할 수 있는지 계산할 수 있다
  · 소속외인력(파견·용역·사내하도급)이 공시된다
    → README 가 "어떤 공시에도 없다"고 적은 간접고용이 공공부문엔 있다

⚠️ 한계
  · 알리오 화면이 바뀌면 깨진다. 실패는 조용히 넘기고 diag 에 남긴다.
  · 공공기관은 이익이 없어 ④ 의 '지불능력' 계산이 성립하지 않는다.
    총인건비 인상률 상한은 기재부 「공기업·준정부기관 예산운용지침」이 정하며
    공개 API 가 없다 → 화면에서 이용자가 직접 넣는다. 여기서는 추정하지 않는다.
  · 기능별 분류는 이 파일의 규칙이 만든 것이지 알리오의 공식 분류가 아니다.
    근거 규칙을 레코드마다 같이 실어 확인할 수 있게 한다.

출력: docs/public_sector.json
🚨 어느 쪽 주장도 대변하지 않는 계산 결과 · 노무·법률 자문 아님.
"""

import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FILE = os.path.join(BASE_DIR, "docs", "public_sector.json")

ALIO = "https://alio.go.kr"
PAGE = "/statisticsSearch/singleStatisticsSearch.do"
TREE = "/statisticsSearch/findItemTreeList.json"
LIST = "/statisticsSearch/findSingleItemSearchList.json"
UA = {
    "User-Agent": "Mozilla/5.0 (compatible; lprc-public-sector)",
    "Referer": ALIO + PAGE,
    "Accept": "application/json, text/plain, */*",
}
PER_PAGE = 100      # 서버 상한. 더 넣어도 100건만 온다.
PAUSE = 0.25        # 요청 간격

# 닿지 않을 때 오래 매달리지 않는 것이 중요하다.
# 알리오는 Actions 에서도 정상 수집된다(실측: 21개 항목 4분). 다만 **실행이 겹치면**
# 나중 것이 전부 timeout 난다 — 같은 출처의 동시 접속을 막는 것으로 보인다.
# 실제로 예약 실행이 도는 중에 수동 실행을 겹쳐 걸었다가 전 항목이 막혔다. 예전에는 타임아웃 40초 × 재시도 3회라
# 한 요청이 최대 126초를 잡았고, 84요청이면 3시간 가까이 헛돌았다. 실제로 그래서
# 자동 실행을 두 번 끊어야 했다. 짧게 시도하고 빨리 포기한다.
TIMEOUT = 12        # 초. 되는 환경에서는 0.4초면 온다 — 길게 잡을 이유가 없다.
TRIES = 2
GIVE_UP_AFTER = 3   # 항목이 연속 이만큼 실패하면 남은 항목을 건너뛴다

DIAG = []


def log(msg):
    print(msg, flush=True)


def diag(kind, msg):
    DIAG.append({"kind": kind, "msg": msg})
    log("[%s] %s" % (kind, msg))


def _ctx():
    c = ssl.create_default_context()
    c.check_hostname = False
    c.verify_mode = ssl.CERT_NONE     # 알리오 인증서 체인이 환경에 따라 끊긴다
    return c


def _get(path, params=None, timeout=TIMEOUT, tries=TRIES):
    url = ALIO + path + ("?" + urllib.parse.urlencode(params) if params else "")
    last = None
    for i in range(tries):
        try:
            r = urllib.request.Request(url, headers=UA)
            return urllib.request.urlopen(r, context=_ctx(), timeout=timeout).read()
        except Exception as e:
            last = e
            if i + 1 < tries:
                time.sleep(1.0)
    raise last


def _json(path, params=None):
    return json.loads(_get(path, params).decode("utf-8"))


def _num(v):
    """알리오는 빈칸을 '', 없는 값을 '-' 로 준다. 0 은 진짜 0 이므로 살린다."""
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if s in ("", "-", "null", "None"):
        return None
    try:
        f = float(s)
    except ValueError:
        return None
    return int(f) if f == int(f) else round(f, 2)


# ──────────────────────────────────────────────────────────────────────
# 가져올 항목 — treeCode 는 findItemTreeList.json 에서 확인한 값
# ──────────────────────────────────────────────────────────────────────
ITEMS = [
    # key,          treeCode,          라벨,                                단위
    ("pay",        "20601-GI0101",   "1인당 평균보수(일반정규직)",          "천원"),
    ("pay_m",      "20601-GI0111",   "1인당 평균보수(남성)",                "천원"),
    ("pay_f",      "20601-GI0112",   "1인당 평균보수(여성)",                "천원"),
    ("pay_base",   "20601-GI0102",   "기본급",                              "천원"),
    ("pay_perf",   "20601-GI0106",   "성과상여금",                          "천원"),
    ("pay_eval",   "20601-GI0107",   "경영평가 성과급",                     "천원"),
    ("pay_muhan",  "20601-GI0301",   "1인당 평균보수(무기계약직)",          "천원"),
    ("pay_new",    "20601-GI0208",   "신입사원 초임(합계)",                 "천원"),
    ("hc",         "20601-GI0109",   "상시종업원수",                        "명"),
    ("hc_m",       "20601-GI0113",   "상시종업원수(남성)",                  "명"),
    ("hc_f",       "20601-GI0114",   "상시종업원수(여성)",                  "명"),
    # 근속은 '년'이 아니라 **월** 단위로 온다(itmsUnit=5). 화면에서 12로 나눈다.
    ("ten",        "20601-GI0110",   "평균근속",                            "월"),
    ("ten_m",      "20601-GI0115",   "평균근속(남성)",                      "월"),
    ("ten_f",      "20601-GI0116",   "평균근속(여성)",                      "월"),
    ("emp_all",    "20202-GI03",     "임직원 총계",                         "명"),
    # 현원(GI020102)은 자식을 가진 중간 노드라 값이 안 온다. 잎인 '현원 > 계'를 쓴다.
    ("emp_reg",    "20202-GI02010201", "일반정규직 현원(계)",               "명"),
    ("emp_muhan",  "20202-GI02020201", "무기계약직 현원(계)",               "명"),
    ("emp_fixed",  "20202-GI050103", "기간제 계",                           "명"),
    ("emp_out",    "20202-GI050304", "소속외인력 계(파견·용역·사내하도급)", "명"),
    ("emp_female", "20202-GI0401",   "여성 현원 합계",                      "명"),
    ("hire_reg",   "20402-GI010201", "일반정규직 총신규채용",               "명"),
]

YKEYS = ["yy5", "yy4", "yy3", "yy2", "yy1", "yy0"]     # 오래된 해 → 최신


def alio_year():
    """GB_alioYear 를 화면에서 읽는다. 하드코딩하면 해가 바뀔 때 조용히 틀린다."""
    try:
        html = _get(PAGE).decode("utf-8", "replace")
        m = re.search(r'GB_alioYear\s*=\s*"(\d{4})"', html)
        if m:
            return int(m.group(1))
        diag("WARN", "GB_alioYear 를 화면에서 못 찾음 — 실행 연도로 대체")
    except Exception as e:
        diag("WARN", "알리오 화면 로드 실패(%s) — 실행 연도로 대체" % e)
    return datetime.now(KST).year


def check_tree():
    """연결 확인 겸 항목 코드 검증. 여기서 막히면 자료도 못 받으니 바로 포기한다.

    이 관문이 없으면 84개 요청을 전부 시도하며 몇 시간을 버린다.
    돌려주는 값이 False 면 호출 쪽에서 수집을 중단한다."""
    try:
        tree = _json(TREE)
    except Exception as e:
        diag("ERROR",
             "알리오에 닿지 못했다(%s). 다른 실행이 이미 돌고 있지 않은지 확인할 것 — "
             "동시 접속은 막힌다. 기존 파일을 그대로 둔다." % str(e)[:60])
        return False
    codes = set(n.get("treeCode") for n in tree.get("data", []) if n.get("treeCode"))
    missing = [c for _, c, _, _ in ITEMS if c not in codes]
    if missing:
        diag("ERROR", "트리에서 사라진 항목 코드: %s" % ", ".join(missing))
    else:
        log("  항목 트리 %s개 · 요청 코드 %d개 모두 유효" % (format(len(codes), ","), len(ITEMS)))
    return True


def fetch_item(tree_code):
    """한 항목의 전 기관 값. 실패하면 None 을 돌려 해당 항목만 빠지게 한다."""
    rf, ino = tree_code.split("-", 1)
    rows, page = [], 1
    while True:
        try:
            j = _json(LIST, {"pageNo": page, "countPerPage": PER_PAGE,
                             "reportFormNo": rf, "itemNo": ino})
        except Exception as e:
            diag("ERROR", "%s %d쪽 실패: %s" % (tree_code, page, e))
            return None
        if j.get("status") != "success":
            diag("ERROR", "%s 응답 status=%s" % (tree_code, j.get("status")))
            return None
        d = j.get("data") or {}
        rows += d.get("result") or []
        pg = d.get("page") or {}
        if page >= int(pg.get("totalPage") or 1):
            break
        page += 1
        time.sleep(PAUSE)
    return rows


# ──────────────────────────────────────────────────────────────────────
# 기능별 분류
#
# 알리오 기본 분류(공기업/준정부기관/기타공공기관)는 **법적 지위**라 임금 비교에
# 쓸모가 없다. 같은 '기타공공기관'인 한국산업은행과 국립생태원을 나란히 놓는 셈이다.
# 그래서 하는 일 기준으로 11개로 묶는다. 상장사 쪽을 표준산업분류로 묶은 것과
# 같은 발상이다. 이건 우리가 만든 분류이지 알리오의 공식 분류가 아니므로,
# 어떤 규칙이 걸렸는지 레코드마다 why 에 남긴다.
# ──────────────────────────────────────────────────────────────────────
# 코드를 붙여 두는 이유 — 상세 자료를 그룹별 파일로 쪼개는데(docs/ps/NN.json),
# 파일명에 한글을 쓰면 배포·캐시 경로에서 인코딩 사고가 난다.
GROUPS = [
    ("01", "에너지"), ("02", "SOC"), ("03", "금융"), ("04", "산업진흥정보화"),
    ("05", "농림수산환경"), ("06", "고용보건복지"), ("07", "문화국민생활"),
    ("08", "연구교육"), ("09", "검사검증"), ("10", "외교법무"), ("99", "기타"),
]
GROUP_CODE = dict((n, c) for c, n in GROUPS)

# 기관명 우선 규칙 — 주무부처보다 먼저 본다. (정규식, 그룹, 규칙설명)
# 부처는 정부조직 개편 때마다 바뀌지만 기관명은 잘 안 바뀌어서 더 안정적이다.
NAME_RULES = [
    # 연구·학술이 맨 앞이다. 에너지경제연구원의 노동시장은 발전소가 아니라
    # 다른 정부출연연구기관이다. 주제보다 하는 일이 먼저다.
    (r"연구원|연구소|연구회|정책연구|과학기술원|극지연구|기초과학|수리과학|"
     r"대학교$|대학원|학중앙연구원|기후센터|예보모델",
     "연구교육", "기관명(연구·학술)"),
    (r"병원|의료원|의학원|적십자사|요양원|장기조직기증|공공조직은행",
     "고용보건복지", "기관명(의료)"),
    (r"발전\(주\)|수력원자력|전력공사|전력거래소|전력기술|한전|원자력연료|지역난방|"
     r"에너지공단|에너지기술평가|에너지재단|에너지정보문화",
     "에너지", "기관명(전력·발전·에너지)"),
    (r"가스공사|가스기술|가스안전|석유공사|석유관리|석탄공사|광해광업",
     "에너지", "기관명(가스·석유·석탄·광업)"),
    (r"연금공단", "금융", "기관명(연금)"),
    (r"보증기금|보증재단|보증보험|산업은행|수출입은행|중소기업은행|예금보험|"
     r"자산관리공사|주택금융공사|투자공사|벤처투자|서민금융|주택도시보증|"
     r"무역보험|해양진흥공사",
     "금융", "기관명(금융)"),
    # 조폐공사는 재정경제부 소관이지만 하는 일은 제조업이다.
    (r"조폐공사", "산업진흥정보화", "기관명(제조)"),
    (r"항만공사|공항공사|신공항|철도공단|철도공사|도로공사|국제공항|"
     r"교통안전공단|도로교통공단|토지주택|국토정보|철도|코레일|에스알",
     "SOC", "기관명(교통·국토)"),
    (r"마사회|강원랜드|레저|관광공사|관광개발|체육|박물관|미술관|과학관|기념관|"
     r"문화전당|예술의전당|방송|언론|콘텐츠|저작권|영화|영상|출판|공예디자인|"
     r"국악|태권도|올림픽",
     "문화국민생활", "기관명(문화·체육·관광)"),
    (r"검역|품질평가|품질원|시험원|인증원|안전관리원|승강기안전|전기안전|"
     r"산업안전보건|식품안전|의약품안전|의료기기안전|원자력안전|"
     r"제품안전|방역지원|물기술인증|항공안전|건설기계안전|소방산업기술",
     "검사검증", "기관명(검사·인증·안전)"),
]

# 부처명은 2026년 정부조직 기준. 옛 이름도 같이 넣어 개편이 있어도 덜 깨지게 한다.
MINISTRY_MAP = {
    "국무조정실": "연구교육", "교육부": "연구교육",
    "보건복지부": "고용보건복지", "고용노동부": "고용보건복지",
    "성평등가족부": "고용보건복지", "여성가족부": "고용보건복지",
    "국가보훈부": "고용보건복지",
    "금융위원회": "금융", "재정경제부": "금융", "기획재정부": "금융",
    "국토교통부": "SOC",
    "해양수산부": "농림수산환경", "농림축산식품부": "농림수산환경",
    "산림청": "농림수산환경", "농촌진흥청": "농림수산환경",
    "기후에너지환경부": "농림수산환경", "환경부": "농림수산환경",
    "문화체육관광부": "문화국민생활", "국가유산청": "문화국민생활",
    "방송미디어통신위원회": "문화국민생활", "방송통신위원회": "문화국민생활",
    "식품의약품안전처": "검사검증", "원자력안전위원회": "검사검증",
    "외교부": "외교법무", "법무부": "외교법무", "통일부": "외교법무",
    "국방부": "외교법무", "방위사업청": "외교법무", "재외동포청": "외교법무",
    "행정안전부": "외교법무", "경찰청": "외교법무", "소방청": "외교법무",
    "인사혁신처": "외교법무",
    "산업통상부": "산업진흥정보화", "산업통상자원부": "산업진흥정보화",
    "과학기술정보통신부": "산업진흥정보화", "중소벤처기업부": "산업진흥정보화",
    "지식재산처": "산업진흥정보화", "특허청": "산업진흥정보화",
    "관세청": "산업진흥정보화", "국가데이터처": "산업진흥정보화",
    "통계청": "산업진흥정보화", "기획예산처": "산업진흥정보화",
    "공정거래위원회": "산업진흥정보화", "기상청": "산업진흥정보화",
}


def classify(name, ministry):
    for pat, grp, why in NAME_RULES:
        if re.search(pat, name or ""):
            return grp, why
    g = MINISTRY_MAP.get((ministry or "").strip())
    if g:
        return g, "주무부처(%s)" % ministry
    return "기타", "미분류"


# ──────────────────────────────────────────────────────────────────────
def median(vals, dec=1):
    v = sorted(x for x in vals if x is not None)
    if not v:
        return None
    n = len(v)
    m = v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2
    return round(m, dec)


def latest(seq, upto):
    """결산 구간에서 가장 최근의 값과 그 자리. upto 는 결산 마지막 칸의 인덱스."""
    if not seq:
        return None, None
    for i in range(min(upto, len(seq) - 1), -1, -1):
        if seq[i] is not None:
            return seq[i], i
    return None, None


def build_benchmark(orgs, si):
    """그룹 벤치마크 — 최신 결산연도 기준. 화면이 '우리 기관이 어디쯤인가'를 말한다."""
    def col(key, positive=False):
        out = []
        for o in orgs:
            v, _ = latest(o["d"].get(key), si)
            if v is not None and not (positive and v <= 0):
                out.append(v)
        return out

    pay = sorted(col("pay"))
    b = {
        "n": len(orgs),
        "pay": median(pay, 0),
        "pay_p25": round(pay[int(len(pay) * 0.25)]) if pay else None,
        "pay_p75": round(pay[min(len(pay) - 1, int(len(pay) * 0.75))]) if pay else None,
        # 초임 0은 '0원'이 아니라 그 해 신규채용이 없었다는 뜻이다.
        # 중위값에 넣으면 없는 저임금 기관을 만들어 낸다.
        "pay_new": median(col("pay_new", True), 0),
        "pay_muhan": median(col("pay_muhan", True), 0),
        "ten": median(col("ten"), 1),
    }
    # 성별 보수비 — 기관별로 먼저 비율을 낸 뒤 그 중앙값을 쓴다.
    # 남녀 보수의 중앙값을 각각 구해 나누면 서로 다른 기관을 비교하는 셈이 된다.
    ratios, tgaps, shares, mshares = [], [], [], []
    for o in orgs:
        m, _ = latest(o["d"].get("pay_m"), si)
        f, _ = latest(o["d"].get("pay_f"), si)
        if m and f:
            ratios.append(f / m * 100.0)
        tm, _ = latest(o["d"].get("ten_m"), si)
        tf, _ = latest(o["d"].get("ten_f"), si)
        if tm and tf:
            tgaps.append(tm - tf)
        out, _ = latest(o["d"].get("emp_out"), si)
        tot, _ = latest(o["d"].get("emp_all"), si)
        if out is not None and tot:
            shares.append(out / (out + tot) * 100.0)
        mu, _ = latest(o["d"].get("emp_muhan"), si)
        if mu is not None and tot:
            mshares.append(mu / tot * 100.0)
    b["gap_f"] = median(ratios, 1)          # 여성 보수 / 남성 보수 (%)
    b["ten_gap"] = median(tgaps, 1)         # 남성 근속 - 여성 근속 (월)
    b["out_share"] = median(shares, 1)      # 소속외인력 / (임직원+소속외인력) (%)
    b["muhan_share"] = median(mshares, 1)   # 무기계약직 / 임직원 (%)
    return b


def main():
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # type: ignore
        except Exception:
            pass
    now = datetime.now(KST)
    log("=" * 60)
    log("  공공부문 임금교섭 근거자료 (알리오)")
    log("=" * 60)

    ay = alio_year()
    years = [ay - 5 + i for i in range(6)]      # yy5..yy0 순서와 맞춘다
    si = 4                                      # years[4] = ay-1 이 마지막 결산연도
    log("  공시연도 %d · 결산 %d~%d · 예산 %d" % (ay, years[0], years[4], years[5]))

    if not check_tree():
        return 1                      # 닿지 못한다 — 기존 파일을 보존하고 즉시 끝낸다

    # 기관 명부는 첫 항목 응답에서 만든다. 별도 명부 API 를 또 부를 이유가 없다.
    orgs, ok, units, miss = {}, 0, {}, 0
    for key, code, label, unit in ITEMS:
        rows = fetch_item(code)
        time.sleep(PAUSE)
        if rows is None:
            miss += 1
            if miss >= GIVE_UP_AFTER:
                diag("ERROR", "연속 %d개 항목 실패 — 남은 항목을 건너뛴다." % miss)
                break
            continue
        miss = 0
        ok += 1
        # 단위는 우리가 적어 둔 값 대신 응답이 말하는 값을 쓴다.
        # 근속연수가 '년'이 아니라 '월'로 오는 것처럼, 짐작하면 틀린다.
        seen = set(r.get("itmsUnitNm") for r in rows if r.get("itmsUnitNm"))
        if len(seen) == 1:
            u = seen.pop()
            if u != unit:
                diag("WARN", "%s 단위가 '%s'가 아니라 '%s' — 응답을 따른다." % (label, unit, u))
            units[key] = u
        elif seen:
            diag("WARN", "%s 단위가 기관마다 다름: %s" % (label, ", ".join(sorted(seen))))
        for r in rows:
            oid = r.get("apbaId")
            if not oid:
                continue
            o = orgs.get(oid)
            if o is None:
                o = orgs[oid] = {
                    "id": oid,
                    "name": (r.get("apbaNa") or "").strip(),
                    "type": (r.get("apbaTypeNm") or "").strip(),
                    "ministry": (r.get("jidtDptmNa") or "").strip(),
                    "d": {},
                }
            seq = [_num(r.get(k)) for k in YKEYS]
            if any(x is not None for x in seq):
                o["d"][key] = seq
        log("    %-28s %s건" % (label, format(len(rows), ",")))

    if ok == 0 or not orgs:
        diag("ERROR", "전 항목 실패 — 기존 파일을 보존하고 종료한다.")
        return 1
    if ok < len(ITEMS):
        diag("WARN", "%d개 항목 누락 — 부분 수집으로 저장한다." % (len(ITEMS) - ok))

    for o in orgs.values():
        o["group"], o["why"] = classify(o["name"], o["ministry"])

    rows = sorted(orgs.values(), key=lambda x: x["name"])
    log("  기관 %s곳 · 항목 %d/%d개" % (format(len(rows), ","), ok, len(ITEMS)))

    # 그룹별 · 유형별 벤치마크
    groups, types = [], {}
    for code, g in GROUPS:
        mem = [o for o in rows if o["group"] == g]
        if not mem:
            continue
        b = build_benchmark(mem, si)
        b["code"], b["name"] = code, g
        groups.append(b)
        log("    %-8s %3d곳 · 중위 평균보수 %6.0f만원 · 여성/남성 %s%%"
            % (g, b["n"], (b["pay"] or 0) / 10.0, b["gap_f"]))
    for t in sorted(set(o["type"] for o in rows if o["type"])):
        types[t] = build_benchmark([o for o in rows if o["type"] == t], si)
    allb = build_benchmark(rows, si)

    # 전 기관 평균보수의 전년대비 변화 중앙값 — 총인건비 인상률이 실제로 남긴 결과다.
    # 지침 수치 자체는 공개 API 가 없으므로 여기서 만들어내지 않는다.
    yoy = []
    for i in range(1, 6):
        ch = []
        for o in rows:
            s = o["d"].get("pay")
            if s and s[i] and s[i - 1]:
                ch.append((s[i] / s[i - 1] - 1) * 100.0)
        yoy.append({"year": years[i], "median": median(ch, 2), "n": len(ch),
                    "basis": "예산" if i == 5 else "결산"})

    # 상장사 쪽과 같은 방식으로 쪼갠다 — 첫 화면은 목록만 받고,
    # 기관을 고른 뒤 그 그룹 파일 하나만 받는다. 그 파일이 '그룹 내 위치' 비교군도 겸한다.
    detail_dir = os.path.join(BASE_DIR, "docs", "ps")
    os.makedirs(detail_dir, exist_ok=True)
    for old in os.listdir(detail_dir):          # 그룹이 비면 옛 파일이 남는다
        if old.endswith(".json"):
            os.remove(os.path.join(detail_dir, old))
    for code, g in GROUPS:
        mem = [o for o in rows if o["group"] == g]
        if not mem:
            continue
        with open(os.path.join(detail_dir, code + ".json"), "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False, separators=(",", ":"))

    index = []
    for o in rows:
        pay, _ = latest(o["d"].get("pay"), si)
        index.append({"id": o["id"], "name": o["name"], "type": o["type"],
                      "ministry": o["ministry"], "g": GROUP_CODE.get(o["group"], "99"),
                      "why": o["why"], "pay": pay})

    out = {
        "generated": now.isoformat(),
        "source": "알리오(alio.go.kr) 공공기관 경영정보 공개시스템",
        "source_url": ALIO + PAGE,
        "alio_year": ay,
        "years": years,
        "basis": {
            "settled": years[:5],
            "budget": years[5],
            "note": ("알리오 각주 그대로 — 임원연봉·직원 평균보수·수입지출현황 항목의 "
                     "%d~%d년 자료는 결산 기준이고 %d년은 당해년도 예산편성 기준이다. "
                     "섞어서 비교하지 말 것." % (years[0], years[4], years[5])),
        },
        "items": dict((k, {"label": l, "unit": units.get(k, u), "code": c})
                      for k, c, l, u in ITEMS),
        "groups": groups,
        "types": types,
        "all": allb,
        "pay_yoy": yoy,
        "index": index,
        "detail_dir": "./ps/",
        "diag": DIAG,
        "limits": [
            "기능별 11개 분류는 이 도구가 만든 것이며 알리오의 공식 분류가 아니다. "
            "기관마다 why 에 어떤 규칙이 걸렸는지 적어 두었으니 확인하고 쓸 것.",
            "공공기관은 이익이 없어 상장사와 같은 '지불능력' 계산이 성립하지 않는다. "
            "총인건비 인상률 상한은 기재부 「공기업·준정부기관 예산운용지침」이 정하며 "
            "공개 API 가 없어 이용자가 직접 넣어야 한다.",
            "1인당 평균보수는 근속·직급 구성에 좌우된다. 기관 간 비교는 "
            "신입사원 초임과 평균근속연수를 함께 봐야 한다.",
            "소속외인력(파견·용역·사내하도급)은 해당 기관 소속 노동자가 아니다. "
            "인원만 공시되고 임금 수준은 공시되지 않는다.",
        ],
    }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, OUTPUT_FILE)
    det = sum(os.path.getsize(os.path.join(detail_dir, f))
              for f in os.listdir(detail_dir)) / 1024
    log("  저장 목록 %.0fKB + 그룹 상세 %d개 %.0fKB"
        % (os.path.getsize(OUTPUT_FILE) / 1024, len(os.listdir(detail_dir)), det))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
