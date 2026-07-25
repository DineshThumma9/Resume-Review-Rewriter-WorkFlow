from typing import Any

from schemas.schema import RewriteResume


def map_llm_to_profile(parsed: Any) -> dict[str, Any]:
    if isinstance(parsed, dict):
        parsed = RewriteResume.model_validate(parsed)

    details = getattr(parsed, "details", None)
    links = getattr(details, "profile_links", {}) if details else {}
    if links is None:
        links = {}

    profile_data = {
        "name": getattr(details, "name", "") if details else "",
        "phone": links.get("phone") or "",
        "location": links.get("location") or "",
        "github": links.get("github") or "",
        "linkedin": links.get("linkedin") or "",
        "website": links.get("website") or links.get("portfolio") or "",
        "sections": {},
    }

    sections = {}

    # Map Education
    if parsed.education:
        edu_list = []
        for idx, edu in enumerate(parsed.education):
            edu_list.append(
                {
                    "id": f"edu_{idx}",
                    "title": edu.course or "",
                    "subtitle": edu.institution or "",
                    "date": edu.year or "",
                    "description": f"GPA: {edu.gpa}" if edu.gpa else "",
                }
            )
        if edu_list:
            sections["education"] = edu_list

    # Map Experience
    if parsed.experience:
        exp_list = []
        for idx, exp in enumerate(parsed.experience):
            resp_str = (
                "\n".join([f"- {r}" for r in exp.responsibilities]) if exp.responsibilities else ""
            )
            exp_list.append(
                {
                    "id": f"exp_{idx}",
                    "title": exp.role or "",
                    "subtitle": exp.company or "",
                    "date": exp.duration or "",
                    "description": resp_str,
                }
            )
        if exp_list:
            sections["experience"] = exp_list

    # Map Projects
    if parsed.projects:
        proj_list = []
        for idx, proj in enumerate(parsed.projects):
            tech_str = ", ".join(proj.technologies) if proj.technologies else ""
            desc_str = proj.description or ""
            if proj.highlights:
                desc_str += "\n" + "\n".join([f"- {h}" for h in proj.highlights])
            proj_list.append(
                {
                    "id": f"proj_{idx}",
                    "title": proj.name or "",
                    "subtitle": "",
                    "skills": tech_str,
                    "link": proj.link or "",
                    "description": desc_str.strip(),
                }
            )
        if proj_list:
            sections["projects"] = proj_list

    # Map Skills
    if parsed.technical_skills:
        skills_list = []
        for idx, sk in enumerate(parsed.technical_skills):
            skills_list.append(
                {
                    "id": f"skill_{idx}",
                    "title": sk.category or "",
                    "skills": ", ".join(sk.skills) if sk.skills else "",
                }
            )
        if skills_list:
            sections["skills"] = skills_list

    # Map Achievements
    ach_source = getattr(parsed, "achievements", None) or getattr(parsed, "achivements", None)
    if ach_source:
        ach_list = []
        for idx, ach in enumerate(ach_source):
            ach_list.append({"id": f"ach_{idx}", "title": ach, "description": ""})
        if ach_list:
            sections["achievements"] = ach_list

    # Map Open Source
    if parsed.open_source:
        os_list = []
        for idx, os_item in enumerate(parsed.open_source):
            os_list.append({"id": f"os_{idx}", "description": os_item})
        if os_list:
            sections["open_source"] = os_list

    # Map Certifications
    if parsed.certifications:
        cert_list = []
        for idx, cert in enumerate(parsed.certifications):
            cert_list.append({"id": f"cert_{idx}", "title": cert})
        if cert_list:
            sections["certifications"] = cert_list

    # Map Hackathons
    if parsed.hackathons:
        hack_list = []
        for idx, hack in enumerate(parsed.hackathons):
            hack_list.append({"id": f"hack_{idx}", "title": hack})
        if hack_list:
            sections["hackathons"] = hack_list

    # Map Coursework
    if parsed.coursework:
        course_list = []
        for idx, course in enumerate(parsed.coursework):
            course_list.append({"id": f"course_{idx}", "description": course})
        if course_list:
            sections["coursework"] = course_list

    profile_data["sections"] = sections
    return profile_data
