"""The repo is public: saved pages in tests/pages/ must not carry personal contact data. Organisational role addresses of
government domains (info@wbmsc.gov.in) and office landlines are allowed; mobile numbers, tel: links and other e-mail addresses
are not."""
import re
from pathlib import Path

PAGES = Path(__file__).parent / "pages"
MOBILE = re.compile(r"(?<![\d/.-])(?:\+?91[\s-]?)?[6-9]\d{9}(?![\d/.-])")
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9-]+\.)+[A-Za-z]{2,}")
ROLE = re.compile(r"^(info|procurement|tender|tenders|contact|admin|webmaster|support|helpdesk|md|ceo|gm|cgm|office|"
                  r"mail|enquiry|grievance|rti)[A-Za-z0-9._-]*@([A-Za-z0-9-]+\.)*(gov|nic)\.in$", re.I)


def test_fixtures_have_no_personal_contacts():
    for f in sorted(PAGES.iterdir()):
        s = f.read_text(encoding="utf-8", errors="replace")
        assert not re.search(r"\btel:", s, re.I), f"{f.name}: tel: link"
        assert not MOBILE.findall(s), f"{f.name}: mobile number {MOBILE.findall(s)[:3]}"
        bad = [m.group(0) for m in EMAIL.finditer(s) if not ROLE.match(m.group(0))]
        assert not bad, f"{f.name}: e-mail addresses {bad[:3]}"


def test_privacy_patterns():
    assert MOBILE.findall("call 9876543210 now") and MOBILE.findall("+91-9876543210")
    assert not MOBILE.findall("033-23576504") and not MOBILE.findall("Files/PDF/639277867228469050_x.pdf")
    assert ROLE.match("procurement@wbmsc.gov.in") and not ROLE.match("ram.kumar@gmail.com")
