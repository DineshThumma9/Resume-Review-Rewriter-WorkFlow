import copy
import os
import re

from jinja2 import Environment, FileSystemLoader


def get_proj_attr(project, attr_name, default=None):
    if isinstance(project, dict):
        return project.get(attr_name, default)
    return getattr(project, attr_name, default)


def set_proj_attr(project, attr_name, value):
    if isinstance(project, dict):
        project[attr_name] = value
    else:
        setattr(project, attr_name, value)


def clean_markup(text: str) -> str:
    return text.replace("**", "").replace("~~", "").strip()


def optimize_projects_for_rendering(data: dict) -> dict:
    """
    Optimizes project skills/technologies to prevent line overflow in LaTeX rendering.
    Orders technologies by JD keywords (if present) and core skills, then trims
    trailing ones if the total character length exceeds the safe page layout limit (85).
    """
    # Create a deep copy to avoid modifying original caller data/DB objects
    data_copy = copy.deepcopy(data)

    # Ensure both 'achievements' and 'achivements' exist in data dictionary for templates
    achievements = data_copy.get("achievements") if data_copy.get("achievements") is not None else data_copy.get("achivements")
    if achievements is not None:
        data_copy["achievements"] = achievements
        data_copy["achivements"] = achievements

    projects = data_copy.get("projects")
    if not projects or not isinstance(projects, list):
        return data_copy

    # Extract target keywords from JD
    jd_text = data_copy.get("jd") or data_copy.get("jd_snippet") or ""
    jd_words = set()
    if jd_text:
        jd_words = {word.lower() for word in re.findall(r"\b\w+\b", jd_text)}

    # Extract candidate's core technical skills
    core_skills = set()
    technical_skills = data_copy.get("technical_skills")
    if technical_skills and isinstance(technical_skills, list):
        for skill_group in technical_skills:
            skills_list = get_proj_attr(skill_group, "skills")
            if skills_list:
                if isinstance(skills_list, list):
                    for sk in skills_list:
                        core_skills.add(clean_markup(str(sk)).lower())
                elif isinstance(skills_list, str):
                    for sk in skills_list.split(","):
                        core_skills.add(clean_markup(sk).lower())

    for project in projects:
        name = get_proj_attr(project, "name") or ""
        date = get_proj_attr(project, "date") or ""
        technologies = get_proj_attr(project, "technologies")

        if not technologies or not isinstance(technologies, list):
            continue

        scored_techs = []
        for idx, tech in enumerate(technologies):
            tech_str = str(tech)
            tech_clean = clean_markup(tech_str)
            tech_lower = tech_clean.lower()

            is_in_jd = False
            if jd_text and (
                tech_lower in jd_text.lower()
                or any(w in jd_words for w in re.findall(r"\b\w+\b", tech_lower))
            ):
                is_in_jd = True

            is_in_core = tech_lower in core_skills or any(
                tech_lower in cs or cs in tech_lower for cs in core_skills
            )

            score = 0
            if is_in_jd:
                score = 2
            elif is_in_core:
                score = 1

            scored_techs.append((score, idx, tech_str))

        # Stable sort: descending by score, then ascending by original index
        scored_techs.sort(key=lambda x: (-x[0], x[1]))
        sorted_techs = [item[2] for item in scored_techs]

        # Trim technologies to fit standard page line length limits.
        # Safe limit is 85 characters for the total project title line.
        max_chars = 85
        valid_techs = []
        current_len = len(name) + len(date)
        has_techs = False

        for tech in sorted_techs:
            # We measure the length of the tech string as it will be rendered.
            # Clean markup for accurate length measurement.
            tech_clean_len = len(clean_markup(tech))
            sep_len = 3 if not has_techs else 2  # " | " or ", "
            added_len = tech_clean_len + sep_len

            if current_len + added_len <= max_chars:
                valid_techs.append(tech)
                current_len += added_len
                has_techs = True
            else:
                break

        set_proj_attr(project, "technologies", valid_techs)

    return data_copy


def escape_latex(value, diff=False):
    """
    Escape characters for LaTeX. Returns empty string for None/non-string values.
    """
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)

    # Extract **text** and ~~text~~ to protect them during the main escape
    bold_parts = []
    del_parts = []

    def bold_repl(m):
        bold_parts.append(m.group(1))
        return f"BBBOLD{len(bold_parts) - 1}EEE"

    def del_repl(m):
        del_parts.append(m.group(1))
        return f"DDDEL{len(del_parts) - 1}EEE"

    value = re.sub(r"\*\*(.*?)\*\*", bold_repl, value)
    value = re.sub(r"~~(.*?)~~", del_repl, value)

    # Define escaping rules
    LATEX_SUBS = (
        (re.compile(r"\\"), r"\\textbackslash "),
        (re.compile(r"([{}_#%&$])"), r"\\\1"),
        (re.compile(r"~"), r"\~{}"),
        (re.compile(r"\^"), r"\^{}"),
        (re.compile(r'"'), r"''"),
        (re.compile(r"\.\.\.+"), r"\\ldots "),
    )

    for pattern, replacement in LATEX_SUBS:
        value = pattern.sub(replacement, value)

    # Restore bold parts and del parts
    for i, part in enumerate(bold_parts):
        escaped_part = part
        for pattern, replacement in LATEX_SUBS:
            escaped_part = pattern.sub(replacement, escaped_part)
        if diff:
            value = value.replace(f"BBBOLD{i}EEE", f"\\added{{{escaped_part}}}")
        else:
            value = value.replace(f"BBBOLD{i}EEE", f"\\textbf{{{escaped_part}}}")

    for i, part in enumerate(del_parts):
        escaped_part = part
        for pattern, replacement in LATEX_SUBS:
            escaped_part = pattern.sub(replacement, escaped_part)
        if diff:
            value = value.replace(f"DDDEL{i}EEE", f"\\deleted{{{escaped_part}}}")
        else:
            value = value.replace(f"DDDEL{i}EEE", "")

    return value


def get_jinja_env(diff=False):
    # Templates directory is in the parent of services/
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    templates_dir = os.path.join(base_dir, "templates")

    env = Environment(
        loader=FileSystemLoader(templates_dir),
        block_start_string="[%",
        block_end_string="%]",
        variable_start_string="[[",
        variable_end_string="]]",
        comment_start_string="[#",
        comment_end_string="#]",
        trim_blocks=True,
        lstrip_blocks=True,
    )

    env.filters["escape_latex"] = lambda val: escape_latex(val, diff=diff)
    return env


def render_resume_template(template_name: str, data: dict, diff=False) -> str:
    """
    Render a LaTeX template with the given data.
    """
    optimized_data = optimize_projects_for_rendering(data)
    env = get_jinja_env(diff=diff)
    template = env.get_template(template_name)
    return template.render(**optimized_data)


def render_resume_template_from_string(tex_source: str, data: dict, diff=False) -> str:
    """
    Render a LaTeX template from a raw string with the given data.
    """
    optimized_data = optimize_projects_for_rendering(data)
    env = get_jinja_env(diff=diff)
    template = env.from_string(tex_source)
    return template.render(**optimized_data)
