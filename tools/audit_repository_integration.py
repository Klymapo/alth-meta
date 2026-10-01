"""Read-only audit of the ALASTHEO content import and protected ALTH assets."""
import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]

def blob_sha(path):
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

def audit(root, verify_preservation=False):
    manifest = json.loads((root / "docs/integration/alastheo-import.json").read_text())
    failures = []
    imported = []
    for entry in manifest["files"]:
        path = root / entry["destination"]
        ok = path.is_file() and blob_sha(path) == entry["destination_blob_sha"]
        imported.append({"path": entry["destination"], "match": ok, "mode": entry["mode"]})
        if not ok:
            failures.append("IMPORT_MISMATCH: " + entry["destination"])
    preserved_changes = []
    preserved = manifest["preserved_alth_files"]
    for entry in preserved:
        path = root / entry["path"]
        if not path.is_file() or blob_sha(path) != entry["sha"]:
            preserved_changes.append(entry["path"])
            if verify_preservation:
                failures.append("ALTH_FILE_CHANGED: " + entry["path"])
    alpha = root / manifest["protected_alpha"]["path"]
    sha = hashlib.sha256(alpha.read_bytes()).hexdigest() if alpha.is_file() else None
    if sha != manifest["protected_alpha"]["sha256"]:
        failures.append("ALPHA_SHA_MISMATCH")
    policy = json.loads((root / "copox/production/theo_m5_policy.json").read_text())
    if policy.get("automatic_promotion_enabled") is not False:
        failures.append("AUTOMATIC_PROMOTION_ENABLED")
    if list((root / "copox/cassettes/enabled").glob("*.json")):
        failures.append("PRODUCTIVE_CASSETTE_ENABLED")
    links_checked = 0
    for entry in manifest["files"]:
        path = root / entry["destination"]
        if path.suffix != ".md":
            continue
        text = re.sub(r"```.*?```", "", path.read_text(), flags=re.S)
        for target in re.findall(r"!?(?:\[[^\]]*\])\(([^)]+)\)", text):
            target = target.strip().strip("<>")
            if re.match(r"https?://|mailto:|#", target):
                continue
            target = unquote(target.split("#", 1)[0])
            links_checked += 1
            if not (path.parent / target).exists():
                failures.append("BROKEN_LOCAL_LINK: " + entry["destination"] + " -> " + target)
    workbook = {}
    try:
        with zipfile.ZipFile(root / manifest["workbook"]) as z:
            bad = z.testzip()
            if bad:
                failures.append("WORKBOOK_ZIP_CRC: " + bad)
            names = z.namelist()
            if "xl/workbook.xml" not in names:
                failures.append("WORKBOOK_NOT_XLSX")
            else:
                doc = ElementTree.fromstring(z.read("xl/workbook.xml"))
                workbook["sheets"] = [e.attrib.get("name") for e in doc.iter()
                                      if e.tag.endswith("}sheet")]
                workbook["worksheet_files"] = sum(n.startswith("xl/worksheets/sheet") and n.endswith(".xml") for n in names)
    except (OSError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        failures.append("WORKBOOK_ERROR: " + str(exc))
    workflow = (root / ".github/workflows/repository-integration-audit.yml").read_text()
    if "contents: read" not in workflow or "${{ secrets." in workflow:
        failures.append("AUDIT_WORKFLOW_PERMISSION_OR_COMMERCIAL_SECRET")
    findings = []
    for path in sorted((root / ".github/workflows").glob("*.yml")):
        text = path.read_text()
        if "${{ secrets." in text:
            findings.append({"path": str(path.relative_to(root)), "severity": "info",
                             "finding": "Historical manual workflow references external credentials; not executed by this audit."})
    return {"status": "PASS" if not failures else "FAIL", "source_repository": manifest["source_repository"],
            "source_commit": manifest["source_commit"], "imported_file_count": len(imported),
            "imported": imported, "preserved_alth_file_count": len(preserved),
            "initial_preservation_enforced": verify_preservation, "changes_since_integration": preserved_changes,
            "alpha_sha256": sha, "local_links_checked": links_checked, "workbook": workbook,
            "automatic_promotion_enabled": policy.get("automatic_promotion_enabled"),
            "promotion_executed": False, "findings": findings, "failures": failures,
            "scope": "Content integrity, local documentation links, XLSX structure and model protection. Historical reconstruction methods and production-sheet data are not revalidated."}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=".copox/integration-audit/report.json")
    parser.add_argument("--verify-preservation", action="store_true", help="Enforce the original ALTH snapshot while importing; later development is reported separately.")
    args = parser.parse_args()
    report = audit(ROOT, args.verify_preservation)
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print("INTEGRATION_AUDIT:" + json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1

if __name__ == "__main__":
    sys.exit(main())
