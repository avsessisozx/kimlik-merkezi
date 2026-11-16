"""CI özeti: junit XML + günlükteki OLCUM satırları -> markdown ($GITHUB_STEP_SUMMARY ve günlük)."""
from __future__ import annotations

import glob
import os
import sys
import xml.etree.ElementTree as ET


def main(klasor: str) -> None:
    satirlar = [f"## Karar A ölçümü: {os.environ.get('RUNNER_OS', '?')} (Python {sys.version.split()[0]})", ""]
    satirlar += ["| Test | Sonuç | Süre (s) |", "|---|---|---|"]
    sayac = {"GEÇTİ": 0, "KALDI": 0, "ATLANDI": 0}
    for xml in sorted(glob.glob(os.path.join(klasor, "junit-*.xml"))):
        for tc in ET.parse(xml).getroot().iter("testcase"):
            ad = f"{tc.get('classname', '').split('.')[0]}::{tc.get('name')}"
            if tc.find("failure") is not None or tc.find("error") is not None:
                s = "KALDI"
            elif tc.find("skipped") is not None:
                s = "ATLANDI"
            else:
                s = "GEÇTİ"
            sayac[s] += 1
            satirlar.append(f"| {ad} | {s} | {float(tc.get('time', 0)):.2f} |")
    satirlar += ["", f"Toplam: GEÇTİ={sayac['GEÇTİ']} KALDI={sayac['KALDI']} ATLANDI={sayac['ATLANDI']}", "",
                 "### Ölçümler", "", "```"]
    for log in sorted(glob.glob(os.path.join(klasor, "gunluk-*.txt"))):
        with open(log, encoding="utf-8", errors="replace") as f:
            satirlar += [l.rstrip() for l in f if l.startswith("OLCUM|")]
    satirlar.append("```")
    metin = "\n".join(satirlar)
    print(metin)
    hedef = os.environ.get("GITHUB_STEP_SUMMARY")
    if hedef:
        with open(hedef, "a", encoding="utf-8") as f:
            f.write(metin + "\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else ".")
