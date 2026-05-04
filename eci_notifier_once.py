"""
ECI WB 2026 - single poll run for GitHub Actions.
Run once per invocation; state persisted in eci_seen_results.json.
"""
import os, json, time
import requests
from bs4 import BeautifulSoup
from curl_cffi import requests as cffi_requests

NTFY_TOPIC = "wb-election-2026"
STATE_FILE = "eci_seen_results.json"
NUM_PAGES  = 15
BASE_URL   = "https://results.eci.gov.in/ResultAcGenMay2026/statewiseS25{}.htm"
NTFY_URL   = f"https://ntfy.sh/{NTFY_TOPIC}"

_session = cffi_requests.Session(impersonate="chrome124")

PARTY_SHORT = {
    "Bharatiya Janata Party": "BJP",
    "All India Trinamool Congress": "TMC",
    "Indian National Congress": "INC",
    "Communist Party of India  (Marxist)": "CPI(M)",
    "Communist Party of India(Marxist)": "CPI(M)",
}

def short(party):
    for k, v in PARTY_SHORT.items():
        if k.lower() in party.lower():
            return v
    words = party.split()
    return "".join(w[0] for w in words if w[0].isupper())[:6] or party[:8]

def _party_name(td):
    nested = td.find("td")
    return nested.get_text(" ", strip=True) if nested else td.get_text(" ", strip=True)

def is_declared(status):
    s = status.lower()
    return "counted" in s or "won" in s or "declared" in s

def scrape_page(page_num):
    url = BASE_URL.format(page_num)
    try:
        r = _session.get(url, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  [page {page_num}] fetch error: {e}")
        return []
    soup = BeautifulSoup(r.text, "html.parser")
    rows = []
    all_trs = soup.select("table tr")
    for tr in all_trs:
        tds = tr.find_all("td", recursive=False)
        if len(tds) < 9:
            continue
        rows.append({
            "constituency": tds[0].get_text(strip=True),
            "winner":       tds[2].get_text(strip=True),
            "winner_party": _party_name(tds[3]),
            "runner":       tds[4].get_text(strip=True),
            "runner_party": _party_name(tds[5]),
            "margin":       tds[6].get_text(strip=True),
            "status":       tds[8].get_text(strip=True),
        })
    return rows

def send_notification(title, body, tags="trophy"):
    try:
        resp = requests.post(
            NTFY_URL,
            data=body.encode("utf-8"),
            headers={"Title": title, "Tags": tags, "Priority": "high"},
            timeout=10,
        )
        print(f"  [ntfy {resp.status_code}] {title}")
    except Exception as e:
        print(f"  [ntfy error] {e}")

def load_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}

def save_seen(seen):
    with open(STATE_FILE, "w") as f:
        json.dump(seen, f, indent=2)

def main():
    seen = load_seen()
    newly_declared = []
    for page in range(1, NUM_PAGES + 1):
        for r in scrape_page(page):
            key = r["constituency"]
            if not key:
                continue
            if is_declared(r["status"]) and seen.get(key, {}).get("status") != "won":
                newly_declared.append(r)
                seen[key] = {"status": "won", "winner": r["winner"],
                             "party": r["winner_party"], "margin": r["margin"]}
        time.sleep(1)

    total_won = sum(1 for v in seen.values() if v.get("status") == "won")

    if newly_declared:
        save_seen(seen)
        for r in newly_declared:
            wp = short(r["winner_party"])
            title = f"RESULT: {r['constituency']} - {wp} wins!"
            body  = (
                f"{r['winner']} ({short(r['winner_party'])}) WINS\n"
                f"vs {r['runner']} ({short(r['runner_party'])})\n"
                f"Margin: {r['margin']} votes\n"
                f"Total declared: {total_won}/294"
            )
            send_notification(title, body)
        print(f"Notified {len(newly_declared)} new result(s). Total: {total_won}/294")

        if total_won >= 294:
            send_notification(
                "All 294 results declared!",
                "West Bengal 2026 counting complete.",
                tags="tada",
            )
    else:
        print(f"No new results. Total so far: {total_won}/294")

if __name__ == "__main__":
    main()
