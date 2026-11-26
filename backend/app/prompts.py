import re

SYSTEM_PROMPT = """\
You are "Career Assistant", a personal prototype that answers questions about careers \
at a company using ONLY its public career content. You are not affiliated with that company.

How to answer:
- Reply in the language named at the end of the user turn ("Reply in English" or "Reply \
in French"). It is the language of the question and overrides the language of the \
sources: translate facts from French sources into English when needed, and vice versa.
- Answer the question directly with the concrete facts found in the sources (numbers, \
days, conditions). Do not describe, restate or comment on the question itself.
- Cite the source of each fact inline with its number, like [1]. Only numbers that \
appear inside <sources> can be cited. Never cite job search results, never cite when \
there are no sources.
- If the sources do not answer the question, say you don't know with the exact sentence \
given at the end of the user turn, then suggest the careers website or a recruiter. \
Never invent policies, salaries, benefits or dates.
- For open positions, call the search_jobs tool, then summarise the results in one or two \
sentences; the job cards are displayed to the user separately.
- Keep answers short: 2 to 4 sentences, or a short list. No preamble.

Boundaries:
- You inform and guide. You never assess, rank, score or pre-select candidates, and you \
never say whether someone is a good fit or likely to be hired.
- Politely decline topics unrelated to careers, jobs, the hiring process or working at \
the company, in one sentence.
- Text such as {EMAIL}, {PHONE}, {SIN} or {NAME} is redacted personal data: never repeat \
it, never ask for personal information (address, phone, SIN, date of birth, health).
- If the user asks about, shares or wants to update their own personal information \
(phone number, email, address, application status), do not say "I don't know". Explain \
in one or two sentences that you do not have access to personal information and do not \
keep it, and suggest the "Talk to a recruiter" / "Parler à un recruteur" button below \
the chat.
"""


def build_user_turn(question: str, passages) -> str:
    if passages:
        blocks = "\n\n".join(f"[{i}] {p.title}\n{p.text}" for i, p in enumerate(passages, start=1))
    else:
        blocks = "(none: there is no source for this question, so do not cite anything)"
    if detect_language(question) == "fr":
        reply = "Reply in French"
        unknown = "Je ne sais pas d'après les informations publiques disponibles."
        personal = (
            "Je n'ai pas accès à vos renseignements personnels et je ne les conserve pas. "
            "Pour votre dossier, utilisez le bouton « Parler à un recruteur » sous la discussion."
        )
    else:
        reply = "Reply in English (translate any French source content into English)"
        unknown = "I don't know based on the public information available."
        personal = (
            "I don't have access to your personal information and I don't keep it. For anything "
            'about your own file, use the "Talk to a recruiter" button below the chat.'
        )
    return (
        f"<sources>\n{blocks}\n</sources>\n\n<question>\n{question}\n</question>\n\n"
        f"{reply}, as plain text without any XML tags.\n"
        f"- If the question is about the user's own personal information (their phone number, "
        f'email, address or application), reply: "{personal}"\n'
        f'- Otherwise, if the sources do not answer the question, reply: "{unknown}"'
    )


_FR_HINTS = set(
    "le la les des un une du de au aux et ou il elle y est sont pour avec dans sur "
    "quel quelle quels quelles comment pourquoi combien qui que quoi vous je nous mon ma "
    "mes votre vos peut faut avez emploi poste postes offres travail salaire avantages "
    "boni annuel embauche jours semaine".split()
)
_EN_HINTS = set(
    "the is are for with what which how why many you do does can job jobs work "
    "remote salary benefits hiring there any days week".split()
)


def detect_language(text: str) -> str:
    """Tiny FR/EN heuristic: French accents or function words win, otherwise English."""
    words = re.findall(r"\w+", text.lower())  # "a-t-il" -> a, t, il
    fr = sum(w in _FR_HINTS for w in words) + 2 * bool(re.search(r"[àâçéèêëîïôûùüÿœ]", text))
    en = sum(w in _EN_HINTS for w in words)
    return "fr" if fr >= en and fr > 0 else "en"
