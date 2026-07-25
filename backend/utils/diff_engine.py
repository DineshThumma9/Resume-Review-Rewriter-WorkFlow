import copy
import re
from difflib import SequenceMatcher


def find_best_match(target: str, text: str) -> str:
    # Split original text into sentences/lines
    lines = [line.strip() for line in re.split(r"\n|•|-|\*", text) if len(line.strip()) > 10]
    best_match = ""
    best_ratio = 0.0
    for line in lines:
        ratio = SequenceMatcher(None, target, line).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = line

    if best_ratio < 0.3:
        return ""
    return best_match


def compute_diff(old: str, new: str) -> str:
    if not old:
        return f"**{new}**"

    old_words = old.split()
    new_words = new.split()

    matcher = SequenceMatcher(None, old_words, new_words)
    result = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            result.append(" ".join(old_words[i1:i2]))
        elif tag == "replace":
            result.append(f"~~{' '.join(old_words[i1:i2])}~~ **{' '.join(new_words[j1:j2])}**")
        elif tag == "delete":
            result.append(f"~~{' '.join(old_words[i1:i2])}~~")
        elif tag == "insert":
            result.append(f"**{' '.join(new_words[j1:j2])}**")

    return " ".join(result).replace("  ", " ").strip()


def apply_diff_to_data(original_text: str, data: dict) -> dict:
    new_data = copy.deepcopy(data)

    # Process profile summary
    if new_data.get("profile") and new_data["profile"].get("profile_summary"):
        val = new_data["profile"]["profile_summary"]
        if val:
            best_old = find_best_match(val, original_text)
            new_data["profile"]["profile_summary"] = compute_diff(best_old, val)

    # Process experience
    if new_data.get("experience"):
        for exp in new_data["experience"]:
            if exp.get("responsibilities"):
                new_resp = []
                for resp in exp["responsibilities"]:
                    if resp:
                        best_old = find_best_match(resp, original_text)
                        new_resp.append(compute_diff(best_old, resp))
                    else:
                        new_resp.append(resp)
                exp["responsibilities"] = new_resp

    # Process projects
    if new_data.get("projects"):
        for proj in new_data["projects"]:
            if proj.get("highlights"):
                new_high = []
                for hl in proj["highlights"]:
                    if hl:
                        best_old = find_best_match(hl, original_text)
                        new_high.append(compute_diff(best_old, hl))
                    else:
                        new_high.append(hl)
                proj["highlights"] = new_high

    return new_data
