"""
Verifies the live CRM state against every decision made in this session.
Run from inside the bellhaven-sync folder (needs requests + your .env
values, or hardcode CRM_TOKEN/CRM_BASE_URL below).
"""
import requests

BASE = "https://analyst-assessment-production.up.railway.app/api/v1"
TOKEN = "bh_arzIeBHlp9LgqAU10PxIKw"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

def get(account_id):
    r = requests.get(f"{BASE}/accounts/{account_id}", headers=HEADERS)
    r.raise_for_status()
    return r.json()

def search(q):
    r = requests.get(f"{BASE}/accounts", headers=HEADERS, params={"q": q})
    r.raise_for_status()
    return r.json()["data"]

def check(label, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label}" + (f" — {detail}" if detail and status == 'FAIL' else ""))
    return condition

print("=== Simple needs_fix renames / re-parents ===")
a = get("001TZCSTBZFM6K5BGN")
check("Grove City renamed", a["name"] == "Bellhaven Rehabilitation & Nursing of Grove City", a["name"])

a = get("001RJ0D7Z5MAZN5HX5")
check("Ashland renamed", a["name"] == "Bellhaven Healthcare Centre of Ashland", a["name"])

a = get("001LGFPBJY4N9MB6KL")
check("Lima re-parented to Bellhaven", a["parent_id"] == "0015QAPLGS3FVYEEEM", a["parent_id"])

a = get("001UKEFGADQ8YCZ4YM")
check("Findlay re-parented to Bellhaven", a["parent_id"] == "0015QAPLGS3FVYEEEM", a["parent_id"])

print("\n=== CHOW splits (old preserved, new created) ===")
for label, old_id, city in [("Tiffin", "001U6RW32TY0WSXZZB", "Tiffin"), ("Marietta", "001A34WFSUYHCRBLFT", "Marietta")]:
    old = get(old_id)
    check(f"{label} old account still parented to Cedar Trail (untouched)", old["parent_id"] != "0015QAPLGS3FVYEEEM", old["parent_id"])
    matches = [r for r in search(city) if r["parent_id"] == "0015QAPLGS3FVYEEEM" and r["billing_city"] == city]
    check(f"{label} new account created under Bellhaven", len(matches) == 1, f"found {len(matches)}")
    if matches:
        new_id = matches[0]["account_id"]
        check(f"{label} old account links chow_current_account to new", old.get("chow_current_account") == new_id,
              f"old.chow_current_account={old.get('chow_current_account')!r}, new id={new_id!r}")

print("\n=== Rejected needs_fix: Zanesville — real gap check ===")
cedar = get("001H1JMVZWP46D5VUF")
check("Cedar Trail of Zanesville left untouched (correctly rejected)", cedar["name"] == "Cedar Trail of Zanesville", cedar["name"])
zanesville_matches = [r for r in search("Zanesville") if r["parent_id"] == "0015QAPLGS3FVYEEEM"]
check("A real 'Bellhaven of Zanesville' account now exists", len(zanesville_matches) >= 1,
      "NONE FOUND — rejecting the bad match left this facility with no CRM account at all. You need to create one manually.")

print("\n=== Genuine new facilities (no_account_yet approvals) ===")
for name, city in [("Kettering", "Kettering"), ("Batavia", "Batavia"), ("Union Square", "New Albany"),
                    ("Carlisle", "Carlisle"), ("Amberly Manor", "Hudson")]:
    matches = [r for r in search(name) if r["billing_city"] == city]
    check(f"'{name}' created in {city}", len(matches) == 1, f"found {len(matches)}")

print("\n=== Stealth rebrands (rejected + manually corrected) ===")
checks = [
    ("Chesterton", "0013NUZQHQUEZ8DXEG", "Bellhaven of Chesterton"),
    ("Chagrin Falls (real)", "001RJU1X4NBWC1Q0G7", "Bellhaven of Chagrin Falls"),
    ("Willow Creek (real)", "0017MN2JYAJBDS8WQZ", "Bellhaven Willow Creek"),
]
for label, acc_id, expected_name in checks:
    a = get(acc_id)
    check(f"{label} renamed correctly", a["name"] == expected_name, a["name"])

print("\n=== Duplicates deactivated and linked ===")
dupes = [
    ("Chagrin Falls duplicate", "00134C3635F77CC7A7", "001RJU1X4NBWC1Q0G7"),
    ("Willow Creek duplicate", "0010BD9EB2B2DB55E0", "0017MN2JYAJBDS8WQZ"),
    ("Owosso duplicate", "001QU150PM4Z15UA71", "001EGU7BMJ942ZTRE6"),
]
for label, dup_id, real_id in dupes:
    a = get(dup_id)
    check(f"{label} status Inactive", a["status"] == "Inactive", a["status"])
    check(f"{label} duplicate_of_account correct", a["duplicate_of_account"] == real_id, a.get("duplicate_of_account"))

print("\n=== Genuine closures (Needs Review, untouched otherwise) ===")
for label, acc_id in [("Alliance", "00116ETS45BL7DTQP7"), ("Coldwater", "0016PVXH4B25HWR7QE"), ("Sandusky", "001SXSF4ELF0Z2LGDM")]:
    a = get(acc_id)
    check(f"{label} status Needs Review", a["status"] == "Needs Review", a["status"])
