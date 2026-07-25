DUMMY_RESUME_DATA = {
    "details": {
        "name": "Alex Applicant",
        "profile_summary": "Resourceful Senior Software Engineer with 6+ years of experience designing high-throughput distributed systems, cloud microservices, and modern web applications. Specialized in performance optimization, automated CI/CD pipelines, and technical leadership.",
        "profile_links": {
            "phone": "+1 (555) 123-4567",
            "email": "alex.applicant@example.com",
            "linkedin": "https://linkedin.com/in/alexapplicant",
            "github": "https://github.com/alexapplicant",
            "portfolio": "https://alexapplicant.dev",
            "location": "San Francisco, CA",
        },
    },
    "education": [
        {
            "institution": "University of Technology",
            "year": "2016 - 2020",
            "gpa": "3.9 / 4.0",
            "course": "B.S. in Computer Science & Engineering",
            "location": "San Francisco, CA",
        }
    ],
    "experience": [
        {
            "company": "Tech Innovations Inc.",
            "role": "Senior Backend Engineer",
            "duration": "Jan 2022 - Present",
            "location": "San Francisco, CA",
            "responsibilities": [
                "Architected and deployed event-driven microservices using FastAPI, Redis Pub/Sub, and Docker, improving system throughput by 45%.",
                "Optimized PostgreSQL database indexes and query plans, reducing average 99th-percentile API response latency from 800ms to 120ms.",
                "Mentored 4 junior developers, spearheaded code review standards, and automated deployment pipelines via GitHub Actions.",
            ],
        },
        {
            "company": "Web Solutions LLC",
            "role": "Full Stack Engineer",
            "duration": "Jun 2020 - Dec 2021",
            "location": "San Jose, CA",
            "responsibilities": [
                "Engineered responsive single-page web applications using React, TypeScript, and Tailwind CSS, increasing mobile user conversion by 30%.",
                "Integrated secure REST API endpoints with Stripe payment processing, handling $2M+ in monthly transaction volume.",
                "Collaborated cross-functionally with UI/UX designers and product managers to execute quarterly feature roadmaps.",
            ],
        },
    ],
    "technical_skills": [
        {
            "category": "Languages",
            "skills": [
                "Python",
                "TypeScript",
                "JavaScript",
                "SQL",
                "Go",
                "C++",
                "HTML/CSS",
            ],
        },
        {
            "category": "Frameworks & Libraries",
            "skills": [
                "FastAPI",
                "React.js",
                "Next.js",
                "Node.js",
                "Express",
                "Tailwind CSS",
            ],
        },
        {
            "category": "Infrastructure & Tools",
            "skills": [
                "Docker",
                "Kubernetes",
                "AWS (EC2, S3)",
                "Git",
                "PostgreSQL",
                "Redis",
                "CI/CD",
            ],
        },
    ],
    "projects": [
        {
            "name": "E-Commerce Platform Redesign",
            "date": "2023",
            "technologies": ["React", "Node.js", "MongoDB", "Redis"],
            "highlights": [
                "Implemented real-time inventory tracking and dynamic cart synchronization using WebSockets, reducing abandoned carts by 20%.",
                "Optimized asset loading and client bundle size, elevating Google Lighthouse performance score from 62 to 98.",
            ],
        },
        {
            "name": "AI Resume Reworker Platform",
            "date": "2024",
            "technologies": ["FastAPI", "LangChain", "Python", "Docker"],
            "highlights": [
                "Built an automated ATS optimization pipeline leveraging LLM structured output and Docker-based pdflatex compilation.",
                "Designed an asynchronous Redis queue architecture for real-time SSE job notifications and live feedback streaming.",
            ],
        },
    ],
    "certifications": [
        "AWS Certified Solutions Architect – Associate (2023)",
        "Certified Kubernetes Application Developer (CKAD - 2024)",
    ],
    "achivements": [
        "1st Place Winner – Annual University Hackathon (out of 120+ competing teams)",
        "Published technical article on High-Performance Python Microservices (50k+ reads)",
    ],
}


_VALIDATION_URLS: dict[str, str] = {
    "groq": "https://api.groq.com/openai/v1/models",
    "openai": "https://api.openai.com/v1/models",
    "anthropic": "https://api.anthropic.com/v1/models",
    "mistralai": "https://api.mistral.ai/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "google_genai": "https://generativelanguage.googleapis.com/v1beta/models",
    "huggingface": "https://router.huggingface.co/v1/models",
}


VALID_PROVIDERS = list(_VALIDATION_URLS.keys())


STATIC_MODELS = {
    "openai": ["gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"],
    "anthropic": [
        "claude-3-5-sonnet-20240620",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307",
    ],
    "google_genai": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-pro"],
    "groq": ["llama3-70b-8192", "llama3-8b-8192", "mixtral-8x7b-32768"],
    "mistralai": [
        "mistral-large-latest",
        "mistral-small-latest",
        "open-mixtral-8x7b",
    ],
    "openrouter": [
        "anthropic/claude-3.5-sonnet",
        "openai/gpt-4o",
        "meta-llama/llama-3-70b-instruct",
    ],
    "huggingface": [
        "meta-llama/Meta-Llama-3-70B-Instruct",
        "mistralai/Mixtral-8x7B-Instruct-v0.1",
    ],
}

DEFAULT_TEMPLATE = "jakes1.tex"
DEFAULT_LLM_PROVIDER = "groq"
DEFAULT_LLM_MODEL = "llama-3.3-70b-versatile"
MAX_REWRITE_ITERATIONS = 5
